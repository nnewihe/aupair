# ServePhysics.py
# Fully dt-based, resolution-independent physics engine for serve detection
# Hybrid D1 energy model (bbox vertical velocity only since Flow=A)
# Ball and player motion normalized to ft and ft/s
# Full serve state machine with baseline-relative, signed cy_ft

from dataclasses import dataclass
import numpy as np
import math
import time
from src.vision.utils import point_line_distance_px, exp_smooth, pixels_per_foot

# ================================================================
# Player + Ball Physics State
# ================================================================

@dataclass
class PlayerPhysicsState:
    prev_t: float = None

    # Real-world vertical distance from nearest baseline (ft), previous step
    cy_prev_ft: float = None

    # Real-world vertical velocity (ft/s) along baseline-normal axis
    v_cy_ftps: float = 0.0

    # Energy accumulator (hybrid D1 model, integrates positive v_cy_ftps)
    swing_energy_up: float = 0.0

    # Ready state
    ready_start_t: float = None
    ready_start_cx_ft: float = None
    ready_duration_s: float = 0.0
    in_ready: bool = False

    # Smoothed vertical position (ft)
    sm_cy_ft: float = None
    


@dataclass
class BallPhysicsState:
    prev_t: float = None
    x: float = None
    y: float = None
    vx_ftps: float = 0.0
    vy_ftps: float = 0.0


# ================================================================
# Serve Physics Engine
# ================================================================

