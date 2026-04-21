"""
anya_transitions.py
===================
State machine logic. Determines transitions between WAITING, ARMED, and ACTIVE
based on the rolling telemetry buffer from anya_base.py.

ACTIVE → WAITING uses a two-stage hybrid model:

  Stage 1 — Ball Trace Gate (primary):
    If an active ball trace exists within the BALL_TIMEOUT window (i.e. ball
    candidates are present AND not identified as a stationary cluster by DBSCAN),
    the point stays ACTIVE unconditionally.

  Stage 2 — Energy Bar Fallback:
    When no active ball trace has been seen for BALL_TIMEOUT seconds, an energy
    bar is introduced.  The bar starts at 1.0, anchored to:
        max(last_active_trace_time, active_start_time + SERVE_TO_ENERGY_DELAY)
    It decays or boosts each frame based on near-player telemetry (velocity,
    shape change, walking gait — same model as near_anya.py).  The point dies
    when the bar reaches 0.

    If a new active ball trace appears while the energy bar is running, the bar
    is discarded and reset to 1.0 (point stays ACTIVE).  The same two-stage
    logic applies again if the ball goes quiet a second time.

When a transition fires, `last_transition_time` is set to the anchor time used
for the energy bar (i.e. when the point effectively died).  The main loop uses
this to rewind output-video writing.
"""

from collections import deque
from typing import List, Optional, Tuple
import math

import numpy as np
from sklearn.cluster import DBSCAN


