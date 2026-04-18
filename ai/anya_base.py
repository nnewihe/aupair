"""
anya_base.py
=============
Core telemetry provider. Handles homography, exclusion zones, and runs the 
necessary detectors (YOLO / MediaPipe) based on the current state.
Maintains a 5-second rolling buffer of telemetry data.
"""

import cv2
import numpy as np
from ultralytics import YOLO
# import mediapipe as mp
# Instead of mediapipe.python..., use the standard solutions path
# Instead of from mediapipe.solutions import pose
# import mediapipe.python.solutions.pose as mp_pose
# from mediapipe.solutions import drawing_utils as mp_drawing
import json
import os
import random
import math
from dataclasses import dataclass
from typing import List, Optional, Tuple, Any
from sklearn.cluster import DBSCAN
from src.ai.utilities import (BoxSmoother, Config, _is_in_exclusion_zone, init_court,
                               create_auto_exclusion_zones, get_exclusion_zones_from_frames)
from collections import deque

@dataclass
class TelemetryFrame:
    frame_id: int
    timestamp: float
    state: str
    near_player_box: Optional[Tuple[int, int, int, int]] = None
    near_player_world: Optional[Tuple[float, float]] = None
    toss_ball_candidates: List[dict] = None
    active_ball_candidates: List[dict] = None
    trophy_score: float = 0.0          # Probability of trophy/serve pose (ARMED state)
    pose_landmarks: Any = None         # MediaPipe results (future use)
    player_crop: Any = None            # BGR crop of near player (ACTIVE state, for GaitAnalyzer)
    player_crop_rect: Any = None       # (cx1, cy1, cx2, cy2) frame coords of player_crop
    z_box: Optional[Tuple[int, int, int, int]] = None  # Zone box for ARMED toss detection (x1, y1, x2, y2)


