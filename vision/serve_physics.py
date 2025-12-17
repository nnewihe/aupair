# ServePhysics.py
# Fully dt-based, resolution-independent physics engine for serve detection
# (Ready-band gating + Trophy pose + Ball-toss motion)
#
# Key ideas (beginner-friendly):
#  1) We estimate whether the player is "ready" based on their feet location vs baselines (in feet).
#  2) While the player is in the ready band, we watch:
#       - trophy_conf (from your trophy-pose classifier)
#       - ball vertical motion (from your YOLO ball detector) to detect a toss-like upward movement
#  3) We compute scores while in ready:
#       serve_score = 0.5 * toss_score + 0.5 * trophy_score
#  4) If serve_score crosses a threshold, we emit "serve_start" and enter a quiet period.

from dataclasses import dataclass
from typing import Optional, Tuple, List
import numpy as np

from src.vision.utils import point_line_distance_px, exp_smooth


# ================================================================
# Player Physics State
# ================================================================

@dataclass
class PlayerPhysicsState:
    prev_t: Optional[float] = None

    # Signed distance from nearest baseline (ft)
    cy_prev_ft: Optional[float] = None
    sm_cy_ft: Optional[float] = None

    # Ready-band bookkeeping
    ready_start_t: Optional[float] = None
    ready_start_cx_ft: Optional[float] = None
    ready_duration_s: float = 0.0
    in_ready: bool = False
    ready_last_true_t: Optional[float] = None  # for anti-flicker grace

    # Trophy classifier
    trophy_conf: float = 0.0
    trophy_conf_t: Optional[float] = None


# ================================================================
# Ball / Toss State
# ================================================================