class TransitionEngine:
    def __init__(self, fps: float):
        self.fps = fps

        # ------------------------------------------------------------------
        # WAITING
        # ------------------------------------------------------------------
        self.READY_MIN_DIST_FT   = -0.5
        self.READY_MAX_DIST_FT   = 3.5
        self.READY_WAIT_TIME_SEC = 0.4

        # ------------------------------------------------------------------
        # ARMED
        # ------------------------------------------------------------------
        self.ARMED_BAND_WINDOW_SEC      = 2.0
        self.ARMED_OUT_RATIO_THRESHOLD  = 0.25
        self.TRANSITION_SCORE_THRESHOLD = 0.55
        self.EVENT_WINDOW_SECONDS       = 1.2

        # ------------------------------------------------------------------
        # ACTIVE — Ball trace detection
        # ------------------------------------------------------------------
        self.BALL_TIMEOUT             = 2.5   # seconds — DBSCAN history window
        self.BALL_DEAD_SPEED_FTS      = 6.0   # ft/s — "stationary" threshold (DBSCAN + trace filter)
        self.BALL_DEAD_CLUSTER_EPS_FT = 3.0   # ft  — DBSCAN eps
        self.FAST_BALL_THRESHOLD_FTS  = 15.0  # ft/s — serve/groundstroke speed
        self.EXTENDED_TIMEOUT_SEC     = 4.0   # extra grace for fast balls
        self.MAX_BALL_SPEED_FTS       = 176.0 # ft/s — physical upper bound (≈120 mph serve)
        self.BALL_SPEED_WINDOW_SEC    = 0.15  # seconds — displacement window for speed smoothing

        # ------------------------------------------------------------------
        # ACTIVE — Energy bar constants (adapted from near_anya.py Config)
        # ------------------------------------------------------------------
        self.ENERGY_BOOST_SPRINT          = 4.0  # energy/second while sprinting
        self.ENERGY_BOOST_SWING           = 4.0  # energy/second during swing/split-step
        self.ENERGY_DECAY_WALKING         = 0.25 # energy/second drain while walking
        self.ENERGY_DECAY_MISSING         = 0.4  # energy/second drain when player not detected
        self.ENERGY_DECAY_STILL           = 0.25 # energy/second drain while standing still
        self.PLAYER_SPRINT_VELOCITY_FTS   = 7.0  # ft/s (world space) → sprinting
        self.PLAYER_STILL_VELOCITY_FTS    = 1.5  # ft/s (world space) → standing still
        self.VELOCITY_WINDOW_SIZE         = 20   # number of player position samples to smooth over
        self.ACTIVE_PLAYER_STRIDE         = 4    # must match AnyaTelemetryProvider.ACTIVE_PLAYER_STRIDE
        # Walking gait detection
        self.GAIT_BUFFER_FRAMES  = 45
        self.GAIT_MIN_REVERSALS  = 2
        self.GAIT_MAX_REVERSALS  = 8
        self.GAIT_MIN_DRIFT_PX   = 10.0

        # ------------------------------------------------------------------
        # Persistent state — WAITING
        # ------------------------------------------------------------------
        self.near_ready_start_time: Optional[float] = None

        # ------------------------------------------------------------------
        # Persistent state — ARMED
        # ------------------------------------------------------------------
        self.armed_band_history: deque = deque()

        self.toss_consecutive_frames:       int             = 0
        self.toss_gap_frames:               int             = 0
        self.toss_ball_above_head_detected: bool            = False
        self.toss_min_y_px:                 Optional[float] = None
        self.last_toss_ball:                Optional[dict]  = None

        self._trophy_scores: deque = deque()
        self._toss_scores:   deque = deque()

        self.last_serve_scores = {
            "trophy_score": 0.0,
            "toss_score":   0.0,
            "serve_score":  0.0,
        }

        # ------------------------------------------------------------------
        # Persistent state — ACTIVE (ball tracking)
        # ------------------------------------------------------------------
        self.active_start_time:   float = 0.0
        self.last_ball_seen_time: float = 0.0

        # Rolling world-space ball history over BALL_TIMEOUT window: (t, wx, wy)
        self._active_ball_world_history: deque = deque()

        # Timestamp of the most recent frame that had an active (non-stationary) trace
        self.last_active_trace_time: float = 0.0

        # DBSCAN result cache
        self._stationary_cache_len:    int                    = -1
        self._stationary_cache_result: List[Tuple[float, float]] = []

        # ------------------------------------------------------------------
        # Persistent state — ACTIVE (energy bar)
        # ------------------------------------------------------------------
        self.energy_bar_mode:       bool  = False  # True while energy bar is active
        self.energy_bar_start_time: float = 0.0    # anchor time for last_transition_time rewind
        self.point_energy:          float = 1.0

        # Player tracking buffers (pixel space) for energy computation
        self._energy_player_positions: deque = deque(maxlen=self.VELOCITY_WINDOW_SIZE)
        self._energy_player_boxes:     deque = deque(maxlen=5)
        self._energy_gait_y_buffer:    deque = deque(maxlen=self.GAIT_BUFFER_FRAMES)
        self._player_missing_frames:   int   = 0
        self.PLAYER_MISSING_GRACE_FRAMES: int = 5
        self.PLAYER_EMA_ALPHA:           float = 0.25  # EMA smoothing factor for world position
                                                        # (lower = more smoothing)

        # EMA-smoothed world position; reset to None on each ACTIVE exit
        self._smoothed_player_world: Optional[Tuple[float, float]] = None

        # Ball trace — pixel centres of speed-validated detections (960×540 space)
        # maxlen ≈ 2s worth of frames; cleared on each ACTIVE exit
        self._ball_trace_pixels: deque = deque(maxlen=120)

        # ------------------------------------------------------------------
        # Signal to the main loop: timestamp to truncate output on transition.
        # ------------------------------------------------------------------
        self.last_transition_time: Optional[float] = None

        # Debug snapshot for HUD / CSV
        self.last_active_debug = {
            "time_since_trace":    0.0,
            "has_active_trace":    False,
            "energy_bar_mode":     False,
            "point_energy":        1.0,
            "player_velocity":     0.0,
            "shape_change":        0.0,
            "walking_gait":        False,
            "ball_count":          0,
            "window_max_speed_fts": 0.0,
        }

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def evaluate_transitions(self, history: deque, current_state: str) -> str:
        if not history:
            return current_state
        if current_state == "WAITING":
            return self._check_waiting(history)
        if current_state == "ARMED":
            return self._check_armed(history)
        if current_state == "ACTIVE":
            return self._check_active(history)
        return current_state

    # ------------------------------------------------------------------
    # WAITING → ARMED
    # ------------------------------------------------------------------

    def _check_waiting(self, history: deque) -> str:
        frame = history[-1]
        now   = frame.timestamp

        if frame.near_player_world is None:
            self.near_ready_start_time = None
            return "WAITING"

        _, wy   = frame.near_player_world
        dist_ft = abs(wy)
        in_zone = wy < 0 and self.READY_MIN_DIST_FT <= dist_ft <= self.READY_MAX_DIST_FT

        if in_zone:
            if self.near_ready_start_time is None:
                self.near_ready_start_time = now
            elapsed = now - self.near_ready_start_time
            if elapsed > self.READY_WAIT_TIME_SEC:
                print(f"[TRANSITION] WAITING -> ARMED. "
                      f"Player held ready for {elapsed:.1f}s.")
                self.near_ready_start_time = None
                return "ARMED"
        else:
            self.near_ready_start_time = None

        return "WAITING"

    # ------------------------------------------------------------------
    # ARMED → ACTIVE  or  ARMED → WAITING
    # ------------------------------------------------------------------

    def _check_armed(self, history: deque) -> str:
        frame = history[-1]
        now   = frame.timestamp

        in_band = False
        if frame.near_player_world is not None:
            _, wy   = frame.near_player_world
            dist_ft = abs(wy)
            in_band = wy < 0 and self.READY_MIN_DIST_FT <= dist_ft <= self.READY_MAX_DIST_FT

        self.armed_band_history.append((now, in_band))
        while (self.armed_band_history and
               now - self.armed_band_history[0][0] > self.ARMED_BAND_WINDOW_SEC):
            self.armed_band_history.popleft()

        if len(self.armed_band_history) > 1:
            total_time = self.armed_band_history[-1][0] - self.armed_band_history[0][0]
            if total_time > 1.0:
                time_out = sum(
                    self.armed_band_history[i + 1][0] - self.armed_band_history[i][0]
                    for i in range(len(self.armed_band_history) - 1)
                    if not self.armed_band_history[i][1]
                )
                out_ratio = time_out / total_time
                if out_ratio > self.ARMED_OUT_RATIO_THRESHOLD:
                    print(f"[TRANSITION] ARMED -> WAITING. "
                          f"Out of band {out_ratio:.0%} over {total_time:.1f}s.")
                    self._reset_armed_state()
                    return "WAITING"

        if not in_band or frame.near_player_box is None:
            return "ARMED"

        nx1, ny1, nx2, ny2 = frame.near_player_box

        trophy_score = getattr(frame, "trophy_score", 0.0) or 0.0
        if trophy_score > 0:
            self._trophy_scores.append((trophy_score, now))

        toss_score = self._update_toss_detection(frame, ny1, now)
        if toss_score > 0:
            self._toss_scores.append((toss_score, now))

        for buf in (self._trophy_scores, self._toss_scores):
            while buf and now - buf[0][1] > self.EVENT_WINDOW_SECONDS:
                buf.popleft()

        max_trophy  = max((s for s, _ in self._trophy_scores), default=0.0)
        max_toss    = max((s for s, _ in self._toss_scores),   default=0.0)
        serve_score = 0.2 * max_trophy + 0.8 * max_toss

        self.last_serve_scores = {
            "trophy_score": max_trophy,
            "toss_score":   max_toss,
            "serve_score":  serve_score,
        }

        if serve_score >= self.TRANSITION_SCORE_THRESHOLD:
            if self.toss_min_y_px is not None and self.toss_min_y_px >= ny1:
                print(f"[DEBUG] Toss height invalid: min_y={self.toss_min_y_px:.1f} "
                      f"must be < player_top={ny1}")
                self.toss_min_y_px = None
                return "ARMED"

            toss_h_str = (f"{self.toss_min_y_px:.1f}px (above {ny1})"
                          if self.toss_min_y_px is not None else "N/A")
            print(f"[TRANSITION] ARMED -> ACTIVE. "
                  f"Serve detected! Score: {serve_score:.2f}  "
                  f"Toss height: {toss_h_str}")
            self._reset_armed_state()
            self._init_active(now)
            return "ACTIVE"

        return "ARMED"

    def _update_toss_detection(self, frame, ny1: float, now: float) -> float:
        if not frame.toss_ball_candidates:
            self.last_toss_ball    = None
            self.toss_gap_frames  += 1
            if self.toss_gap_frames > 3:
                self.toss_consecutive_frames       = 0
                self.toss_ball_above_head_detected = False
            return 0.0

        best = max(frame.toss_ball_candidates, key=lambda x: x["conf"])
        bx1, by1, bx2, by2 = best["box"]
        cy = (by1 + by2) / 2.0

        is_moving_upward   = False
        is_ball_above_head = cy < ny1

        if self.last_toss_ball is not None:
            dy  = cy - self.last_toss_ball["y"]
            dtt = now - self.last_toss_ball["time"]
            if dy < 0 and dtt > 0:
                is_moving_upward = True

        if is_ball_above_head:
            if self.toss_min_y_px is None or cy < self.toss_min_y_px:
                self.toss_min_y_px = cy

        self.last_toss_ball = {"y": cy, "time": now}

        if is_moving_upward and is_ball_above_head:
            self.toss_gap_frames              = 0
            self.toss_consecutive_frames     += 1
            self.toss_ball_above_head_detected = True
        else:
            self.toss_gap_frames += 1
            if self.toss_gap_frames > 3:
                self.toss_consecutive_frames       = 0
                self.toss_ball_above_head_detected = False

        if not self.toss_ball_above_head_detected:
            return 0.0
        if self.toss_consecutive_frames >= 3:
            return 1.0
        if self.toss_consecutive_frames >= 2:
            return 0.7
        return 0.0

    # ------------------------------------------------------------------
    # ACTIVE → WAITING  (hybrid ball-trace / energy-bar)
    # ------------------------------------------------------------------

    def _check_active(self, history: deque) -> str:
        frame      = history[-1]
        now        = frame.timestamp
        candidates = frame.active_ball_candidates or []

        # ---- 1. Update player tracking buffers for energy computation ----
        self._update_player_tracking(frame)

        # ---- 2. Update ball history (speed-filtered) ----
        # For each candidate:
        #   a) Reject if inter-frame speed exceeds MAX_BALL_SPEED_FTS (physically impossible).
        #   b) Only add pixel centre to the visual trace if ball is actually moving
        #      (speed > BALL_DEAD_SPEED_FTS) — stationary detections are excluded from trace.
        #   c) Track whether any candidate this frame is actually moving (for step 3).
        any_moving = False
        for c in candidates:
            wx, wy = c.get("world_x", 0.0), c.get("world_y", 0.0)
            speed_fts = 0.0

            # Find the reference position from ~BALL_SPEED_WINDOW_SEC ago.
            # Iterate newest→oldest through history; take the first entry that
            # is both from a previous frame (t < now) and old enough to cover
            # the smoothing window.  If history is shorter than the window, use
            # whatever oldest entry is available — still better than one frame.
            ref = None
            for entry in reversed(self._active_ball_world_history):
                if entry[0] >= now:
                    continue        # same-frame entry — skip
                ref = entry         # always keep updating so we have a fallback
                if now - entry[0] >= self.BALL_SPEED_WINDOW_SEC:
                    break           # old enough — use this as the reference

            if ref is not None:
                ref_t, ref_wx, ref_wy = ref
                dt_ball = now - ref_t
                if dt_ball > 0:
                    speed_fts = math.hypot(wx - ref_wx, wy - ref_wy) / dt_ball
                    if speed_fts > self.MAX_BALL_SPEED_FTS:
                        continue    # implausible displacement — discard

            self._active_ball_world_history.append((now, wx, wy))

            if speed_fts > self.BALL_DEAD_SPEED_FTS:
                any_moving = True
                pc = c.get("pixel_center")
                if pc is not None:
                    self._ball_trace_pixels.append(pc)

        while (self._active_ball_world_history and
               now - self._active_ball_world_history[0][0] > self.BALL_TIMEOUT):
            self._active_ball_world_history.popleft()

        if candidates:
            self.last_ball_seen_time = now

        # ---- 3. Determine whether an active ball trace is present ----
        # Fast path: no candidates, or all candidates are below BALL_DEAD_SPEED_FTS this
        # frame → no active trace immediately, without waiting for DBSCAN to converge.
        # This ensures a ball sitting still (e.g. in the net) is never counted as a live
        # trace regardless of how long DBSCAN needs to classify the cluster.
        # Slow path: at least one candidate is moving → fall back to DBSCAN to confirm
        # it isn't part of a pre-existing stationary cluster.
        if not candidates or not any_moving:
            has_active_trace = False
        else:
            stationary_clusters = self._get_stationary_clusters()
            has_active_trace    = not self._is_all_balls_dead(stationary_clusters)

        # ---- 4. Update debug snapshot ----
        self.last_active_debug = {
            "time_since_trace":     now - self.last_active_trace_time,
            "has_active_trace":     has_active_trace,
            "energy_bar_mode":      self.energy_bar_mode,
            "point_energy":         self.point_energy,
            "ball_count":           len(candidates),
            "window_max_speed_fts": self._window_max_speed(),
        }

        # ---- 5a. Active trace present → point is alive ----
        if has_active_trace:
            self.last_active_trace_time = now
            if self.energy_bar_mode:
                print(f"[ACTIVE] Ball trace restored at t={now:.2f}s. "
                      f"Discarding energy bar (was {self.point_energy:.2f}).")
                self.energy_bar_mode = False
                self.point_energy    = 1.0
                self._energy_player_positions.clear()
                self._energy_player_boxes.clear()
                self._energy_gait_y_buffer.clear()
            return "ACTIVE"

        # ---- 5b. No active trace → energy bar mode ----
        if not self.energy_bar_mode:
            print(f"[ACTIVE] No ball trace. Entering energy bar mode "
                  f"(anchor={self.last_active_trace_time:.2f}s, now={now:.2f}s).")
            self.energy_bar_mode       = True
            self.energy_bar_start_time = self.last_active_trace_time
            self.point_energy          = 1.0

        # ---- 6. Compute and apply energy delta ----
        dt           = 1.0 / self.fps
        energy_delta, status = self._compute_energy_delta(frame, dt)
        self.point_energy = max(0.0, min(1.0, self.point_energy + energy_delta))

        self.last_active_debug.update({
            "energy_bar_mode":  self.energy_bar_mode,
            "point_energy":     self.point_energy,
            "energy_status":    status,
        })

        # ---- 7. Transition when energy reaches zero ----
        if self.point_energy <= 0.0:
            self.last_transition_time = self.energy_bar_start_time
            elapsed = now - self.active_start_time
            print(f"\n[TRANSITION] ACTIVE -> WAITING (Energy Depleted [{status}]). "
                  f"Lasted {elapsed:.1f}s. Rewind to t={self.energy_bar_start_time:.2f}s.")
            self._reset_active_state()
            return "WAITING"

        return "ACTIVE"

    # ------------------------------------------------------------------
    # Player tracking helpers for energy computation
    # ------------------------------------------------------------------

    def _update_player_tracking(self, frame) -> None:
        """Append near-player position (world space) and box (pixel space) to rolling buffers."""
        near_box   = frame.near_player_box
        near_world = frame.near_player_world
        if near_box is None or near_world is None:
            self._player_missing_frames += 1
            self._energy_gait_y_buffer.clear()
            return
        self._player_missing_frames = 0

        # World-space position: (world_x at box centre, world_y at box bottom)
        # near_player_world is already computed from (pixel_cx, pixel_y2) in anya_base.py.
        # Apply EMA to suppress perspective-foreshortening noise — the same pixel jitter
        # maps to much larger world distances near the net than at the baseline.
        wx, wy = near_world
        if self._smoothed_player_world is None:
            self._smoothed_player_world = (wx, wy)
        else:
            α = self.PLAYER_EMA_ALPHA
            self._smoothed_player_world = (
                α * wx + (1 - α) * self._smoothed_player_world[0],
                α * wy + (1 - α) * self._smoothed_player_world[1],
            )
        self._energy_player_positions.append(self._smoothed_player_world)

        # Pixel box retained for shape-change (swing) detection
        self._energy_player_boxes.append(near_box)

        # Gait: pixel-space feet y for oscillation detection
        self._energy_gait_y_buffer.append(float(near_box[3]))

    def _compute_energy_delta(self, frame, dt: float):
        """
        Return (energy_delta, status_label) for one frame.

        Priority (high → low):
          1. Player missing                → drain ENERGY_DECAY_MISSING
          2. Walking gait detected         → drain ENERGY_DECAY_WALKING
          3. Sprinting (high velocity)     → boost ENERGY_BOOST_SPRINT
          4. Swing / split-step (shape Δ) → boost ENERGY_BOOST_SWING
          5. Standing still               → drain ENERGY_DECAY_STILL
          6. Moving (neutral)             → tiny boost 0.1/s
        """
        if self._player_missing_frames > self.PLAYER_MISSING_GRACE_FRAMES:
            return -(self.ENERGY_DECAY_MISSING * dt), "MISSING"

        if self._detect_walking_gait():
            return -(self.ENERGY_DECAY_WALKING * dt), "WALKING"

        # Velocity in world-space ft/s, smoothed over VELOCITY_WINDOW_SIZE samples.
        # Each sample is ACTIVE_PLAYER_STRIDE frames apart, so elapsed time is:
        #   n_samples * ACTIVE_PLAYER_STRIDE / fps
        # This corrects for the player detection stride so the reported speed is
        # physically accurate rather than inflated by the subsampling rate.
        player_velocity_fts = 0.0
        if len(self._energy_player_positions) >= 5:
            old_p   = self._energy_player_positions[0]
            new_p   = self._energy_player_positions[-1]
            dist_ft = math.hypot(new_p[0] - old_p[0], new_p[1] - old_p[1])
            elapsed = len(self._energy_player_positions) * self.ACTIVE_PLAYER_STRIDE / self.fps
            player_velocity_fts = dist_ft / elapsed if elapsed > 0 else 0.0

        if player_velocity_fts > self.PLAYER_SPRINT_VELOCITY_FTS:
            return (self.ENERGY_BOOST_SPRINT * dt), f"SPRINTING {player_velocity_fts:.1f}ft/s"

        # Shape change normalised by box height (position-independent, pixel space)
        if len(self._energy_player_boxes) >= 5:
            old_b      = self._energy_player_boxes[0]
            new_b      = self._energy_player_boxes[-1]
            box_height = old_b[3] - old_b[1]
            if box_height > 0:
                dw = abs((new_b[2] - new_b[0]) - (old_b[2] - old_b[0]))
                dh = abs((new_b[3] - new_b[1]) - (old_b[3] - old_b[1]))
                if (dw + dh) / box_height > 0.35:
                    return (self.ENERGY_BOOST_SWING * dt), "SWING"

        if player_velocity_fts < self.PLAYER_STILL_VELOCITY_FTS:
            return -(self.ENERGY_DECAY_STILL * dt), f"STILL {player_velocity_fts:.1f}ft/s"
        return (0.1 * dt), f"MOVING {player_velocity_fts:.1f}ft/s"

    def _detect_walking_gait(self) -> bool:
        """
        Detect walking gait from oscillatory y-movement of player feet.
        Returns True if consistent with a walk cadence.
        """
        ys = list(self._energy_gait_y_buffer)
        n  = len(ys)
        if n < self.GAIT_BUFFER_FRAMES * 0.6:
            return False

        drift = abs(ys[-1] - ys[0])
        if drift < self.GAIT_MIN_DRIFT_PX:
            return False

        # Detrend and count direction reversals
        residuals = [
            ys[i] - (ys[0] + (ys[-1] - ys[0]) * (i / (n - 1)))
            for i in range(n)
        ]
        reversals      = 0
        prev_direction = 0
        for i in range(1, len(residuals)):
            delta = residuals[i] - residuals[i - 1]
            if abs(delta) < 0.5:
                continue
            direction = 1 if delta > 0 else -1
            if prev_direction != 0 and direction != prev_direction:
                reversals += 1
            prev_direction = direction

        return self.GAIT_MIN_REVERSALS <= reversals <= self.GAIT_MAX_REVERSALS

    # ------------------------------------------------------------------
    # Stationary-cluster detection (used to define "active trace")
    # ------------------------------------------------------------------

    def _get_stationary_clusters(self) -> List[Tuple[float, float]]:
        """Identify clusters that have stayed stationary for the timeout duration."""
        buf = self._active_ball_world_history
        if len(buf) < 5:
            return []

        if len(buf) == self._stationary_cache_len:
            return self._stationary_cache_result

        times = np.array([t for t, _, _ in buf])
        pts   = np.array([[wx, wy] for _, wx, wy in buf])

        if (times[-1] - times[0]) < (self.BALL_TIMEOUT - 0.1):
            self._stationary_cache_len    = len(buf)
            self._stationary_cache_result = []
            return []

        labels = DBSCAN(eps=self.BALL_DEAD_CLUSTER_EPS_FT, min_samples=3).fit_predict(pts)
        stationary = []
        for lbl in set(labels):
            if lbl == -1:
                continue
            mask    = labels == lbl
            c_pts   = pts[mask]
            c_times = times[mask]
            t_span  = c_times.max() - c_times.min()
            if t_span < (self.BALL_TIMEOUT - 0.5):
                continue
            diffs = c_pts[:, None, :] - c_pts[None, :, :]
            max_d = np.sqrt((diffs ** 2).sum(axis=2)).max()
            if (max_d / t_span) < self.BALL_DEAD_SPEED_FTS:
                stationary.append(tuple(np.mean(c_pts, axis=0)))

        self._stationary_cache_len    = len(buf)
        self._stationary_cache_result = stationary
        return stationary

    def _is_all_balls_dead(self, stationary_clusters) -> bool:
        """
        True if all detected ball positions belong to stationary clusters
        (i.e. no kinetic "trace" of a moving ball).
        """
        if not stationary_clusters:
            return False

        buf = self._active_ball_world_history
        pts = np.array([[wx, wy] for _, wx, wy in buf])

        kinetic_points = [
            p for p in pts
            if not any(
                math.hypot(p[0] - c[0], p[1] - c[1]) < self.BALL_DEAD_CLUSTER_EPS_FT
                for c in stationary_clusters
            )
        ]
        if len(kinetic_points) < 3:
            return True

        kp         = np.array(kinetic_points)
        trace_span = math.hypot(kp[:, 0].max() - kp[:, 0].min(),
                                kp[:, 1].max() - kp[:, 1].min())
        TRACE_THRESHOLD_FT = 8.0
        return trace_span <= TRACE_THRESHOLD_FT

    # ------------------------------------------------------------------
    # Speed helpers (used for debug snapshot)
    # ------------------------------------------------------------------

    def _last_ball_speed_fts(self) -> float:
        buf = self._active_ball_world_history
        if len(buf) < 2:
            return 0.0
        t1, x1, y1 = buf[-2]
        t2, x2, y2 = buf[-1]
        dt = t2 - t1
        if dt <= 0:
            return 0.0
        return math.hypot(x2 - x1, y2 - y1) / dt

    def _window_max_speed(self) -> float:
        buf = self._active_ball_world_history
        if len(buf) < 2:
            return 0.0
        t_span = buf[-1][0] - buf[0][0]
        if t_span <= 0:
            return 0.0
        pts   = np.array([[wx, wy] for _, wx, wy in buf])
        diffs = pts[:, None, :] - pts[None, :, :]
        max_d = np.sqrt((diffs ** 2).sum(axis=2)).max()
        return max_d / t_span

    # ------------------------------------------------------------------
    # Helpers — reset / init
    # ------------------------------------------------------------------

    def _post_active_next_state(self, near_pos, default_state: str) -> str:
        """
        On ACTIVE → WAITING, bypass WAITING if the player is already inside
        the ready zone — go straight to ARMED for the next point.
        """
        if near_pos is not None:
            _, wy   = near_pos
            dist_ft = abs(wy)
            if wy < 0 and self.READY_MIN_DIST_FT <= dist_ft <= self.READY_MAX_DIST_FT:
                print("[BYPASS] Player already at baseline. Jumping to ARMED.")
                self._reset_armed_state()
                return "ARMED"
        return default_state

    def _reset_armed_state(self) -> None:
        self.armed_band_history.clear()
        self.toss_consecutive_frames       = 0
        self.toss_gap_frames               = 0
        self.toss_ball_above_head_detected = False
        self.toss_min_y_px                 = None
        self.last_toss_ball                = None
        self._trophy_scores.clear()
        self._toss_scores.clear()
        self.last_serve_scores = {
            "trophy_score": 0.0,
            "toss_score":   0.0,
            "serve_score":  0.0,
        }

    def _reset_active_state(self) -> None:
        self._active_ball_world_history.clear()
        self.last_ball_seen_time      = 0.0
        self.active_start_time        = 0.0
        self.last_active_trace_time   = 0.0
        self._stationary_cache_len    = -1
        self._stationary_cache_result = []
        self._player_missing_frames = 0
        # Energy bar
        self.energy_bar_mode          = False
        self.energy_bar_start_time    = 0.0
        self.point_energy             = 1.0
        self._energy_player_positions.clear()
        self._energy_player_boxes.clear()
        self._energy_gait_y_buffer.clear()
        self._ball_trace_pixels.clear()
        self._smoothed_player_world = None

    def _init_active(self, now: float) -> None:
        self._reset_active_state()
        self.active_start_time      = now
        self.last_ball_seen_time    = now
        self.last_active_trace_time = now
        self.last_transition_time   = None
