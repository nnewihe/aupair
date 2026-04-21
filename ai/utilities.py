import time
import random
from enum import Enum
from collections import deque
from dataclasses import dataclass, field
from ultralytics import YOLO
import cv2
import numpy as np
from typing import List, Optional, Tuple
import math
from sklearn.cluster import DBSCAN
from moviepy import VideoFileClip, concatenate_videoclips
import os
import json
import csv
import re
import subprocess
import argparse
import tempfile
import shutil


    
# =============================================================
# Config
# =============================================================
class Config:
    ANALYSIS_WIDTH = 960
    ANALYSIS_HEIGHT = 540
    PLAYER_IMGSZ = 480
    BALL_IMGSZ = 960
    TOSS_BALL_IMGSZ = 320
    ACTIVE_BALL_CONF = 0.15   # confidence threshold for whole-court ball detection (ACTIVE)
    TOSS_BALL_CONF   = 0.10   # confidence threshold for toss ROI ball detection (ARMED)
    TROPHY_IMGSZ = 320
    COURT_WIDTH_FT = 27.0
    COURT_LENGTH_FT = 78.0
    COURT_X_PADDING_FT = 15.0
    DEFAULT_BALL_CLASS_INDEX = 0
    DEFAULT_PLAYER_CLASS_INDEX = 0
    DEFAULT_NEAR_TROPHY_MODEL_PATH  = "weights/trophy_pose_cls2/weights/best.pt"
    DEFAULT_NEAR_TROPHY_CLASS_INDEX = 1
    DEFAULT_TROPHY_PAD              = 0.30
    TELEMETRY_BUFFER_SECONDS = 5.0
    HORIZON_Y_PX             = 200

# =============================================================
# BoxSmoother  
# =============================================================
# Add this to src/ai/utilities.py
@dataclass
class Point3D:
    x: float
    y: float
    z: float = 0.0

@dataclass
class Box:
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def w(self): return self.x2 - self.x1
    @property
    def h(self): return self.y2 - self.y1

    def contains(self, x, y):
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2

@dataclass
class BoxSmoother:
    """
    Exponentially-weighted moving average for a bounding box (cx, cy, w, h).

    Uses separate alphas for position and size, and suppresses size updates
    when the player appears stationary.

    Parameters
    ----------
    alpha_pos   : EWA weight for centre-point updates  (higher = more responsive)
    alpha_size  : EWA weight for width/height updates  (lower  = more stable)
    still_thresh: pixel/frame velocity below which size smoothing is further
                  suppressed (multiplied by 0.3).
    """
    alpha_pos:   float = 0.35
    alpha_size:  float = 0.12
    still_thresh: float = 4.0

    _cx: Optional[float] = field(default=None, init=False, repr=False)
    _cy: Optional[float] = field(default=None, init=False, repr=False)
    _w:  Optional[float] = field(default=None, init=False, repr=False)
    _h:  Optional[float] = field(default=None, init=False, repr=False)

    def update(self, cx: float, cy: float, w: float, h: float
               ) -> Tuple[float, float, float, float]:
        """Feed a raw (cx, cy, w, h) observation and get the smoothed version."""
        if self._cx is None:
            self._cx, self._cy, self._w, self._h = cx, cy, w, h
            return cx, cy, w, h

        vel = math.hypot(cx - self._cx, cy - self._cy)

        self._cx = (1 - self.alpha_pos) * self._cx + self.alpha_pos * cx
        self._cy = (1 - self.alpha_pos) * self._cy + self.alpha_pos * cy

        eff_alpha = self.alpha_size * 0.3 if vel < self.still_thresh else self.alpha_size
        self._w = (1 - eff_alpha) * self._w + eff_alpha * w
        self._h = (1 - eff_alpha) * self._h + eff_alpha * h

        return self._cx, self._cy, self._w, self._h

    def reset(self):
        """Clear the smoother's state (e.g. when tracking is interrupted)."""
        self._cx = self._cy = self._w = self._h = None

    def smooth_box_xyxy(self, x1: int, y1: int, x2: int, y2: int
                        ) -> Tuple[int, int, int, int]:
        """
        Convenience wrapper: accept raw (x1,y1,x2,y2), smooth internally,
        and return a smoothed (x1,y1,x2,y2) ready to draw on frame.
        """
        raw_cx = (x1 + x2) / 2.0
        raw_cy = (y1 + y2) / 2.0
        raw_w  = float(x2 - x1)
        raw_h  = float(y2 - y1)

        scx, scy, sw, sh = self.update(raw_cx, raw_cy, raw_w, raw_h)

        sx1 = int(scx - sw / 2.0)
        sy1 = int(scy - sh / 2.0)
        sx2 = int(scx + sw / 2.0)
        sy2 = int(scy + sh / 2.0)
        return sx1, sy1, sx2, sy2