@dataclass
class BallTossState:
    """
    Tracks ball center over time so we can estimate vertical velocity and detect
    "persistent upward motion" (a toss).
    """
    prev_t: Optional[float] = None
    prev_y_px: Optional[float] = None

    # Smoothed upward velocity in px/s (positive = moving up)
    vy_up_pxps: float = 0.0

    # Toss detection counters
    up_streak: int = 0
    down_streak: int = 0

    # Toss event timing
    toss_onset_t: Optional[float] = None    # first time we considered toss "on"
    last_ball_seen_t: Optional[float] = None

    # Live toss score (0..1-ish)
    toss_score: float = 0.0


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

        # Precompute baseline y's for sign logic
        self.y_top = 0.5 * (self.TL[1] + self.TR[1])
        self.y_bottom = 0.5 * (self.BL[1] + self.BR[1])

        # -------------------------------
        # Ready-band parameters
        # -------------------------------
        # cy_ft < 0 means "behind baseline", cy_ft > 0 means inside court
        self.ready_min_ft = -1.0
        self.ready_max_ft = 3.0

        # Must be ready for at least this long before we allow a serve event
        self.ready_min_s = 1.0

        # Grace to reduce flicker when bbox jitters at boundary
        self.ready_grace_s = 0.50

        # Lateral drift constraint (ft) during ready
        self.max_lateral_drift_ft = 2.5

        # Smoothing
        self.tau_pos = 0.05
        self.tau_vy_ball = 0.06  # a bit slower so toss velocity is stable

        # -------------------------------
        # Quiet period (cooldown)
        # -------------------------------
        self.quiet_period_s = 2.5
        self.quiet_until_t = -1.0

        # -------------------------------
        # Scores for overlay/debug
        # -------------------------------
        self.trophy_score = 0.0
        self.toss_score = 0.0
        self.serve_score = 0.0

        # Max trackers while in-ready (we keep “best evidence so far”)
        self.trophy_max_ready = 0.0
        self.toss_max_ready = 0.0

        # Serve trigger threshold on serve_score
        self.serve_score_thresh = 0.70

        # -------------------------------
        # Toss detection tuneables
        # -------------------------------
        # Minimum upward velocity (px/s) to count as an "up" frame
        self.toss_min_vy_up_pxps = 120.0

        # How many "up" frames needed (persistence) before we consider toss “active”
        self.toss_min_up_streak = 4

        # If ball disappears for too long (seconds), reset toss tracking
        self.ball_missing_reset_s = 0.35

        # -------------------------------
        # Trophy–toss pairing window
        # -------------------------------
        # [CHANGED] We allow either order: trophy can occur before toss or after toss.
        # This is the maximum allowed separation (seconds) between toss onset and trophy.
        self.toss_to_trophy_max_s = 1.5  # [CHANGED]

        # If you want trophy to be optional “verification”, keep this False.
        # If True, we require trophy evidence near the toss to trigger serve.
        self.require_trophy = False

        # Internal states
        self.player_state: Optional[PlayerPhysicsState] = None
        self.ball_state: BallTossState = BallTossState()

        # For pairing: store last times we saw “strong” trophy in ready
        self._trophy_peak_t: Optional[float] = None

    # -------------------------------
    # Helper: quiet period
    # -------------------------------
    def in_quiet(self, time_s: float) -> bool:
        return time_s < float(self.quiet_until_t)

    # ============================================================
    # Player Update (bbox only)
    # ============================================================
    def update_player(self, box, time_s: float, trophy_conf: Optional[float] = None) -> Optional[PlayerPhysicsState]:
        """
        box: [x1,y1,x2,y2] in pixels
        trophy_conf: float in [0..1] (from trophy pose classifier)
        """
        if box is None:
            return None

        p = self.player_state
        if p is None:
            p = PlayerPhysicsState()
            self.player_state = p

        x1, y1, x2, y2 = box
        cx = 0.5 * (x1 + x2)
        y_feet = y2

        # px/ft at player row (perspective-aware)
        y_mid = 0.5 * (y_feet + y1)
        ppf = float(self.poly(y_mid))

        # Distances in px to each baseline
        P = (cx, y_feet)
        dist_top_px = point_line_distance_px(P, self.TL, self.TR)
        dist_bot_px = point_line_distance_px(P, self.BL, self.BR)

        # Convert to ft
        dist_top_ft = dist_top_px / max(ppf, 1e-6)
        dist_bot_ft = dist_bot_px / max(ppf, 1e-6)

        # Choose nearest baseline and assign sign
        if dist_top_ft < dist_bot_ft:
            nearest_dist_ft = dist_top_ft
            sign = -1.0 if y_feet < self.y_top else 1.0
        else:
            nearest_dist_ft = dist_bot_ft
            sign = -1.0 if y_feet > self.y_bottom else 1.0

        cy_ft = sign * nearest_dist_ft

        # dt
        if p.prev_t is None:
            dt = 0.0
        else:
            dt = max(1e-4, time_s - p.prev_t)

        # Smooth vertical position for stability
        p.sm_cy_ft = exp_smooth(p.sm_cy_ft, cy_ft, dt, self.tau_pos)
        p.cy_prev_ft = cy_ft

        # Ready-band test uses smoothed coordinate (less jitter)
        cy_for_ready = p.sm_cy_ft if p.sm_cy_ft is not None else cy_ft
        in_band = (self.ready_min_ft <= cy_for_ready <= self.ready_max_ft)

        # -----------------------------
        # [CHANGED] Lateral drift from the CENTER of the bbox (more stable)
        # -----------------------------
        cy_center = 0.5 * (y1 + y2)
        P_lat = (cx, cy_center)

        # Use ppf at the same y as the lateral point (avoid scale jitter)
        ppf_lat = float(self.poly(cy_center))

        dist_left_px = point_line_distance_px(P_lat, self.TL, self.BL)
        cx_ft = dist_left_px / max(ppf_lat, 1e-6)

        # Anti-flicker grace
        if in_band:
            p.ready_last_true_t = time_s
        else:
            if p.ready_last_true_t is not None and (time_s - p.ready_last_true_t) <= self.ready_grace_s:
                in_band = True

        # Ready duration + lateral drift check
        if in_band:
            if p.ready_start_t is None:
                p.ready_start_t = time_s
                p.ready_start_cx_ft = cx_ft

            lat_drift = abs(cx_ft - float(p.ready_start_cx_ft))
            if lat_drift > self.max_lateral_drift_ft:
                # Hard reset if drift too large
                in_band = False
                p.ready_start_t = None
                p.ready_start_cx_ft = None
                p.ready_duration_s = 0.0
                p.ready_last_true_t = None
            else:
                p.ready_duration_s = time_s - float(p.ready_start_t)
        else:
            p.ready_start_t = None
            p.ready_start_cx_ft = None
            p.ready_duration_s = 0.0

        p.in_ready = in_band

        # Trophy update
        if trophy_conf is not None:
            p.trophy_conf = float(trophy_conf)
            p.trophy_conf_t = time_s

        p.prev_t = time_s
        return p

    # ============================================================
    # Ball Update (ball center from detector)
    # ============================================================
    def update_ball(self, ball_center_xy_px: Optional[Tuple[float, float]], time_s: float) -> BallTossState:
        """
        ball_center_xy_px: (x_px, y_px) if ball detected this frame, else None
        """
        b = self.ball_state

        # If ball not detected, potentially reset after timeout
        if ball_center_xy_px is None:
            if b.last_ball_seen_t is not None and (time_s - b.last_ball_seen_t) > self.ball_missing_reset_s:
                # reset tracking
                b.prev_t = None
                b.prev_y_px = None
                b.vy_up_pxps = 0.0
                b.up_streak = 0
                b.down_streak = 0
                b.toss_onset_t = None
                b.toss_score = 0.0
            return b

        # Ball detected
        _, y_px = ball_center_xy_px
        b.last_ball_seen_t = time_s

        if b.prev_t is None:
            b.prev_t = time_s
            b.prev_y_px = float(y_px)
            b.vy_up_pxps = 0.0
            b.up_streak = 0
            b.down_streak = 0
            b.toss_score = 0.0
            return b

        dt = max(1e-4, time_s - float(b.prev_t))
        dy = float(y_px) - float(b.prev_y_px)

        # In image coordinates: y decreases when moving up.
        vy_up_raw = max(0.0, (-dy) / dt)  # px/s upward
        b.vy_up_pxps = exp_smooth(b.vy_up_pxps, vy_up_raw, dt, self.tau_vy_ball)

        # Update persistence counters
        if b.vy_up_pxps >= self.toss_min_vy_up_pxps:
            b.up_streak += 1
            b.down_streak = 0
        else:
            b.down_streak += 1
            # let up_streak decay slowly instead of snapping to 0
            b.up_streak = max(0, b.up_streak - 1)

        # Detect toss onset
        if b.up_streak >= self.toss_min_up_streak and b.toss_onset_t is None:
            b.toss_onset_t = time_s

        # Simple toss score (0..1): based on persistence + velocity
        # (You can tune the denominator to match typical speeds)
        streak_score = min(1.0, b.up_streak / max(1, self.toss_min_up_streak))
        vel_score = min(1.0, b.vy_up_pxps / (self.toss_min_vy_up_pxps * 2.0))
        b.toss_score = 0.5 * streak_score + 0.5 * vel_score

        b.prev_t = time_s
        b.prev_y_px = float(y_px)
        return b

    # ============================================================
    # Serve Detection (ball toss + trophy, max-over-ready, quiet time)
    # ============================================================
    def detect_serve(self, p: PlayerPhysicsState, time_s: float) -> Optional[str]:
        if p is None:
            return None

        # Quiet period gate
        if self.in_quiet(time_s):
            # keep live overlay readable during quiet (optional)
            self.serve_score = 0.0
            return None

        # If not in ready band: reset all “in-ready” evidence
        if not p.in_ready:
            self.trophy_score = 0.0
            self.toss_score = 0.0
            self.serve_score = 0.0
            self.trophy_max_ready = 0.0
            self.toss_max_ready = 0.0
            self._trophy_peak_t = None

            # also reset ball toss onset (so next ready window starts fresh)
            self.ball_state.toss_onset_t = None
            self.ball_state.up_streak = 0
            self.ball_state.toss_score = 0.0
            return None

        # Always update per-frame scores (for overlay)
        trophy_now = float(getattr(p, "trophy_conf", 0.0))
        toss_now = float(getattr(self.ball_state, "toss_score", 0.0))

        self.trophy_score = trophy_now
        self.toss_score = toss_now

        # Track max evidence while in ready
        if trophy_now >= self.trophy_max_ready:
            self.trophy_max_ready = trophy_now
            self._trophy_peak_t = time_s  # record when we saw our current best trophy
        self.toss_max_ready = max(self.toss_max_ready, toss_now)

        # Compute serve score from max-over-ready evidence
        serve_score = 0.5 * self.toss_max_ready + 0.5 * self.trophy_max_ready
        self.serve_score = float(serve_score)

        # Must be in ready for at least ready_min_s before we can trigger
        if float(p.ready_duration_s) < float(self.ready_min_s):
            return None

        # ------------------------------------------------------------
        # [CHANGED] Trophy–toss timing check now allows either order.
        # Previously, we forced "toss before trophy" — too rigid because
        # some servers show trophy posture before the ball is reliably seen.
        # ------------------------------------------------------------
        toss_t = self.ball_state.toss_onset_t
        trophy_t = self._trophy_peak_t

        paired_ok = True
        if self.require_trophy:
            # if trophy is required, we need both timestamps and they must be close
            if toss_t is None or trophy_t is None:
                paired_ok = False
            else:
                dt = abs(float(trophy_t) - float(toss_t))                 # [CHANGED]
                paired_ok = (dt <= float(self.toss_to_trophy_max_s))      # [CHANGED]
        else:
            # trophy optional: only enforce pairing if BOTH exist (used as verification)
            if toss_t is not None and trophy_t is not None:
                dt = abs(float(trophy_t) - float(toss_t))                 # [CHANGED]
                paired_ok = (dt <= float(self.toss_to_trophy_max_s))      # [CHANGED]

        # Trigger serve if score threshold met AND timing constraints satisfied
        if paired_ok and serve_score >= float(self.serve_score_thresh):
            self.quiet_until_t = time_s + float(self.quiet_period_s)

            # Reset evidence for next serve window
            self.trophy_max_ready = 0.0
            self.toss_max_ready = 0.0
            self.trophy_score = 0.0
            self.toss_score = 0.0
            self.serve_score = 0.0
            self._trophy_peak_t = None

            # Reset ball toss state so next serve can be detected cleanly
            self.ball_state.toss_onset_t = None
            self.ball_state.up_streak = 0
            self.ball_state.toss_score = 0.0

            return "serve_start"

        return None