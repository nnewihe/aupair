# ServePhysics.py
# Fully dt-based, resolution-independent physics engine for serve detection
# Hybrid D1 energy model (bbox vertical velocity only since Flow=A)
# Ball and player motion normalized to ft and ft/s

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
    cy_prev_ft: float = None
    v_cy_ftps: float = 0.0
    swing_energy_up: float = 0.0

    ready_start_t: float = None
    ready_start_cx_ft: float = None
    ready_duration_s: float = 0.0
    in_ready: bool = False

    sm_cy_ft: float = None

    trophy_conf: float = 0.0
    trophy_conf_t: float = None

    # ============================================================
    # [NEW] Serve-motion velocity based on bbox TOP (y1), not feet.
    # ============================================================
    top_prev_ft: float = None       # [NEW] previous bbox-top position in ft
    v_top_ftps: float = 0.0         # [NEW] upward speed proxy (ft/s, positive=up)

    # ============================================================
    # [NEW] Ready-band anti-flicker (grace)
    # ============================================================
    ready_last_true_t: float = None  # [NEW] last time we were confidently in-band


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
        self.TL, self.TR, self.BR, self.BL = court_vertices

        # -------------------------------
        # [NEW] Live scores (for overlay)
        # -------------------------------
        self.trophy_score = 0.0
        self.v_score = 0.0
        self.serve_score = 0.0

        # --- Ready-band max trackers ---
        self.v_score_max_ready = 0.0
        self.trophy_score_max_ready = 0.0

        # -------------------------------
        # [CHANGED] Quiet-period (“cooldown”) -- keep only ONE definition.
        # -------------------------------
        self.quiet_period_s = 2.0
        self.quiet_until_t = -1.0  # time until which we suppress new serves

        # Precompute baseline y's for sign logic
        self.y_top = 0.5 * (self.TL[1] + self.TR[1])
        self.y_bottom = 0.5 * (self.BL[1] + self.BR[1])

        # Physical thresholds
        self.max_lateral_drift_ft = 2.5
        self.swing_vel_threshold = 5

        # -------------------------------
        # [NEW/CHANGED] Tuneables for simplified detection
        # -------------------------------
        self.ready_min_s = 1.0           # player must be in ready band >= this
        self.serve_score_thresh = 0.75    # serve triggers if serve_score >= this
        self.v_score_margin = 4.0        # V1 = V0 + margin for normalization

        # [NEW] Ready grace to prevent flicker resets (seconds)
        self.ready_grace_s = 0.25        # tweak 0.15–0.40 depending on jitter

        # Ready band (signed cy_ft)
        self.ready_min_ft = -1
        self.ready_max_ft = 3

        # Smoothing tau (seconds)
        self.tau_pos = 0.05
        self.tau_vel = 0.03
        self.tau_energy = 0.12

    # -------------------------------
    # [NEW] Helper: are we in quiet period?
    # -------------------------------
    def in_quiet(self, time_s: float) -> bool:
        return time_s < float(self.quiet_until_t)

    # ============================================================
    # Player Update (bbox only; Flow = A)
    # ============================================================

    def update_player(self, box, time_s, trophy_conf=None):
        """
        box: [x1,y1,x2,y2] in pixels.
        time_s: timestamp in seconds.
        trophy_conf: float in [0..1] from YOLOv8-cls
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
        y_mid = 0.5 * (y_feet + y1)
        ppf = self.poly(y_mid)

        # REAL-WORLD VERTICAL DISTANCE TO BASELINES (signed cy_ft)
        P = (cx, y_feet)
        dist_top_px = point_line_distance_px(P, self.TL, self.TR)
        dist_bot_px = point_line_distance_px(P, self.BL, self.BR)

        dist_top_ft = dist_top_px / ppf
        dist_bot_ft = dist_bot_px / ppf

        if dist_top_ft < dist_bot_ft:
            nearest_dist_ft = dist_top_ft
            sign = -1.0 if y_feet < self.y_top else 1.0
        else:
            nearest_dist_ft = dist_bot_ft
            sign = -1.0 if y_feet > self.y_bottom else 1.0

        cy_ft = sign * nearest_dist_ft

        # dt and smoothing
        if p.prev_t is None:
            dt = 0.0
        else:
            dt = max(1e-4, time_s - p.prev_t)

        p.sm_cy_ft = exp_smooth(p.sm_cy_ft, cy_ft, dt, self.tau_pos)

        # REAL-WORLD VERTICAL VELOCITY (ft/s) along baseline-normal axis (feet/baseline distance)
        if p.cy_prev_ft is None or dt <= 0:
            v_cy_ftps = 0.0
        else:
            v_cy_ftps = (cy_ft - p.cy_prev_ft) / dt

        p.v_cy_ftps = exp_smooth(p.v_cy_ftps, v_cy_ftps, dt, self.tau_vel)
        p.cy_prev_ft = cy_ft

        # ============================================================
        # [NEW] Serve-motion velocity proxy from bbox TOP (y1)
        # - y1 decreases when player rises -> "up" corresponds to negative dy
        # - convert to ft using ppf; store upward speed as POSITIVE
        # ============================================================
        top_ft = float(y1) / float(ppf) if ppf > 1e-6 else 0.0  # [NEW]
        if p.top_prev_ft is None or dt <= 0:
            v_top_raw = 0.0
        else:
            v_top_raw = (top_ft - p.top_prev_ft) / dt  # ft/s (negative means moving up)

        up_top_ftps = max(0.0, -v_top_raw)  # [NEW] upward speed only
        p.v_top_ftps = exp_smooth(p.v_top_ftps, up_top_ftps, dt, self.tau_vel)  # [NEW]
        p.top_prev_ft = top_ft  # [NEW]

        # READY BAND (use smoothed position for stability)
        cy_for_ready = p.sm_cy_ft if p.sm_cy_ft is not None else cy_ft
        in_band = (self.ready_min_ft <= cy_for_ready <= self.ready_max_ft)

        # Lateral distance from left singles sideline in ft
        dist_left_px = point_line_distance_px(P, self.TL, self.BL)
        cx_ft = dist_left_px / ppf

        # ============================================================
        # [NEW] Ready-band grace to prevent flicker resets
        # If we *just* left the band, keep treating as in_band briefly.
        # ============================================================
        if in_band:
            p.ready_last_true_t = time_s  # [NEW]
        else:
            if p.ready_last_true_t is not None and (time_s - p.ready_last_true_t) <= self.ready_grace_s:
                in_band = True  # [NEW] treat as still in band during grace

        if in_band:
            if p.ready_start_t is None:
                p.ready_start_t = time_s
                p.ready_start_cx_ft = cx_ft

            lat_drift = abs(cx_ft - p.ready_start_cx_ft)
            if lat_drift > self.max_lateral_drift_ft:
                in_band = False
                # [NEW] if drift kicks us out, also clear last_true to avoid "sticky" band
                p.ready_last_true_t = None
            else:
                p.ready_duration_s = time_s - p.ready_start_t

        if not in_band:
            p.ready_start_t = None
            p.ready_duration_s = 0.0
            p.ready_start_cx_ft = None

        p.in_ready = in_band

        # TROPHY POSE CONFIDENCE
        if trophy_conf is not None:
            p.trophy_conf = float(trophy_conf)
            p.trophy_conf_t = time_s

        p.prev_t = time_s
        return p

    # ============================================================
    # Serve Detection (simplified, max-over-ready, quiet time)
    # ============================================================

    def detect_serve(self, p: PlayerPhysicsState, time_s: float):
        if p is None:
            return None

        READY_MIN_S = float(self.ready_min_s)
        V0 = float(self.swing_vel_threshold)
        V1 = V0 + float(self.v_score_margin)

        # --- Quiet period gate ---
        if time_s < self.quiet_until_t:
            self.serve_score = 0.0
            return None

        # ============================================================
        # [CHANGED] Reset accumulators ONLY when player is NOT in ready.
        # Do NOT require ready_duration >= READY_MIN_S to accumulate maxes.
        # ============================================================
        if not p.in_ready:  # [CHANGED]
            self.v_score_max_ready = 0.0
            self.trophy_score_max_ready = 0.0
            self.serve_score = 0.0
            self.v_score = 0.0
            self.trophy_score = 0.0
            return None

        # ============================================================
        # (keep your velocity evidence line as-is)
        # ============================================================
        v = max(0.0, float(getattr(p, "v_top_ftps", 0.0)))

        if v <= V0:
            v_score = 0.0
        elif v >= V1:
            v_score = 1.0
        else:
            v_score = (v - V0) / (V1 - V0)

        trophy_score = float(getattr(p, "trophy_conf", 0.0))

        # --- Accumulate maxima during ready band ---
        self.v_score_max_ready = max(self.v_score_max_ready, v_score)
        self.trophy_score_max_ready = max(self.trophy_score_max_ready, trophy_score)

        # --- Combined serve score (MAX-based) ---
        serve_score = (
            0.0 * self.v_score_max_ready +
            1.0 * self.trophy_score_max_ready
        )

        # keep live per-frame scores for overlay/debug
        self.v_score = float(v_score)
        self.trophy_score = float(trophy_score)
        self.serve_score = float(serve_score)

        # ============================================================
        # [CHANGED] Require ready_duration threshold ONLY to allow triggering.
        # (But we still accumulated maxes even if duration briefly reset.)
        # ============================================================
        if p.ready_duration_s < READY_MIN_S:  # [CHANGED]
            return None

        # --- Trigger serve ---
        if serve_score >= self.serve_score_thresh:
            self.quiet_until_t = time_s + self.quiet_period_s

            # Reset for next serve
            self.v_score_max_ready = 0.0
            self.trophy_score_max_ready = 0.0
            self.serve_score = 0.0
            self.v_score = 0.0
            self.trophy_score = 0.0

            return "serve_start"

        return None