# =============================================================
# Exclusion Zone Helpers
# =============================================================

def create_auto_exclusion_zones(
    video_path: str,
    ball_model,
    num_frames: int = 20,
    conf: float = 0.05,
    eps: int = 5,
    min_samples: int = 15,
    padding: int = 5,
    ball_class_index: int = 0,
    analysis_size: tuple = None,
) -> List[Tuple[int, int, int, int]]:
    """
    Scan random frames across the full video to find static clusters of objects
    that look like balls (e.g. ball-baskets). Uses DBSCAN clustering of detection
    centers. Returns exclusion zone rectangles with padding.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames < num_frames:
        cap.release()
        return []

    frame_indices = random.sample(range(total_frames), num_frames)

    all_detections = []
    for frame_idx in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, frame = cap.read()
        if not ok:
            continue

        if analysis_size is not None:
            frame = cv2.resize(frame, analysis_size, interpolation=cv2.INTER_AREA)

        res = ball_model(frame, verbose=False, conf=conf, imgsz=Config.BALL_IMGSZ)
        if res and res[0].boxes:
            for b in res[0].boxes:
                if int(b.cls[0]) != ball_class_index:
                    continue
                x1, y1, x2, y2 = b.xyxy[0].tolist()
                cx = 0.5 * (x1 + x2)
                cy = 0.5 * (y1 + y2)
                all_detections.append((cx, cy))

    cap.release()

    if len(all_detections) < min_samples:
        return []

    X = np.array(all_detections)
    db = DBSCAN(eps=eps, min_samples=min_samples).fit(X)
    labels = db.labels_

    zones = []
    for k in set(labels):
        if k == -1:
            continue
        pts = X[labels == k]
        if len(pts) > 0:
            x_min, y_min = np.min(pts, axis=0)
            x_max, y_max = np.max(pts, axis=0)
            zones.append((
                int(x_min - padding), int(y_min - padding),
                int(x_max + padding), int(y_max + padding),
            ))

    return zones


def get_exclusion_zones_from_frames(
    frames: List[np.ndarray],
    ball_model,
    sample_size: int = 5,
    conf: float = 0.10,
    eps: int = 5,
    min_samples: int = 15,
    padding: int = 5,
    ball_class_index: int = 0,
) -> List[Tuple[int, int, int, int]]:
    """
    Given a list of frames, detect balls and return exclusion zones using the
    same DBSCAN clustering logic as create_auto_exclusion_zones().
    Randomly sample frames, cluster detection centers, and return bounding boxes
    for valid clusters.
    """
    if not frames:
        return []

    sample = random.sample(frames, min(len(frames), sample_size))

    # Collect detection centers (same logic as static exclusion zones)
    all_detections = []
    for frm in sample:
        res = ball_model(frm, verbose=False, conf=conf, imgsz=Config.BALL_IMGSZ)
        if res and res[0].boxes:
            for b in res[0].boxes:
                if int(b.cls[0]) != ball_class_index:
                    continue
                x1, y1, x2, y2 = b.xyxy[0].tolist()
                cx = 0.5 * (x1 + x2)
                cy = 0.5 * (y1 + y2)
                all_detections.append((cx, cy))

    if len(all_detections) < min_samples:
        return []

    # Cluster detection centers using DBSCAN (same params as static zones)
    X = np.array(all_detections)
    db = DBSCAN(eps=eps, min_samples=min_samples).fit(X)
    labels = db.labels_

    zones = []
    for k in set(labels):
        if k == -1:
            continue
        pts = X[labels == k]
        if len(pts) > 0:
            x_min, y_min = np.min(pts, axis=0)
            x_max, y_max = np.max(pts, axis=0)
            zones.append((
                int(x_min - padding), int(y_min - padding),
                int(x_max + padding), int(y_max + padding),
            ))

    return zones


def _is_in_exclusion_zone(x, y, exclusion_zones):
    for (x1, y1, x2, y2) in exclusion_zones:
        if x1 <= x <= x2 and y1 <= y <= y2:
            return True
    return False


def _court_cache_path(video_path: str) -> str:
    video_dir  = os.path.dirname(os.path.abspath(video_path))
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    return os.path.join(video_dir, f"{video_name}_court_cache.json")


def init_court(video_path: str, target_idx: int = 300, analysis_size: tuple = None):
    """Interactive court corner selection with JSON caching."""
    cache_path = _court_cache_path(video_path)

    if os.path.isfile(cache_path):
        try:
            with open(cache_path, "r") as f:
                cached = json.load(f)
            cached_size = tuple(cached.get("analysis_size", [None, None]))
            if cached_size == (analysis_size if analysis_size else (None, None)):
                pts   = [tuple(p) for p in cached["points"]]
                shape = tuple(cached["frame_shape"])
                print(f"[COURT] Loaded cached corners from: {os.path.basename(cache_path)}")
                return pts, shape
            else:
                print("[COURT] Analysis size changed — re-selecting corners.")
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"[COURT] Cache corrupt ({e}), re-selecting.")

    num_points = 4
    win = "Click 4 court corners (any order). Press r=reset, q=quit"

    base = get_reference_frame(video_path, target_idx=target_idx)
    if analysis_size is not None:
        base = cv2.resize(base, analysis_size, interpolation=cv2.INTER_AREA)
    img = base.copy()

    state = {"img": img, "clicked_pts": [], "done": False, "win": win, "num_points": num_points}

    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.imshow(win, state["img"])
    cv2.setMouseCallback(win, select_points, state)

    while True:
        key = cv2.waitKey(20) & 0xFF
        if state["done"]:
            cv2.destroyWindow(win)
            cv2.waitKey(1)
            pts   = [(float(x), float(y)) for x, y in state["clicked_pts"]]
            shape = base.shape
            try:
                cache_data = {
                    "points": pts,
                    "frame_shape": list(shape),
                    "analysis_size": list(analysis_size) if analysis_size else [None, None],
                    "video": os.path.basename(video_path),
                }
                with open(cache_path, "w") as f:
                    json.dump(cache_data, f, indent=2)
                print(f"[COURT] Saved corners to: {os.path.basename(cache_path)}")
            except Exception as e:
                print(f"[COURT] WARN: Could not save cache: {e}")
            return pts, shape

        if key == ord("r"):
            state["clicked_pts"].clear()
            state["done"] = False
            state["img"] = base.copy()
            cv2.imshow(win, state["img"])

        if key in (ord("q"), 27):
            cv2.destroyWindow(win)
            cv2.waitKey(1)
            raise RuntimeError("Court polygon selection aborted by user.")


def point_line_distance_px(P, A, B):
    Px, Py = P
    Ax, Ay = A
    Bx, By = B
    ABx, ABy = Bx - Ax, By - Ay
    APx, APy = Px - Ax, Py - Ay
    cross = abs(ABx * APy - ABy * APx)
    denom = math.hypot(ABx, ABy)
    return 0.0 if denom == 0 else cross / denom


def get_reference_frame(video_path: str, target_idx: int):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        ok, frame = cap.read()
        cap.release()
        if not ok:
            raise RuntimeError("Could not read any frame from video.")
        return frame
    ref_idx = min(target_idx, total_frames // 2)
    cap.set(cv2.CAP_PROP_POS_FRAMES, ref_idx)
    ok, frame = cap.read()
    if not ok:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        raise RuntimeError(f"Failed to read reference frame (idx={ref_idx}).")
    return frame


def select_points(event, x, y, flags, param):
    if event != cv2.EVENT_LBUTTONDOWN:
        return
    state = param
    state["clicked_pts"].append((x, y))
    cv2.circle(state["img"], (x, y), 6, (0, 0, 255), -1, lineType=cv2.LINE_AA)
    if len(state["clicked_pts"]) == state["num_points"]:
        state["done"] = True
    cv2.imshow(state["win"], state["img"])


def build_mask(frame_shape, poly):
    h, w = frame_shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(mask, [poly], 255)
    return mask


def point_in_mask(mask, x, y):
    h, w = mask.shape[:2]
    if x < 0 or y < 0 or x >= w or y >= h:
        return False
    return mask[int(y), int(x)] != 0


def probe_video(video_path: str) -> dict:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")
    fps         = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width       = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height      = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    if fps <= 0 or fps > 300:
        print(f"[WARN] Video reported FPS={fps}, falling back to 30.0")
        fps = 30.0

    duration_sec = frame_count / fps if fps > 0 else 0.0
    info = {
        "fps": fps, "frame_count": frame_count,
        "width": width, "height": height, "duration_sec": duration_sec,
    }

    print(f"\n{'='*50}")
    print(f"  VIDEO PROBE: {os.path.basename(video_path)}")
    print(f"  Resolution : {width} x {height}")
    print(f"  FPS        : {fps:.2f}")
    print(f"  Frames     : {frame_count}")
    print(f"  Duration   : {duration_sec:.1f}s ({duration_sec/60:.1f} min)")
    print(f"{'='*50}\n")
    return info


def resize_for_analysis(frame):
    return cv2.resize(frame, (Config.ANALYSIS_WIDTH, Config.ANALYSIS_HEIGHT),
                      interpolation=cv2.INTER_AREA)