class ServePhysics:
    def __init__(self, poly, court_vertices):
        """
        poly: callable or np.poly1d giving px/ft as a function of image y.
        court_vertices: [TL, TR, BR, BL] pixel coordinates of singles court.
        """
        self.poly = poly

        # vertices = [TL, TR, BR, BL]
        self.TL, self.TR, self.BR, self.BL = court_vertices

        # Precompute baseline y's for sign logic
        self.y_top = 0.5 * (self.TL[1] + self.TR[1])
        self.y_bottom = 0.5 * (self.BL[1] + self.BR[1])

        # Physical thresholds (defaults)
        self.swing_up_thresh = 0.5       # ft·s accumulated before upswing
        self.vertical_dom_thresh = 1.5   # vertical dominance threshold
        self.max_lateral_drift_ft = 2.5  # ft allowed during ready
        self.swing_vel_threshold = 5     # swing velocity threshold before upswing detected
    

        # Option A sign convention:
        #   cy_ft < 0 : behind baseline
        #   cy_ft > 0 : inside court (in front of baseline)
        # Ready band is behind the baseline, e.g. 3 ft to -1 ft ;  
        # Accounting for errors in court mask and the fact that people foot fault

        self.ready_min_ft = -1.0
        self.ready_max_ft = 3.0

        # Smoothing tau (seconds)
        self.tau_pos = 0.05        # position smoothing
        self.tau_vel = 0.03        # velocity smoothing
        self.tau_energy = 0.12     # energy smoothing (mild)

        # Serve FSM
        self.state = "idle"
        self.state_t = None        # time when state changed

    # ============================================================
    # Player Update (bbox only; Flow = A)
    # ============================================================

    def update_player(self, box, time_s):
        """
        box: [x1,y1,x2,y2] in pixels.
        time_s: timestamp in seconds.
        """
        if box is None:
            return None

        p = getattr(self, "player_state", None)
        if p is None:
            p = PlayerPhysicsState()
            self.player_state = p

        x1, y1, x2, y2 = box

        # Player feet position in pixels
        cx = 0.5 * (x1 + x2)
        y_feet = y2

        # px/ft at the player's feet row (perspective-aware)
        y_mid = 0.5*(y_feet + y1)   # between feet and head
        ppf = self.poly(y_mid)

        # --------------------------------------------------------
        # REAL-WORLD VERTICAL DISTANCE TO BASELINES (signed cy_ft)
        # --------------------------------------------------------
        P = (cx, y_feet)

        # Distances in px to each baseline
        dist_top_px = point_line_distance_px(P, self.TL, self.TR)
        dist_bot_px = point_line_distance_px(P, self.BL, self.BR)

        # Convert to ft
        dist_top_ft = dist_top_px / ppf
        dist_bot_ft = dist_bot_px / ppf

        # Decide which baseline is nearer and assign sign
        if dist_top_ft < dist_bot_ft:
            nearest_dist_ft = dist_top_ft
            # For the far (top) baseline, feet above it (smaller y) means "behind"
            sign = -1.0 if y_feet < self.y_top else 1.0
        else:
            nearest_dist_ft = dist_bot_ft
            # For the near (bottom) baseline, feet below it (larger y) means "behind"
            sign = -1.0 if y_feet > self.y_bottom else 1.0

        # Signed real-world vertical coordinate (ft)
        cy_ft = sign * nearest_dist_ft

        # --------------------------------------------------------
        # dt and smoothing
        # --------------------------------------------------------
        if p.prev_t is None:
            dt = 0.0
        else:
            dt = max(1e-4, time_s - p.prev_t)

        # Smoothed vertical position
        p.sm_cy_ft = exp_smooth(p.sm_cy_ft, cy_ft, dt, self.tau_pos)

        # --------------------------------------------------------
        # REAL-WORLD VERTICAL VELOCITY (ft/s)
        # --------------------------------------------------------
        if p.cy_prev_ft is None or dt <= 0:
            v_cy_ftps = 0.0
        else:
            v_cy_ftps = (cy_ft - p.cy_prev_ft) / dt

        p.v_cy_ftps = exp_smooth(p.v_cy_ftps, v_cy_ftps, dt, self.tau_vel)
        p.cy_prev_ft = cy_ft


        # --------------------------------------------------------
        # READY BAND (behind nearest baseline, using signed cy_ft)
        # --------------------------------------------------------
        in_band = (self.ready_min_ft <= cy_ft <= self.ready_max_ft)

        # Lateral distance from left singles sideline in ft
        dist_left_px = point_line_distance_px(P, self.TL, self.BL)
        cx_ft = dist_left_px / ppf

        # Ready-time and lateral constraint
        if in_band:
            if p.ready_start_t is None:
                p.ready_start_t = time_s
                p.ready_start_cx_ft = cx_ft

            # Lateral drift constraint (ft)
            lat_drift = abs(cx_ft - p.ready_start_cx_ft)
            if lat_drift > self.max_lateral_drift_ft:
                in_band = False
            else:
                p.ready_duration_s = time_s - p.ready_start_t

        if not in_band:
            # Reset
            p.ready_start_t = None
            p.ready_duration_s = 0.0
            p.ready_start_cx_ft = None

        p.in_ready = in_band

        # Bookkeeping
        p.prev_t = time_s

        return p


    # ============================================================
    # Serve Detection FSM
    # ============================================================

    def detect_serve(self, p: PlayerPhysicsState,  time_s: float):
        """
        Returns one of:
            None
            "serve_start"
            "serve_contact"
            "serve_end"
        """

        if p is None:
            return None

        # Vertical dominance: ratio of player vertical velocity to ball vertical
        vertical_dom = abs(p.v_cy_ftps)

        # --- FSM ---
        if self.state == "idle":
            # Look for ready state or small bouncing before serve
            if p.in_ready and p.ready_duration_s > 2.0:
                self.state = "ready"
                self.state_t = time_s
                return None

        elif self.state == "ready":
            # Transition to upswing when energy starts to rise
            if p.v_cy_ftps > self.swing_vel_threshold:
#            if p.swing_energy_up > self.swing_up_thresh:
                self.state = "upswing"
                self.state_t = time_s
                return "serve_start"

        elif self.state == "upswing":
            # End of serve when motion settles
            if vertical_dom < 0.3:
                self.state = "idle"
                self.state_t = time_s
                return "serve_end"

        return None