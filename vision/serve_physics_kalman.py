# ServePhysics.py
# Fully dt-based, resolution-independent physics engine for serve detection
# with integrated Kalman filter for post-serve ball tracking.

from dataclasses import dataclass
from typing import Optional, Tuple, List
import numpy as np
from ultralytics import YOLO
from filterpy.kalman import KalmanFilter

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
    current_ball_pos_px: Optional[Tuple[float, float]] = None # ADDED: Current ball position

    # Live toss score (0..1-ish)
    toss_score: float = 0.0


# ================================================================
# Serve Physics Engine
# ================================================================

class ServePhysics:
    def __init__(self, poly, court_vertices, ball_model_path: str, fps: float):
        """
        poly: callable or np.poly1d giving px/ft as a function of image y.
        court_vertices: [TL, TR, BR, BL] pixel coordinates of singles court.
        ball_model_path: Path to the YOLO ball detection model.
        fps: Frames per second of the video.
        """
        self.poly = poly
        self.TL, self.TR, self.BR, self.BL = court_vertices
        self.fps = fps

        self.y_top = 0.5 * (self.TL[1] + self.TR[1])
        self.y_bottom = 0.5 * (self.BL[1] + self.BR[1])

        # --- Load model and initialize Kalman Filter ---
        self.ball_model = YOLO(ball_model_path)
        self.kf = KalmanFilter(dim_x=4, dim_z=2)
        dt = 1.0 / self.fps
        
        # State transition matrix (Constant Velocity Model)
        self.kf.F = np.array([[1, 0, dt, 0],
                              [0, 1, 0, dt],
                              [0, 0, 1, 0],
                              [0, 0, 0, 1]])

        # Measurement function
        self.kf.H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]])

        # Measurement noise covariance
        self.kf.R = np.eye(2) * 10

        # Process noise covariance
        self.kf.Q = np.eye(4) * 0.1

        # Initial state covariance
        self.kf.P = np.eye(4) * 100

        # --- State for integrated tracking ---
        self.is_tracking_serve = False
        self.last_ball_seen_t_tracking = -1.0
        self.ball_track = []  # For visualizing the tracked path (Kalman corrected)

        # -------------------------------
        # Ready-band parameters
        # -------------------------------
        # cy_ft < 0 means "behind baseline", cy_ft > 0 means inside court
        self.ready_min_ft = 0.5
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
        self.toss_to_trophy_max_s = 0.6  # [CHANGED]

        # If you want trophy to be optional “verification”, keep this False.
        # If True, we require trophy evidence near the toss to trigger serve.
        self.require_trophy = True

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
    # Ball Update (ball center from detector or KF)
    # ============================================================
    def update_ball(self, frame: np.ndarray, time_s: float, p_state: Optional[PlayerPhysicsState]) -> Optional[Tuple[float, float]]:
        """
        Updates ball state based on detection (toss mode) or tracking (serve mode).
        Returns the current ball position (x, y) in pixels if detected/tracked, else None.
        """
        current_ball_pos_for_drawing = None

        if self.is_tracking_serve:
            current_ball_pos_for_drawing = self.track_ball_after_serve(frame, time_s)
        else:
            # --- Arming Gate ---
            if p_state is None:
                return None # Cannot determine arming state without player

            is_armed = (
                p_state.in_ready and
                p_state.ready_duration_s >= self.ready_min_s and
                not self.in_quiet(time_s)
            )

            if not is_armed:
                self.ball_state.up_streak = 0
                self.ball_state.toss_onset_t = None
                self.ball_state.toss_score = 0.0
                return None # Stop processing for the ball

            # --- Original Toss Detection Logic (now armed) ---
            results = self.ball_model(frame, verbose=False, conf=0.15)
            ball_center_xy_px = None
            max_conf = 0
            for r in results:
                for box in r.boxes:
                    if box.conf > max_conf:
                        max_conf = box.conf
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        ball_center_xy_px = ((x1 + x2) / 2, (y1 + y2) / 2)
            
            b = self.ball_state
            b.current_ball_pos_px = ball_center_xy_px
            current_ball_pos_for_drawing = ball_center_xy_px

            if ball_center_xy_px is None:
                # Only reset on ball missing IF a toss hasn't already started.
                if b.toss_onset_t is None and b.last_ball_seen_t is not None and (time_s - b.last_ball_seen_t) > self.ball_missing_reset_s:
                    b.prev_t = None; b.prev_y_px = None; b.vy_up_pxps = 0.0; b.up_streak = 0; b.down_streak = 0; b.toss_onset_t = None; b.toss_score = 0.0
                return current_ball_pos_for_drawing

            _, y_px = ball_center_xy_px
            b.last_ball_seen_t = time_s

            if b.prev_t is None:
                b.prev_t = time_s; b.prev_y_px = float(y_px); b.vy_up_pxps = 0.0; b.up_streak = 0; b.down_streak = 0; b.toss_score = 0.0
                return current_ball_pos_for_drawing

            dt = max(1e-4, time_s - float(b.prev_t))
            dy = float(y_px) - float(b.prev_y_px)

            vy_up_raw = max(0.0, (-dy) / dt)
            b.vy_up_pxps = exp_smooth(b.vy_up_pxps, vy_up_raw, dt, self.tau_vy_ball)

            if b.vy_up_pxps >= self.toss_min_vy_up_pxps:
                b.up_streak += 1; b.down_streak = 0
            else:
                b.down_streak += 1; b.up_streak = max(0, b.up_streak - 1)

            if b.up_streak >= self.toss_min_up_streak and b.toss_onset_t is None:
                b.toss_onset_t = time_s

            streak_score = min(1.0, b.up_streak / max(1, self.toss_min_up_streak))
            vel_score = min(1.0, b.vy_up_pxps / (self.toss_min_vy_up_pxps * 2.0))
            b.toss_score = 0.5 * streak_score + 0.5 * vel_score

            b.prev_t = time_s
            b.prev_y_px = float(y_px)
            
        return current_ball_pos_for_drawing

    def track_ball_after_serve(self, frame: np.ndarray, time_s: float) -> Optional[Tuple[float, float]]:
        """
        Internal method to track the ball using Kalman filter after a serve is detected.
        Returns the tracked ball position (x,y) or None if tracking lost.
        """
        # First frame of tracking, initialize KF
        if not self.ball_track: # Check if ball_track is empty, meaning first frame
            if self.ball_state.current_ball_pos_px is not None:
                init_x, init_y = self.ball_state.current_ball_pos_px
                self.kf.x = np.array([[init_x], [init_y], [0], [0]])  # Initial velocity 0
                self.kf.P = np.eye(4) * 100  # Reset covariance
                self.ball_track.append((int(init_x), int(init_y)))
            else:
                # Cannot initialize KF without a starting point
                self.is_tracking_serve = False
                return None

        self.kf.predict()
        pred_x_kf, pred_y_kf = int(self.kf.x[0]), int(self.kf.x[1]) # Use separate names to avoid confusion

        # Define dynamic search window around KF prediction
        base_size = 150
        uncertainty = np.trace(self.kf.P[:2, :2])
        margin = int(base_size + uncertainty * 0.1)
        x1, y1 = max(0, pred_x_kf - margin), max(0, pred_y_kf - margin)
        x2, y2 = min(frame.shape[1], pred_x_kf + margin), min(frame.shape[0], pred_y_kf + margin)
        window = frame[y1:y2, x1:x2]

        # Use YOLO on the small window (conf=0.4 for post-serve tracking)
        results = self.ball_model(window, verbose=False, conf=0.4)
        
        best_det_pos_full_frame = None
        if results and results[0].boxes:
            # Find detection closest to KF prediction within the window
            window_center_pred = (pred_x_kf - x1, pred_y_kf - y1) # Prediction in window coordinates
            min_dist_sq = float('inf')
            
            for box in results[0].boxes:
                cx_window = (box.xyxy[0][0] + box.xyxy[0][2]) / 2
                cy_window = (box.xyxy[0][1] + box.xyxy[0][3]) / 2
                
                dist_sq = (cx_window - window_center_pred[0])**2 + (cy_window - window_center_pred[1])**2
                if dist_sq < min_dist_sq:
                    min_dist_sq = dist_sq
                    best_det_pos_full_frame = (x1 + cx_window, y1 + cy_window)
        
        # Update Kalman filter
        if best_det_pos_full_frame is not None:
            self.last_ball_seen_t_tracking = time_s
            self.kf.update(np.array(best_det_pos_full_frame))
            corrected_pos = (int(self.kf.x[0]), int(self.kf.x[1]))
            self.ball_track.append(corrected_pos)
        else:
            # If no detection, use Kalman prediction as best guess for display
            corrected_pos = (int(self.kf.x[0]), int(self.kf.x[1]))
            self.ball_track.append(corrected_pos) # Still add to trace even if undetected

        # Velocity check (in m/s)
        vx_pxpf, vy_pxpf = self.kf.x[2][0], self.kf.x[3][0] # Access scalar values
        
        # Ensure that pxpf is pixels per frame, not pixels per second (pxps)
        # kf.x[2] and kf.x[3] are velocities in pixels per dt (dt = 1/fps)
        # So, vx_pxps = vx_pxpf / dt = vx_pxpf * fps
        v_pxps = np.sqrt(vx_pxpf**2 + vy_pxpf**2) * self.fps # This is still correct. vx_pxpf is actually px/dt
        
        # If the velocity is in pixels/dt, then v_pxps = v_pxdt / dt.
        # kf.x[2] is px/frame. So v_pxps = vx_pxpf * fps. Correct.

        ppf = float(self.poly(self.kf.x[1][0])) # px/ft at current ball height (access scalar)
        v_ftps = v_pxps / max(ppf, 1e-6)
        v_mps = v_ftps * 0.3048

        # Termination conditions
        if (time_s - self.last_ball_seen_t_tracking) > 2.0 or v_mps < 0.5:
            self.is_tracking_serve = False
            self.ball_track = [] # Reset track

        return corrected_pos

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
            
            # If we were tracking a serve, reset that too if player exits ready
            if self.is_tracking_serve:
                self.is_tracking_serve = False
                self.ball_track = []

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
            # --- Trigger Tracking ---
            if self.ball_state.current_ball_pos_px is not None:
                self.is_tracking_serve = True
                self.last_ball_seen_t_tracking = time_s
                
                # Kalman filter initialization will happen in track_ball_after_serve on first call
                # self.ball_track is cleared there as well, so no need here.
            else:
                # If no ball was seen at serve start, we cannot track.
                # Just proceed with normal serve detection but without tracking.
                self.is_tracking_serve = False
                self.ball_track = [] # Ensure it's clear

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
            self.ball_state.current_ball_pos_px = None # Clear this for next serve

            return "serve_start"

        return None

    # This is a helper function to be called from the main loop to draw the track
    def draw_track(self, frame: np.ndarray) -> np.ndarray:
        if self.ball_track: # Check if there is any track to draw
            for i in range(1, len(self.ball_track)):
                if self.ball_track[i-1] is not None and self.ball_track[i] is not None:
                    cv2.line(frame, self.ball_track[i-1], self.ball_track[i], (0, 255, 0), 2)
        return frame