class AnyaTelemetryProvider:
    def __init__(self, video_path: str):
        self.video_path = video_path
        self._init_video_props()

        # Models
        self.player_model = YOLO("yolo26n.pt")
        self.ball_model   = YOLO("weights/ball/weights/best.pt")
        self.trophy_model = YOLO(Config.DEFAULT_NEAR_TROPHY_MODEL_PATH)

        # 1. Initialize Court Geometry (at 960x540 resolution)
        self.court_vertices, self.frame_shape = init_court(
            self.video_path,
            analysis_size=(960, 540)
        )
        
        # 2. Compute Homography
        self.H = self._compute_homography()

        # 3. Compute the active-zone polygon from court vertices (used in ACTIVE state)
        self.active_zone_polygon = self._compute_active_zone_polygon()

        # 4. Compute static exclusion zones from full video scan (one-time at startup)
        print("\n[INFO] Scanning video for static exclusion zones...")
        try:
            self.static_exclusion_zones = create_auto_exclusion_zones(
                self.video_path, self.ball_model,
                num_frames=20,
                conf=0.05,
                padding=5,
                ball_class_index=Config.DEFAULT_BALL_CLASS_INDEX,
                analysis_size=(960, 540),
            )
            print(f"[INFO] Found {len(self.static_exclusion_zones)} static exclusion zone(s)")
        except Exception as e:
            print(f"[WARN] Could not compute static exclusion zones: {e}")
            self.static_exclusion_zones = []

        # Dynamic exclusion zones — recomputed on each ARMED entry
        self.dynamic_exclusion_zones: List = []

        # ------------------------------------------------------------------
        # Dynamic exclusion zone state
        # ------------------------------------------------------------------
        self._armed_frame_buffer: List = []
        self._armed_entry_time: Optional[float] = None
        self._armed_collection_done: bool = False

        self.ARMED_DYNAMIC_COLLECTION_SEC = 0.5  # collect for 0.5s after ARMED entry
        self.ARMED_DYNAMIC_SAMPLE_FRAMES = 5     # sample this many frames from buffer

        # State & Buffer
        self.current_state = "WAITING"
        self.frame_counter = 0
        buffer_size = int(self.fps * Config.TELEMETRY_BUFFER_SECONDS)
        self.telemetry_history = deque(maxlen=buffer_size)
        
        
        # MediaPipe Pose for ACTIVE state
        """
        self.mp_pose = mp_pose
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1, # 0 might be needed for Pi 5 if dropping frames
            enable_segmentation=False,
            min_detection_confidence=0.5
        )
        """

    def _init_video_props(self):
        cap = cv2.VideoCapture(self.video_path)
        self.fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        # Frames are resampled to 960x540 in run_anya.py
        self.width = 960
        self.height = 540
        cap.release()

    @property
    def exclusion_zones(self) -> List:
        """Combined static + dynamic exclusion zones for filtering."""
        return self.static_exclusion_zones + self.dynamic_exclusion_zones

    def _compute_active_zone_polygon(self) -> np.ndarray:
        """
        Build a 6-vertex pixel-space polygon that defines where ball detections
        are accepted in the ACTIVE phase.

        Vertex order (clockwise from near-left):
          BL  →  BR  →  BR-150px  →  TR-100px  →  TL-100px  →  BL-150px

        Where:
          BL, BR = near baseline / doubles-alley corners  (first two court vertices)
          TR, TL = far  baseline / doubles-alley corners  (last two court vertices)
          -Npx   = shifted N pixels upward in image space (lower y value)
        """
        BL, BR, TR, TL = self.court_vertices
        pts = np.array([
            [BL[0],       BL[1]      ],   # near-left  baseline
            [BR[0],       BR[1]      ],   # near-right baseline
            [BR[0],       BR[1] - 150],   # near-right +150px up
            [TR[0],       TR[1] - 200],   # far-right  +200px up
            [TL[0],       TL[1] - 200],   # far-left   +200px up
            [BL[0],       BL[1] - 150],   # near-left  +150px up
        ], dtype=np.int32)
        return pts

    def _is_in_active_zone(self, cx: float, cy: float) -> bool:
        """Return True if (cx, cy) lies inside or on the active-zone polygon."""
        return cv2.pointPolygonTest(
            self.active_zone_polygon, (float(cx), float(cy)), False
        ) >= 0

    def _stub_init_court(self):
        # Stub for the interactive init_court function
        return [(0,0), (100,0), (100,100), (0,100)], (1080, 1920, 3)

    def _compute_homography(self):
        BL, BR, TR, TL = self.court_vertices
        dst_pts = np.array([
            [0, 0], [Config.COURT_WIDTH_FT, 0],
            [Config.COURT_WIDTH_FT, Config.COURT_LENGTH_FT], [0, Config.COURT_LENGTH_FT],
        ], dtype=np.float32)
        src_pts = np.array([BL, BR, TR, TL], dtype=np.float32)
        H, _ = cv2.findHomography(src_pts, dst_pts)
        return H

    def get_world_pos(self, px_x, px_y):
        if self.H is None: return 0.0, 0.0
        pt_px = np.array([[[px_x, px_y]]], dtype=np.float32)
        pt_world = cv2.perspectiveTransform(pt_px, self.H)
        return pt_world[0][0][0], pt_world[0][0][1]

    def _is_in_player_box(self, ball_cx, ball_cy, player_box, padding=15):
        """Check if ball center is within player bounding box + padding."""
        if player_box is None:
            return False
        x1, y1, x2, y2 = player_box
        return (x1 - padding <= ball_cx <= x2 + padding and
                y1 - padding <= ball_cy <= y2 + padding)

    def _create_z_box(self, player_box):
        """
        Create zone box for ARMED phase toss detection.
        Bottom line bisects player box vertically (at player center Y).
        Width 2x player width, height 1.5x player height.
        """
        if player_box is None:
            return None
        x1, y1, x2, y2 = player_box
        player_width = x2 - x1
        player_height = y2 - y1
        player_cx = (x1 + x2) / 2.0
        player_cy = (y1 + y2) / 2.0

        z_width = player_width * 2.0
        z_height = player_height * 1.5

        # Bottom of z_box at player center Y (bisects vertically)
        z_x1 = player_cx - z_width / 2.0
        z_x2 = player_cx + z_width / 2.0
        z_y2 = player_cy
        z_y1 = z_y2 - z_height

        # Cap at top of frame
        z_y1 = max(0, z_y1)

        return (int(z_x1), int(z_y1), int(z_x2), int(z_y2))

    def _is_in_z_box(self, ball_cx, ball_cy, z_box):
        """Check if ball center is within z_box."""
        if z_box is None:
            return False
        x1, y1, x2, y2 = z_box
        return x1 <= ball_cx <= x2 and y1 <= ball_cy <= y2

    def _track_near_player(self, frame):
        results = self.player_model(frame, verbose=False, conf=0.5, imgsz=Config.PLAYER_IMGSZ)
        best_box, best_world = None, None
        min_dist = float('inf')

        if results and results[0].boxes:
            for b in results[0].boxes:
                if int(b.cls[0]) == Config.DEFAULT_PLAYER_CLASS_INDEX:
                    x1, y1, x2, y2 = map(int, b.xyxy[0].tolist())
                    cx, y_feet = (x1 + x2) / 2.0, y2
                    wx, wy = self.get_world_pos(cx, y_feet)
                    
                    # Assuming camera is on back fence, player is near baseline (y <= 0)
                    dist_to_baseline = abs(wy) 
                    if dist_to_baseline < min_dist:
                        min_dist = dist_to_baseline
                        best_box = (x1, y1, x2, y2)
                        best_world = (wx, wy)
                        
        return best_box, best_world

    def process_frame(self, frame) -> TelemetryFrame:
        self.frame_counter += 1
        timestamp = self.frame_counter / self.fps

        telemetry = TelemetryFrame(
            frame_id=self.frame_counter,
            timestamp=timestamp,
            state=self.current_state,
            toss_ball_candidates=[],
            active_ball_candidates=[]
        )

        # 1. ALWAYS track near side player
        p_box, p_world = self._track_near_player(frame)
        telemetry.near_player_box = p_box
        telemetry.near_player_world = p_world

        # 2. ARMED State — buffer frames for dynamic exclusion zone computation (0-0.5s window)
        if self.current_state == "ARMED":
            now_t = self.frame_counter / self.fps
            if (not self._armed_collection_done
                    and self._armed_entry_time is not None):
                elapsed = now_t - self._armed_entry_time
                if elapsed <= self.ARMED_DYNAMIC_COLLECTION_SEC:
                    # Still inside the 0.5-second collection window — store frame
                    self._armed_frame_buffer.append(frame.copy())
                elif len(self._armed_frame_buffer) >= 1:
                    # Collection window closed — compute dynamic zones from sampled frames
                    # using same DBSCAN logic as static zones
                    self.dynamic_exclusion_zones = get_exclusion_zones_from_frames(
                        self._armed_frame_buffer,
                        self.ball_model,
                        sample_size=self.ARMED_DYNAMIC_SAMPLE_FRAMES,
                        conf=0.10,
                        eps=5,
                        min_samples=15,
                        padding=5,
                        ball_class_index=Config.DEFAULT_BALL_CLASS_INDEX,
                    )
                    self._armed_collection_done = True
                    self._armed_frame_buffer    = []  # free memory
                    print(f"[INFO] Dynamic exclusion zones: {len(self.dynamic_exclusion_zones)} zone(s)")

        # 2b. ARMED State Detectors
        if self.current_state == "ARMED" and p_box:
            # Create zone box for toss detection
            z_box = self._create_z_box(p_box)
            telemetry.z_box = z_box

            nx1, ny1, nx2, ny2 = p_box
            pw, ph = nx2 - nx1, ny2 - ny1
            fh, fw = frame.shape[:2]

            # Trophy pose classification
            pad_x = int(pw * Config.DEFAULT_TROPHY_PAD)
            pad_y = int(ph * Config.DEFAULT_TROPHY_PAD)
            tx1 = max(0, nx1 - pad_x); ty1 = max(0, ny1 - pad_y)
            tx2 = min(fw, nx2 + pad_x); ty2 = min(fh, ny2 + pad_y)
            trophy_crop = frame[ty1:ty2, tx1:tx2]
            if trophy_crop.size > 0:
                tr = self.trophy_model(trophy_crop, verbose=False, imgsz=Config.TROPHY_IMGSZ)
                if tr and hasattr(tr[0], "probs") and tr[0].probs is not None:
                    idx = Config.DEFAULT_NEAR_TROPHY_CLASS_INDEX
                    if idx < len(tr[0].probs.data):
                        telemetry.trophy_score = float(tr[0].probs.data[idx])

            # Toss ball detection — ROI above player box
            rx1 = max(0,  int(nx1 - pw / 2))
            ry1 = max(0,  int(ny1 - ph))
            rx2 = min(fw, int(nx2 + pw / 2))
            ry2 = min(fh, int(ny1 + ph / 2))
            roi = frame[ry1:ry2, rx1:rx2]
            if roi.size > 0:
                ball_res = self.ball_model(roi, verbose=False, conf=0.10,
                                           imgsz=Config.TOSS_BALL_IMGSZ)
                if ball_res and ball_res[0].boxes:
                    for b in ball_res[0].boxes:
                        cx1, cy1, cx2, cy2 = b.xyxy[0].tolist()
                        ball_x = rx1 + cx1
                        ball_y = ry1 + cy1
                        ball_cx = (ball_x + rx1 + cx2) / 2.0
                        ball_cy = (ball_y + ry1 + cy2) / 2.0

                        # Filter: must be in z_box, not in exclusion zones, and not in player box
                        if (self._is_in_z_box(ball_cx, ball_cy, z_box) and
                            not _is_in_exclusion_zone(ball_cx, ball_cy, self.exclusion_zones) and
                            not self._is_in_player_box(ball_cx, ball_cy, p_box, padding=15)):
                            telemetry.toss_ball_candidates.append({
                                "box":  (ball_x, ball_y, rx1 + cx2, ry1 + cy2),
                                "conf": float(b.conf[0]),
                            })

        # 3. ACTIVE State Detectors
        if self.current_state == "ACTIVE":
            # MediaPipe on Cropped Player
            if p_box:
                nx1, ny1, nx2, ny2 = p_box
                # Add padding for pose tracking
                pad = 30
                cx1, cy1 = max(0, nx1 - pad), max(0, ny1 - pad)
                cx2, cy2 = min(frame.shape[1], nx2 + pad), min(frame.shape[0], ny2 + pad)

                crop = frame[cy1:cy2, cx1:cx2]
                if crop.size > 0:
                    telemetry.player_crop = crop
                    telemetry.player_crop_rect = (cx1, cy1, cx2, cy2)
                    """
                    crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                    pose_results = self.pose.process(crop_rgb)
                    # Translate landmarks back to full frame coordinates if needed here
                    telemetry.pose_landmarks = pose_results.pose_landmarks
                    """

            # Whole-court ball detection — include world coordinates for energy system
            ball_res = self.ball_model(frame, verbose=False, conf=0.10, imgsz=Config.BALL_IMGSZ)
            if ball_res and ball_res[0].boxes:
                for b in ball_res[0].boxes:
                    bx1, by1, bx2, by2 = b.xyxy[0].tolist()
                    bcx, bcy = (bx1 + bx2) / 2.0, (by1 + by2) / 2.0

                    # Filter: must be inside active-zone polygon, outside exclusion zones, outside player box
                    if (self._is_in_active_zone(bcx, bcy) and
                            not _is_in_exclusion_zone(bcx, bcy, self.exclusion_zones) and
                            not self._is_in_player_box(bcx, bcy, p_box, padding=15)):
                        world_x, world_y = self.get_world_pos(bcx, bcy)
                        telemetry.active_ball_candidates.append({
                            "box":          (bx1, by1, bx2, by2),
                            "conf":         float(b.conf[0]),
                            "world_x":      world_x,
                            "world_y":      world_y,
                            "pixel_center": (bcx, bcy),
                        })

        # Append to buffer
        self.telemetry_history.append(telemetry)
        return telemetry

    def update_state(self, new_state: str):
        old_state = self.current_state
        self.current_state = new_state

        if new_state == "ARMED" and old_state != "ARMED":
            now = self.frame_counter / self.fps
            # Clear dynamic zones and start fresh collection
            self.dynamic_exclusion_zones = []
            self._armed_frame_buffer     = []
            self._armed_entry_time       = now
            self._armed_collection_done  = False
            print("[INFO] ARMED entered — starting dynamic exclusion zone collection (0-0.5s)")