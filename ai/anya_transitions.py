"""
anya_transitions.py
===================
State machine logic. Consumes the rolling 5-second telemetry buffer
from anya_base.py to determine state transitions.

All transition decision logic is consolidated here. Detection (running YOLO
models, computing raw scores) is handled by AnyaTelemetryProvider in anya_base.py.
"""

from collections import deque
from typing import List, Optional, Tuple
import math

from src.ai.gait_analyzer import GaitAnalyzer


class TransitionEngine:
    def __init__(self, fps: float):
        self.fps = fps

        # ------------------------------------------------------------------
        # Thresholds
        # ------------------------------------------------------------------
        # Ready zone (ft; wy < 0 means behind near baseline)
        self.READY_MIN_DIST_FT        = -0.5
        self.READY_MAX_DIST_FT        = 3.5
        self.READY_WAIT_TIME_SEC      = 0.4

        # Armed band guard
        self.ARMED_BAND_WINDOW_SEC     = 2.0
        self.ARMED_OUT_RATIO_THRESHOLD = 0.25

        # Serve detection
        self.TRANSITION_SCORE_THRESHOLD = 0.55
        self.EVENT_WINDOW_SECONDS       = 1.2

        # Energy — ball
        self.ENERGY_BOOST_BALL_FAST        = 1.0
        self.ENERGY_DECAY_BALL_ROLLING     = 0.3
        self.ENERGY_DECAY_BALL_OCCLUDED    = 0.2
        self.ENERGY_DECAY_BALL_DEAD        = 0.2
        self.ENERGY_DECAY_BALL_ACTION_ZONE = 0.03
        self.MIN_BALL_VELOCITY_FT_SEC      = 15.0

        # Energy — player
        self.ENERGY_BOOST_PLAYER_ACTION       = 1.0
        self.ENERGY_BOOST_PLAYER_SPRINT       = 1.0
        self.ENERGY_DECAY_PLAYER_WALK         = 0.2
        self.ENERGY_DECAY_PLAYER_WALKING_GAIT = 0.0
        self.ENERGY_DECAY_PLAYER_MISSING      = 0.3
        self.SHAPE_CHANGE_THRESHOLD_PX        = 75.0
        self.PLAYER_WALK_VELOCITY_THRESHOLD   = 2.0
        self.PLAYER_SPRINT_VELOCITY_THRESHOLD = 6.0

        # Energy — player center variance (world-space, 3-second window)
        self.PLAYER_VAR_WINDOW_SEC      = 3.0
        self.PLAYER_VAR_LOW_FT2         = 2.0   # below → low variance → decay
        self.PLAYER_VAR_HIGH_FT2        = 4.0   # above → high variance → boost
        self.ENERGY_BOOST_PLAYER_VARIANCE  = 0.1   # boost rate (units/s) at max variance
        self.ENERGY_DECAY_PLAYER_VARIANCE  = 0.1   # decay rate (units/s) at min variance

        # Action zone / net proximity
        self.ACTION_ZONE_MAX_Y_FT         = 0.0
        self.NET_PROXIMITY_COURT_DEPTH_FT = 39.0
        self.NET_PROXIMITY_PLAYER_SCALE   = 3.0
        self.NET_PROXIMITY_BALL_SCALE     = 0.0

        # Gait detection (kinematic — MediaPipe knee-angle analysis)
        # self._gait_analyzer = GaitAnalyzer(fps=fps)  # DISABLED

        # Ball position tracking
        self.BALL_POSITION_BUFFER_SIZE = 15
        self.VELOCITY_MEDIAN_WINDOW    = 5
        self.VELOCITY_WINDOW_SIZE      = 20
        self.MAX_BALL_SPEED_FT_SEC     = 180.0

        # Ball-lost absolute timeouts
        self.ABSOLUTE_BALL_LOST_TIMEOUT_ACTIVE = 20.0
        self.ABSOLUTE_BALL_LOST_TIMEOUT_IDLE   = 6.0

        # Ghost-state / emergency ACTIVE → ARMED override
        self.GHOST_ENERGY_THRESHOLD = 0.5
        self.GHOST_TROPHY_THRESHOLD = 0.6

        # ------------------------------------------------------------------
        # Persistent state — WAITING
        # ------------------------------------------------------------------
        self.near_ready_start_time: Optional[float] = None

        # ------------------------------------------------------------------
        # Persistent state — ARMED
        # ------------------------------------------------------------------
        self.armed_band_history: deque = deque()

        # Toss consecutive-frame hysteresis
        self.toss_consecutive_frames:       int            = 0
        self.toss_gap_frames:               int            = 0
        self.toss_ball_above_head_detected: bool           = False
        self.toss_min_y_px:                 Optional[float] = None
        self.last_toss_ball:                Optional[dict]  = None  # {"y", "time"}

        # Rolling score windows (score, timestamp)
        self._trophy_scores: deque = deque()
        self._toss_scores:   deque = deque()

        # ------------------------------------------------------------------
        # Persistent state — ACTIVE
        # ------------------------------------------------------------------
        self.point_energy:       float = 1.0
        self.active_start_time:  float = 0.0
        self.last_ball_seen_time: float = 0.0
        self.energy_lock_until: float = 0.0  # Time until which energy is locked at 1.0

        self.active_ball_positions: deque = deque(maxlen=self.BALL_POSITION_BUFFER_SIZE)
        self.near_player_positions: deque = deque(maxlen=self.VELOCITY_WINDOW_SIZE)
        self.near_player_boxes:     deque = deque(maxlen=5)

        # Rolling 3-second buffer of (timestamp, wx, wy) for variance calculation
        self.near_player_var_buffer: deque = deque()

        # Debug: track last frame's energy contributions
        self.last_energy_deltas = {
            # Ball contributions (individual components)
            "ball_fast_delta": 0.0,
            "ball_rolling_delta": 0.0,
            "ball_occluded_delta": 0.0,
            "ball_dead_delta": 0.0,
            "ball_action_zone_delta": 0.0,
            "ball_scale": 1.0,
            # Individual player contributions
            "sprint_delta": 0.0,
            "action_delta": 0.0,
            "walk_delta": 0.0,
            "gait_delta": 0.0,
            "missing_delta": 0.0,
            "variance_delta": 0.0,
            "player_scale": 1.0,
        }

        # ------------------------------------------------------------------
        # Persistent state — ARMED
        # ------------------------------------------------------------------
        # Debug: track last serve scores
        self.last_serve_scores = {
            "trophy_score": 0.0,
            "toss_score": 0.0,
            "serve_score": 0.0,
        }

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def evaluate_transitions(self, history: deque, current_state: str) -> str:
        if not history:
            return current_state

        if current_state == "WAITING":
            return self._check_waiting(history)
        elif current_state == "ARMED":
            return self._check_armed(history)
        elif current_state == "ACTIVE":
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

        # ---- Band tracking (guards ARMED → WAITING) ----
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

        # ---- Accumulate trophy score ----
        trophy_score = getattr(frame, 'trophy_score', 0.0) or 0.0
        if trophy_score > 0:
            self._trophy_scores.append((trophy_score, now))

        # ---- Toss detection ----
        toss_score = self._update_toss_detection(frame, ny1, now)
        if toss_score > 0:
            self._toss_scores.append((toss_score, now))

        # Prune stale scores
        for buf in (self._trophy_scores, self._toss_scores):
            while buf and now - buf[0][1] > self.EVENT_WINDOW_SECONDS:
                buf.popleft()

        max_trophy  = max((s for s, _ in self._trophy_scores), default=0.0)
        max_toss    = max((s for s, _ in self._toss_scores),   default=0.0)
        serve_score = 0.2 * max_trophy + 0.8 * max_toss

        # Track serve scores for debug visualization
        self.last_serve_scores = {
            "trophy_score": max_trophy,
            "toss_score": max_toss,
            "serve_score": serve_score,
        }

        if serve_score >= self.TRANSITION_SCORE_THRESHOLD:
            # Validate toss reached above player's head
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
        """
        Update consecutive-frame toss tracking and return a score in [0, 1].
        Requires is_moving_upward AND is_ball_above_head simultaneously.
        """
        if not frame.toss_ball_candidates:
            self.last_toss_ball = None
            self.toss_gap_frames += 1
            if self.toss_gap_frames > 3:
                self.toss_consecutive_frames = 0
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
            self.toss_gap_frames = 0
            self.toss_consecutive_frames += 1
            self.toss_ball_above_head_detected = True
        else:
            self.toss_gap_frames += 1
            if self.toss_gap_frames > 3:
                self.toss_consecutive_frames = 0
                self.toss_ball_above_head_detected = False

        if not self.toss_ball_above_head_detected:
            return 0.0
        if self.toss_consecutive_frames >= 3:
            return 1.0
        if self.toss_consecutive_frames >= 2:
            return 0.7
        return 0.0

    # ------------------------------------------------------------------
    # ACTIVE → WAITING  or  ACTIVE → ARMED (emergency override)
    # ------------------------------------------------------------------

    def _check_active(self, history: deque) -> str:
        frame = history[-1]
        now   = frame.timestamp
        dt    = 1.0 / self.fps

        near_pos = frame.near_player_world
        near_box = frame.near_player_box

        # ---- Update player tracking ----
        player_velocity = 0.0
        shape_change    = 0.0

        if near_pos:
            self.near_player_positions.append(near_pos)
        if near_box:
            self.near_player_boxes.append(near_box)

        if len(self.near_player_positions) >= 5:
            old_p = self.near_player_positions[0]
            new_p = self.near_player_positions[-1]
            player_velocity = math.hypot(
                new_p[0] - old_p[0], new_p[1] - old_p[1]
            ) / len(self.near_player_positions)

        if len(self.near_player_boxes) >= 5:
            ob, nb = self.near_player_boxes[0], self.near_player_boxes[-1]
            shape_change = (abs((nb[2] - nb[0]) - (ob[2] - ob[0])) +
                            abs((nb[3] - nb[1]) - (ob[3] - ob[1])))

        # ---- Update ball tracking ----
        best_ball = self._select_best_active_ball(frame.active_ball_candidates or [])
        if best_ball:
            proposed = (best_ball["world_x"], best_ball["world_y"], now)
            if self._validate_ball_jump(proposed):
                self.active_ball_positions.append(proposed)
                self.last_ball_seen_time = now
            else:
                best_ball = None

        time_since_ball = now - self.last_ball_seen_time
        ball_velocity   = self._compute_stable_velocity()

        # ---- Action zone / net proximity ----
        player_is_active      = (near_pos is not None and
                                 player_velocity >= self.PLAYER_WALK_VELOCITY_THRESHOLD)
        player_in_action_zone = False
        net_proximity_factor  = 0.0
        if near_pos:
            wy = near_pos[1]
            player_in_action_zone = wy > self.ACTION_ZONE_MAX_Y_FT
            net_proximity_factor  = max(0.0, min(1.0,
                wy / self.NET_PROXIMITY_COURT_DEPTH_FT))

        # ---- Energy deltas ----
        ball_delta   = 0.0
        player_delta = 0.0

        # Track individual ball components for debug
        ball_fast_delta = 0.0
        ball_rolling_delta = 0.0
        ball_occluded_delta = 0.0
        ball_dead_delta = 0.0
        ball_action_zone_delta = 0.0

        if best_ball and ball_velocity > self.MIN_BALL_VELOCITY_FT_SEC:
            ball_fast_delta = self.ENERGY_BOOST_BALL_FAST * dt
            ball_delta += ball_fast_delta
        elif best_ball:
            ball_rolling_delta = -self.ENERGY_DECAY_BALL_ROLLING * dt
            ball_delta += ball_rolling_delta
        elif time_since_ball > 0.25:
            if player_in_action_zone:
                ball_action_zone_delta = -self.ENERGY_DECAY_BALL_ACTION_ZONE * dt
                ball_delta += ball_action_zone_delta
            elif player_is_active:
                ball_occluded_delta = -self.ENERGY_DECAY_BALL_OCCLUDED * dt
                ball_delta += ball_occluded_delta
            else:
                ball_dead_delta = -self.ENERGY_DECAY_BALL_DEAD * dt
                ball_delta += ball_dead_delta

        # walking_gait = (self._gait_analyzer.update(frame.player_crop)
        #                 if frame.player_crop is not None else False)  # DISABLED
        walking_gait = False

        # Track individual player contributions for debug
        sprint_delta = 0.0
        action_delta = 0.0
        walk_delta = 0.0
        gait_delta = 0.0
        missing_delta = 0.0

        if not near_pos:
            missing_delta = -self.ENERGY_DECAY_PLAYER_MISSING * dt
            player_delta -= self.ENERGY_DECAY_PLAYER_MISSING * dt
        elif player_velocity > self.PLAYER_SPRINT_VELOCITY_THRESHOLD:
            sprint_delta = self.ENERGY_BOOST_PLAYER_SPRINT * dt
            player_delta += self.ENERGY_BOOST_PLAYER_SPRINT * dt
        elif shape_change > self.SHAPE_CHANGE_THRESHOLD_PX:
            action_delta = self.ENERGY_BOOST_PLAYER_ACTION * dt
            player_delta += self.ENERGY_BOOST_PLAYER_ACTION * dt
        elif walking_gait:
            gait_delta = -self.ENERGY_DECAY_PLAYER_WALKING_GAIT * dt
            player_delta -= self.ENERGY_DECAY_PLAYER_WALKING_GAIT * dt
            print('PLAYER IS WALKING BY OUR GAIR DETECTOR')
        elif player_velocity < self.PLAYER_WALK_VELOCITY_THRESHOLD:
            walk_delta = -self.ENERGY_DECAY_PLAYER_WALK * dt
            player_delta -= self.ENERGY_DECAY_PLAYER_WALK * dt

        # ---- Player center variance contribution ----
        if near_pos:
            self.near_player_var_buffer.append((now, near_pos[0], near_pos[1]))
        while (self.near_player_var_buffer and
               now - self.near_player_var_buffer[0][0] > self.PLAYER_VAR_WINDOW_SEC):
            self.near_player_var_buffer.popleft()

        variance_delta = self._compute_variance_delta(dt)
        player_delta += variance_delta

        player_scale = 1.0 + net_proximity_factor * (self.NET_PROXIMITY_PLAYER_SCALE - 1.0)
        ball_scale   = 1.0 - net_proximity_factor * (1.0 - self.NET_PROXIMITY_BALL_SCALE)

        # Track energy deltas for debug visualization
        self.last_energy_deltas = {
            "ball_fast_delta": ball_fast_delta,
            "ball_rolling_delta": ball_rolling_delta,
            "ball_occluded_delta": ball_occluded_delta,
            "ball_dead_delta": ball_dead_delta,
            "ball_action_zone_delta": ball_action_zone_delta,
            "ball_scale": ball_scale,
            "sprint_delta": sprint_delta,
            "action_delta": action_delta,
            "walk_delta": walk_delta,
            "gait_delta": gait_delta,
            "missing_delta": missing_delta,
            "variance_delta": variance_delta,
            "player_scale": player_scale,
        }

        # Apply energy lock: hold at 1.0 for 1.5 seconds after serve detection
        if now < self.energy_lock_until:
            self.point_energy = 1.0
        else:
            self.point_energy = max(0.0, min(1.0,
                self.point_energy + player_delta * player_scale + ball_delta * ball_scale))

        # ---- Primary transition: energy depleted or ball lost ----
        timeout    = (self.ABSOLUTE_BALL_LOST_TIMEOUT_ACTIVE
                      if (player_in_action_zone or player_is_active)
                      else self.ABSOLUTE_BALL_LOST_TIMEOUT_IDLE)
        force_kill = time_since_ball > timeout

        if self.point_energy <= 0.0 or force_kill:
            zone   = ("in_court" if player_in_action_zone
                      else ("active" if player_is_active else "idle"))
            reason = ("Energy Depleted" if not force_kill
                      else f"Ball Missing > {timeout:.1f}s (player {zone})")
            elapsed = now - self.active_start_time
            print(f"\n[TRANSITION] ACTIVE -> WAITING. Point dead ({reason}). "
                  f"Lasted {elapsed:.1f}s. Energy: {self.point_energy:.3f}")
            self._reset_active_state()

            # Bypass WAITING if player is already at the baseline
            if near_pos is not None:
                _, wy = near_pos
                if wy < 0 and self.READY_MIN_DIST_FT <= abs(wy) <= self.READY_MAX_DIST_FT:
                    print("[BYPASS] Player already at baseline. Jumping to ARMED.")
                    self._reset_armed_state()
                    return "ARMED"

            return "WAITING"

        # ---- Ghost-state / emergency ACTIVE → ARMED override ----
        trophy_score = getattr(frame, 'trophy_score', 0.0) or 0.0
        if (self.point_energy < self.GHOST_ENERGY_THRESHOLD and
                near_pos is not None and
                trophy_score > self.GHOST_TROPHY_THRESHOLD):
            _, wy   = near_pos
            dist_ft = abs(wy)
            if (wy < 0 and
                    self.READY_MIN_DIST_FT <= dist_ft <= self.READY_MAX_DIST_FT and
                    player_velocity < self.PLAYER_WALK_VELOCITY_THRESHOLD):
                print(f"\n[EMERGENCY OVERRIDE] ACTIVE -> ARMED. "
                      f"Pose: {trophy_score:.2f}")
                self._reset_active_state()
                self._reset_armed_state()
                self._trophy_scores.append((trophy_score, now))
                return "ARMED"

        return "ACTIVE"

    # ------------------------------------------------------------------
    # Ball selection / velocity helpers
    # ------------------------------------------------------------------

    def _select_best_active_ball(self, candidates: List[dict]) -> Optional[dict]:
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        scored = []
        for c in candidates:
            wx, wy = c.get("world_x", 0.0), c.get("world_y", 0.0)
            score  = c["conf"] * 30.0
            if self.active_ball_positions:
                last  = self.active_ball_positions[-1]
                dist  = math.hypot(wx - last[0], wy - last[1])
                score += max(0.0, 50.0 - dist) * 2.0
            scored.append((score, c))
        return max(scored, key=lambda x: x[0])[1]

    def _validate_ball_jump(self, new_pos: Tuple) -> bool:
        if not self.active_ball_positions:
            return True
        last = self.active_ball_positions[-1]
        dist = math.hypot(new_pos[0] - last[0], new_pos[1] - last[1])
        dt   = new_pos[2] - last[2]
        if dt <= 0:
            return dist < 5.0
        return dist / dt <= self.MAX_BALL_SPEED_FT_SEC

    def _compute_stable_velocity(self) -> float:
        n = len(self.active_ball_positions)
        if n < 2:
            return 0.0
        window   = min(self.VELOCITY_MEDIAN_WINDOW, n - 1)
        pairwise = []
        for i in range(n - window, n):
            prev, curr = self.active_ball_positions[i - 1], self.active_ball_positions[i]
            dt = curr[2] - prev[2]
            if dt > 0:
                pairwise.append(
                    math.hypot(curr[0] - prev[0], curr[1] - prev[1]) / dt)
        if not pairwise:
            return 0.0
        pairwise.sort()
        mid = len(pairwise) // 2
        return ((pairwise[mid - 1] + pairwise[mid]) / 2.0
                if len(pairwise) % 2 == 0 else pairwise[mid])

    def _compute_variance_delta(self, dt: float) -> float:
        """
        Return an energy delta based on the variance of the near player's
        world-space position over the last PLAYER_VAR_WINDOW_SEC seconds.

        High variance  → positive delta (boost, up to ENERGY_BOOST_PLAYER_VARIANCE * dt)
        Low variance   → negative delta (decay, down to -ENERGY_DECAY_PLAYER_VARIANCE * dt)
        Average variance → 0
        """
        n = len(self.near_player_var_buffer)
        if n < 2:
            return 0.0

        xs = [e[1] for e in self.near_player_var_buffer]
        ys = [e[2] for e in self.near_player_var_buffer]
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        variance = sum((x - mean_x) ** 2 + (y - mean_y) ** 2
                       for x, y in zip(xs, ys)) / n

        low  = self.PLAYER_VAR_LOW_FT2
        high = self.PLAYER_VAR_HIGH_FT2

        if variance >= high:
            return self.ENERGY_BOOST_PLAYER_VARIANCE * dt
        elif variance <= low:
            return -self.ENERGY_DECAY_PLAYER_VARIANCE * dt
        else:
            # Linear interpolation through zero between low and high
            t = (variance - low) / (high - low)  # 0.0 at low, 1.0 at high
            if t < 0.5:
                return -self.ENERGY_DECAY_PLAYER_VARIANCE * dt * (1.0 - 2.0 * t)
            else:
                return self.ENERGY_BOOST_PLAYER_VARIANCE * dt * (2.0 * t - 1.0)

    # ------------------------------------------------------------------
    # Internal reset / init helpers
    # ------------------------------------------------------------------

    def _reset_armed_state(self):
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
            "toss_score": 0.0,
            "serve_score": 0.0,
        }

    def _reset_active_state(self):
        self.point_energy = 1.0
        self.active_ball_positions.clear()
        self.near_player_positions.clear()
        self.near_player_boxes.clear()
        self.near_player_var_buffer.clear()
        # self._gait_analyzer.reset()  # DISABLED

    def _init_active(self, now: float):
        """Reset and initialise ACTIVE-state trackers at the start of a new point."""
        self._reset_active_state()
        self.active_start_time   = now
        self.last_ball_seen_time = now
        self.energy_lock_until   = now + 1.5  # Lock energy at 1.0 for 1.5 seconds after serve
