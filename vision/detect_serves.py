"""
Serve detection demo/function using:
  - Court detector -> ready band
  - Player detector -> near/far-side player box selection
  - Trophy pose classifier -> trophy confidence
  - Ball detector -> ball motion upward persistence -> toss score
  - ServePhysics -> combines (max toss + max trophy) into serve_start events

Output:
  detect_serve_event_times(...) -> List[float] of serve_start times (seconds)

Optional:
  - Telemetry CSV (serve_log.csv) for per-frame logging
  - UI visualization window
  - Best-effort restriction to point windows via points.csv if it contains recognizable start/end columns
"""

import cv2
import pathlib
import sys
import numpy as np
import math
import csv
import random
from typing import List, Optional, Tuple, Dict, Any

from dataclasses import dataclass
from filterpy.kalman import KalmanFilter
from sklearn.cluster import DBSCAN
import matplotlib.pyplot as plt



try:
    from src.vision.court_mask import find_court_mask
    from src.vision.serve_physics import ServePhysics
except ImportError:
    root = pathlib.Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    from src.vision.court_mask import find_court_mask
    from src.vision.serve_physics import ServePhysics


# =====================================================
# DEFAULTS (can be overridden by function args)
# =====================================================
DEFAULT_TROPHY_MODEL_PATH = "weights/trophy_pose_cls2/weights/best.pt"
DEFAULT_TROPHY_CLASS_INDEX = 1
DEFAULT_TROPHY_PAD = 0.15

DEFAULT_BALL_MODEL_PATH = "weights/ball/weights/best.pt"
DEFAULT_BALL_CLASS_INDEX = 0

DEFAULT_DEBUG_PRINT_INTERVAL = 0.5
DEFAULT_BALL_CONF_MIN = 0.10
DEFAULT_DRAW_TOSS_ROI = True

COURT_WIDTH_FT = 27.0   # singles width
COURT_LENGTH_FT = 78.0  # baseline to baseline
FT_TO_M = 0.3048
COURT_WIDTH_M = COURT_WIDTH_FT * FT_TO_M
COURT_LENGTH_M = COURT_LENGTH_FT * FT_TO_M


# =====================================================
# Helper functions (pure)
# =====================================================

def _homography_px_to_court_m(TL, TR, BR, BL):
    """
    Returns 3x3 homography mapping image pixels (court quad) -> court plane in meters.
    Court coordinates:
      (0,0)       (W,0)
      (0,L)       (W,L)
    """
    src = np.float32([TL, TR, BR, BL])
    dst = np.float32([
        [0.0, 0.0],
        [COURT_WIDTH_M, 0.0],
        [COURT_WIDTH_M, COURT_LENGTH_M],
        [0.0, COURT_LENGTH_M],
    ])
    H = cv2.getPerspectiveTransform(src, dst)
    return H


def _px_points_to_court_m(H, pts_xy):
    """
    pts_xy: list of (x,y) in pixels
    returns: list of (X,Y) in meters in court plane
    """
    if not pts_xy:
        return []
    arr = np.float32(pts_xy).reshape(-1, 1, 2)
    out = cv2.perspectiveTransform(arr, H).reshape(-1, 2)
    return [(float(p[0]), float(p[1])) for p in out]


def _poly_area_m2(pts_xy_m):
    """
    Shoelace area for polygon pts in order (e.g., tl,tr,br,bl).
    Returns positive area (m^2).
    """
    if pts_xy_m is None or len(pts_xy_m) < 3:
        return 0.0
    x = np.array([p[0] for p in pts_xy_m], dtype=float)
    y = np.array([p[1] for p in pts_xy_m], dtype=float)
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _second_derivative_nonuniform(t0, t1, t2, f0, f1, f2):
    """
    Second derivative at t1 for non-uniform sampling.
    Uses:
      f''(t1) ≈ 2 * ( (f2-f1)/(t2-t1) - (f1-f0)/(t1-t0) ) / (t2-t0)
    """
    dt10 = max(t1 - t0, 1e-9)
    dt21 = max(t2 - t1, 1e-9)
    dt20 = max(t2 - t0, 1e-9)
    return 2.0 * ((f2 - f1) / dt21 - (f1 - f0) / dt10) / dt20

def crop_with_pad(frame, box, pad=0.15):
    H, W = frame.shape[:2]
    x1, y1, x2, y2 = box
    bw = x2 - x1
    bh = y2 - y1
    px = pad * bw
    py = pad * bh

    x1i = max(0, int(x1 - px))
    y1i = max(0, int(y1 - py))
    x2i = min(W, int(x2 + px))
    y2i = min(H, int(y2 + py))

    if x2i <= x1i or y2i <= y1i:
        return None

    crop = frame[y1i:y2i, x1i:x2i].copy()
    return crop if crop.size else None


def point_line_distance_px(P, A, B):
    Px, Py = P
    Ax, Ay = A
    Bx, By = B

    ABx = Bx - Ax
    ABy = By - Ay
    APx = Px - Ax
    APy = Py - Ay

    cross = abs(ABx * APy - ABy * APx)
    denom = ((ABx * ABx) + (ABy * ABy)) ** 0.5
    if denom < 1e-6:
        return 1e9
    return cross / denom


def compute_px_per_ft_poly(corners):
    TL, TR, BR, BL = corners
    top_y = (TL[1] + TR[1]) / 2.0
    bottom_y = (BL[1] + BR[1]) / 2.0
    top_width_px = np.linalg.norm(np.array(TR) - np.array(TL))
    bottom_width_px = np.linalg.norm(np.array(BR) - np.array(BL))
    ft_width = 36.0
    ppf_top = top_width_px / ft_width
    ppf_bottom = bottom_width_px / ft_width
    a = (ppf_bottom - ppf_top) / (bottom_y - top_y)
    b = ppf_top - a * top_y
    return np.poly1d([a, b])


def toss_roi_from_player_box(frame_shape, player_box):
    """
    Returns an ROI (rx1,ry1,rx2,ry2) where we expect the tossed ball.
    Simple heuristic ROI above/around the player's upper body.
    """
    H, W = frame_shape[:2]
    x1, y1, x2, y2 = player_box
    bw = x2 - x1
    bh = y2 - y1

    # Horizontal: expand beyond shoulders
    rx1 = int(x1 - 0.25 * bw)
    rx2 = int(x2 + 0.25 * bw)

    # Vertical: from above head only
    ry1 = int(y1 - 1.0 * bh)
    ry2 = int(y1 + 0.2 * bh)

    rx1 = max(0, min(W - 1, rx1))
    rx2 = max(0, min(W - 1, rx2))
    ry1 = max(0, min(H - 1, ry1))
    ry2 = max(0, min(H - 1, ry2))

    # Ensure valid box
    if rx2 <= rx1 + 2 or ry2 <= ry1 + 2:
        return (0, 0, W - 1, H - 1)

    return (rx1, ry1, rx2, ry2)


def create_auto_exclusion_zones(
    video_path: str,
    ball_model,
    num_frames: int = 10,
    conf: float = 0.05,
    eps: int = 30,
    min_samples: int = 5,
    padding: int = 25,
) -> List[Tuple[int, int, int, int]]:
    """
    Analyzes a video to find static clusters of objects that look like balls (e.g., baskets)
    and returns a list of exclusion zones (rectangles) to mask them out.
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
        
        res = ball_model(frame, verbose=False, conf=conf)
        if res and res[0].boxes:
            for b in res[0].boxes:
                # Assuming ball is class 0, which is the default
                if int(b.cls[0]) != DEFAULT_BALL_CLASS_INDEX:
                    continue
                x1, y1, x2, y2 = b.xyxy[0].tolist()
                cx = 0.5 * (x1 + x2)
                cy = 0.5 * (y1 + y2)
                all_detections.append((cx, cy))
    
    cap.release()

    if len(all_detections) < min_samples:
        return []

    # Cluster detections to find static groups
    X = np.array(all_detections)
    db = DBSCAN(eps=eps, min_samples=min_samples).fit(X)
    labels = db.labels_
    
    unique_labels = set(labels)
    zones = []
    
    for k in unique_labels:
        if k == -1:
            # -1 is noise in DBSCAN
            continue
        
        class_member_mask = (labels == k)
        cluster_points = X[class_member_mask]
        
        if len(cluster_points) > 0:
            x_min, y_min = np.min(cluster_points, axis=0)
            x_max, y_max = np.max(cluster_points, axis=0)
            
            # Add padding to create the zone
            zones.append((
                int(x_min - padding),
                int(y_min - padding),
                int(x_max + padding),
                int(y_max + padding),
            ))
            
    return zones


# =====================================================
# points.csv helpers (optional)
# =====================================================
def _load_point_windows(points_csv_path: str) -> Optional[List[Tuple[float, float]]]:
    """
    Best-effort loader for point time windows from points.csv.

    If we can detect (start,end) columns -> returns list of (start_s, end_s).
    Otherwise returns None (function still works; points.csv is not required).
    """
    try:
        with open(points_csv_path, "r", newline="") as f:
            r = csv.DictReader(f)
            if not r.fieldnames:
                return None

            fields = [c.strip().lower() for c in r.fieldnames]

            def pick(*names):
                for n in names:
                    if n in fields:
                        return n
                return None

            start_col = pick("start_s", "point_start_s", "start", "point_start", "t_start", "start_time_s")
            end_col = pick("end_s", "point_end_s", "end", "point_end", "t_end", "end_time_s")
            if not start_col or not end_col:
                return None

            # Map back to original case-sensitive names
            name_map = {c.strip().lower(): c for c in r.fieldnames}
            start_col = name_map[start_col]
            end_col = name_map[end_col]

            windows: List[Tuple[float, float]] = []
            for row in r:
                try:
                    a = float(row[start_col])
                    b = float(row[end_col])
                    if b > a:
                        windows.append((a, b))
                except Exception:
                    continue

            return windows if windows else None

    except FileNotFoundError:
        return None
    except Exception:
        return None


def _time_in_windows(t: float, windows: Optional[List[Tuple[float, float]]]) -> bool:
    if windows is None:
        return True
    for a, b in windows:
        if a <= t <= b:
            return True
    return False


# =====================================================
# ACTIVEPLAY: Kalman + windowed YOLO tracker
# =====================================================

@dataclass
class BallTrackResult:
    xy: Optional[Tuple[int, int]]
    seen: bool
    v_mps: float
    roi: Optional[Tuple[int, int, int, int]]
    debug: Dict[str, Any]


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


class ActivePlayBallTracker:
    """
    Tracks ball position after serve using:
      KF prediction -> dynamic crop window -> YOLO on crop -> KF update.
    """
    def __init__(
        self,
        *,
        ball_model,                  # YOLO model instance (already loaded)
        fps: float,
        poly,                        # px/ft poly (callable)
        conf: float = 0.1,
        base_size: int = 380,
        uncertainty_scale: float = 0.10,
        use_perspective: bool = True,
        min_margin: int = 50,
        max_margin: int = 360,
        miss_timeout_s: float = 2.0,
        min_seen_for_velocity: int = 5,
        v_thresh_mps: float = 0.5,
        exclusion_zones: Optional[List[Tuple[int, int, int, int]]] = None,
    ):

        self.bootstrap_roi: Optional[Tuple[int,int,int,int]] = None
        self.bootstrap_until_seen: bool = False
        self.bootstrap_max_s: float = 0.75   # don’t stay stuck here forever
        self.bootstrap_start_t: float = -1e9

        self.ball_model = ball_model
        self.fps = float(fps)
        self.dt = 1.0 / max(self.fps, 1e-6)
        self.poly = poly

        self.conf = float(conf)
        self.base_size = int(base_size)
        self.uncertainty_scale = float(uncertainty_scale)
        self.use_perspective = bool(use_perspective)
        self.min_margin = int(min_margin)
        self.max_margin = int(max_margin)

        self.min_seen_for_velocity = int(min_seen_for_velocity)
        self.miss_timeout_s = float(miss_timeout_s)
        self.v_thresh_mps = float(v_thresh_mps)
        self.exclusion_zones = exclusion_zones if exclusion_zones is not None else []

        # KF: state [x,y,vx,vy] with vx,vy in px/s
        self.kf = KalmanFilter(dim_x=4, dim_z=2)
        self.kf.F = np.array([[1, 0, self.dt, 0],
                              [0, 1, 0, self.dt],
                              [0, 0, 1, 0],
                              [0, 0, 0, 1]], dtype=float)
        self.kf.H = np.array([[1, 0, 0, 0],
                              [0, 1, 0, 0]], dtype=float)
        self.kf.R = np.eye(2, dtype=float) * 10.0
        self.kf.Q = np.eye(4, dtype=float) * 25.0
        self.kf.P0 = np.eye(4, dtype=float) * 100.0

        self.reset()
    

    def set_bootstrap_roi(self, roi: Tuple[int,int,int,int], time_s: float, *, until_seen: bool = True):
        """Force initial search window to this ROI for a short time or until first detection."""
        self.bootstrap_roi = roi
        self.bootstrap_until_seen = bool(until_seen)
        self.bootstrap_start_t = float(time_s)

    def reset(self):
        self.kf.x = np.zeros((4, 1), dtype=float)
        self.kf.P = self.kf.P0.copy()
        self.initialized = False
        self.last_seen_t = -1e9
        self.track = []

        # If you add bootstrap ROI logic:
        self.bootstrap_roi = None
        self.bootstrap_start_t = -1e9
        self.bootstrap_until_seen = False

        # If you visualize/debug:
        self.last_roi = None
        self.last_pred_xy = None
        self.miss_streak = 0

        self.seen_count = 0

    def init_from_xy(self, xy: Tuple[float, float], time_s: float):
        x0, y0 = float(xy[0]), float(xy[1])
        self.kf.x = np.array([[x0], [y0], [0.0], [0.0]], dtype=float)
        self.kf.P = self.kf.P0.copy()
        self.initialized = True
        self.last_seen_t = float(time_s)
        self.track = [(int(x0), int(y0))]
        self.seen_count = 0

    def _best_det_in_window(
        self, window: np.ndarray, pred_win_xy: Tuple[float, float], win_x1: int, win_y1: int
    ) -> Optional[Tuple[float, float]]:
        px, py = pred_win_xy
        res = self.ball_model(window, verbose=False, conf=self.conf)
        if not res or res[0].boxes is None or len(res[0].boxes) == 0:
            return None

        best = None
        best_dist = float("inf")
        for b in res[0].boxes:
            x1, y1, x2, y2 = b.xyxy[0].tolist()
            cx = 0.5 * (x1 + x2)
            cy = 0.5 * (y1 + y2)

            # Check if the detection is inside an exclusion zone
            full_cx, full_cy = win_x1 + cx, win_y1 + cy
            is_excluded = False
            for zx1, zy1, zx2, zy2 in self.exclusion_zones:
                if zx1 <= full_cx <= zx2 and zy1 <= full_cy <= zy2:
                    is_excluded = True
                    break
            if is_excluded:
                continue

            d = (cx - px) ** 2 + (cy - py) ** 2
            if d < best_dist:
                best_dist = d
                best = (cx, cy)
        return best

    def step(self, frame: np.ndarray, time_s: float) -> BallTrackResult:
        H, W = frame.shape[:2]

        if not self.initialized and self.bootstrap_roi is None:
            return BallTrackResult(xy=None, seen=False, v_mps=0.0, roi=None, debug={"reason": "not_initialized"})

        # -------------------------------------------------
        # 1) Choose ROI for this frame (bootstrap vs KF window)
        # -------------------------------------------------
        use_bootstrap = False
        if self.bootstrap_roi is not None:
            if self.bootstrap_until_seen:
                # Stay in bootstrap ROI indefinitely until we see a detection.
                use_bootstrap = True
            else:
                # Time-limited bootstrap ROI.
                if (time_s - self.bootstrap_start_t) <= self.bootstrap_max_s:
                    use_bootstrap = True
                else:
                    # expired
                    self.bootstrap_roi = None

        if use_bootstrap:
            x1, y1, x2, y2 = self.bootstrap_roi
            x1 = _clamp(int(x1), 0, W - 1); y1 = _clamp(int(y1), 0, H - 1)
            x2 = _clamp(int(x2), 1, W);     y2 = _clamp(int(y2), 1, H)

            window = frame[y1:y2, x1:x2]

            # Predict for continuity if initialized; otherwise "predict" at ROI center
            if self.initialized:
                self.kf.predict()
                pred_x = float(self.kf.x[0, 0])
                pred_y = float(self.kf.x[1, 0])
            else:
                pred_x = 0.5 * (x1 + x2)
                pred_y = 0.5 * (y1 + y2)

            pred_win = (pred_x - x1, pred_y - y1)

            det_win = self._best_det_in_window(window, pred_win, x1, y1)
            seen = False

            if det_win is not None:
                det_full = (x1 + det_win[0], y1 + det_win[1])

                if not self.initialized:
                    self.init_from_xy(det_full, time_s=time_s)
                else:
                    z = np.array([[float(det_full[0])], [float(det_full[1])]], dtype=float)
                    self.kf.update(z)

                seen = True
                self.last_seen_t = float(time_s)
                self.seen_count += 1

                # If configured, stop bootstrapping as soon as we see the ball once.
                if self.bootstrap_until_seen:
                    self.bootstrap_roi = None

            if self.initialized:
                xy = (int(self.kf.x[0, 0]), int(self.kf.x[1, 0]))
                self.track.append(xy)
                v_mps = self._speed_mps()
                return BallTrackResult(
                    xy=xy, seen=seen, v_mps=v_mps, roi=(x1, y1, x2, y2),
                    debug={"mode": "bootstrap_roi", "until_seen": self.bootstrap_until_seen}
                )

            return BallTrackResult(
                xy=None, seen=False, v_mps=0.0, roi=(x1, y1, x2, y2),
                debug={"mode": "bootstrap_roi", "reason": "no_seed_yet", "until_seen": self.bootstrap_until_seen}
            )

        # 1) predict
        self.kf.predict()
        pred_x = float(self.kf.x[0, 0])
        pred_y = float(self.kf.x[1, 0])

        # 2) margin from uncertainty
        uncertainty = float(np.trace(self.kf.P[:2, :2]))
        margin = int(self.base_size + uncertainty * self.uncertainty_scale)

        if self.use_perspective:
            # shrink window towards far side
            perspective_factor = max(0.5, 1.0 - (pred_y / max(1.0, float(H))))
            margin = int(margin * perspective_factor)

        margin = _clamp(margin, self.min_margin, self.max_margin)

        # 3) crop window
        x1 = _clamp(int(pred_x - margin), 0, W - 1)
        y1 = _clamp(int(pred_y - margin), 0, H - 1)
        x2 = _clamp(int(pred_x + margin), 1, W)
        y2 = _clamp(int(pred_y + margin), 1, H)

        if x2 <= x1 + 2 or y2 <= y1 + 2:
            # degenerate
            xy = (int(self.kf.x[0, 0]), int(self.kf.x[1, 0]))
            v_mps = self._speed_mps()
            self.track.append(xy)
            return BallTrackResult(xy=xy, seen=False, v_mps=v_mps, roi=(x1, y1, x2, y2),
                                   debug={"uncertainty": uncertainty, "margin": margin, "reason": "degenerate_roi"})

        window = frame[y1:y2, x1:x2]
        pred_win = (pred_x - x1, pred_y - y1)
        det_win = self._best_det_in_window(window, pred_win, x1, y1)

        seen = False
        if det_win is not None:
            det_full = (x1 + det_win[0], y1 + det_win[1])
            z = np.array([[float(det_full[0])], [float(det_full[1])]], dtype=float)
            self.kf.update(z)
            seen = True
            self.last_seen_t = float(time_s)

        xy = (int(self.kf.x[0, 0]), int(self.kf.x[1, 0]))
        self.track.append(xy)

        v_mps = self._speed_mps()

        return BallTrackResult(
            xy=xy,
            seen=seen,
            v_mps=v_mps,
            roi=(x1, y1, x2, y2),
            debug={"uncertainty": uncertainty, "margin": margin, "seen": seen},
        )

    def _speed_mps(self) -> float:
        # KF vx,vy are px/s (because F uses dt)
        vx = float(self.kf.x[2, 0])
        vy = float(self.kf.x[3, 0])
        v_pxps = math.hypot(vx, vy)

        y = float(self.kf.x[1, 0])
        ppf = float(self.poly(y))  # px/ft
        v_ftps = v_pxps / max(ppf, 1e-6)
        return v_ftps * 0.3048

    def should_end_activeplay(self, time_s: float) -> bool:
        if (time_s - float(self.last_seen_t)) > self.miss_timeout_s:
            return True
        if self.seen_count >= int(self.min_seen_for_velocity):
            if self._speed_mps() < self.v_thresh_mps:
                return True
        return False



# =====================================================
# MAIN FUNCTION
# =====================================================
def detect_serve_event_times(
    input_video: str,
    points_csv: str,
    near_side_start: bool,
    *,
    use_yolo: bool = True,
    trophy_model_path: str = DEFAULT_TROPHY_MODEL_PATH,
    trophy_class_index: int = DEFAULT_TROPHY_CLASS_INDEX,
    trophy_pad: float = DEFAULT_TROPHY_PAD,
    ball_model_path: str = DEFAULT_BALL_MODEL_PATH,
    ball_class_index: int = DEFAULT_BALL_CLASS_INDEX,
    ball_conf_min: float = DEFAULT_BALL_CONF_MIN,
    debug_print_interval: float = DEFAULT_DEBUG_PRINT_INTERVAL,
    draw_toss_roi: bool = DEFAULT_DRAW_TOSS_ROI,
    write_telemetry_csv: bool = False,
    telemetry_csv_path: str = "serve_log.csv",
    show_ui: bool = True,
) -> List[float]:
    """
    Runs serve detection on input_video and returns a list of serve_start times (seconds).

    near_side_start:
      True  -> choose server on near side (closer to bottom baseline)
      False -> choose server on far side  (closer to top baseline)

    points_csv:
      Best-effort used to restrict processing to point windows if it contains recognizable
      (start,end) columns; otherwise it is safely ignored.
    """
    if not use_yolo:
        raise ValueError("use_yolo=False is not supported in this function yet.")

    # local import so this module can still be imported without ultralytics installed (until you call the function)
    from ultralytics import YOLO

    input_video = str(input_video)
    points_csv = str(points_csv)

    cap = cv2.VideoCapture(input_video)
    if not cap.isOpened():
        raise RuntimeError(f"Error opening video: {input_video}")

    # YOLO models
    player_model = YOLO("yolov8n.pt")
    trophy_model = YOLO(trophy_model_path)
    ball_model = YOLO(ball_model_path)

    # Auto-generate exclusion zones for static objects
    print("\n[INFO] Analyzing video for static objects to exclude...")
    try:
        exclusion_zones = create_auto_exclusion_zones(input_video, ball_model)
        if exclusion_zones:
            print(f"[INFO] Found {len(exclusion_zones)} static zone(s) to exclude.")
    except Exception as e:
        print(f"[WARN] Could not run auto-exclusion analysis: {e}")
        exclusion_zones = []

    # points.csv windows (optional)
    point_windows = _load_point_windows(points_csv)

    # Court mask artifacts saved next to the video by default
    match_dir = pathlib.Path(input_video).resolve().parent
    poly_json_path = str(match_dir / "court_poly.json")
    mask_playable_out = str(match_dir / "court_mask_playable.png")
    mask_extended_out = str(match_dir / "court_mask_extended.png")

    res = find_court_mask(
        video_path=input_video,
        poly_json_path=poly_json_path,
        mask_playable_out=mask_playable_out,
        mask_extended_out=mask_extended_out,
        n_vertices=4,
        extend_px=0,
    )

    court_vertices = res.poly
    poly = compute_px_per_ft_poly(court_vertices)
    physics = ServePhysics(poly, court_vertices)

    # Initialize Kalman Filter
    fps = cap.get(cv2.CAP_PROP_FPS)
    active_tracker = ActivePlayBallTracker(
        ball_model=ball_model,
        fps=fps,
        poly=poly,
        conf=0.1,
        miss_timeout_s=2.0,
        v_thresh_mps=0.5,
        exclusion_zones=exclusion_zones,
    )
    end_times: List[float] = []
    active_point = False

    print("\nStarting serve detection...\n")
    print(f"[INFO] Trophy model: {trophy_model_path}")
    print(f"[INFO] Ball model:   {ball_model_path}")
    print(f"[INFO] ServeScore = 0.5 * toss_max_ready + 0.5 * trophy_max_ready")
    print(
        f"[INFO] Threshold={physics.serve_score_thresh} quiet={physics.quiet_period_s}s "
        f"ready_min={physics.ready_min_s}s grace={physics.ready_grace_s}s\n"
    )

    # Fix vertex order for near/far selection
    sorted_by_y = sorted(court_vertices, key=lambda p: p[1])
    top_two = sorted_by_y[:2]
    bottom_two = sorted_by_y[2:]
    TL, TR = sorted(top_two, key=lambda p: p[0])
    BL, BR = sorted(bottom_two, key=lambda p: p[0])
    H_px_to_m = _homography_px_to_court_m(TL, TR, BR, BL)


    # Optional telemetry CSV
    csv_file = None
    csv_writer = None
    if write_telemetry_csv:
        csv_file = open(telemetry_csv_path, "w", newline="")
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow([
            "time_s",
            "player_cx_px", "player_feet_y_px",
            "cy_ft",
            "in_ready",
            "ready_duration_s",
            "quiet",
            "trophy_conf",
            "ball_x_px", "ball_y_px", "ball_conf",
            "ball_vy_up_pxps",
            "ball_up_streak",
            "toss_score", "toss_max",
            "trophy_max",
            "serve_score",
            "serve_start",
        ])
        csv_file.flush()

    def run_yolo_players_local(frame):
        res0 = player_model(frame, verbose=False)[0]
        out = []
        for b in res0.boxes:
            if int(b.cls[0]) == 0:  # person
                x1, y1, x2, y2 = b.xyxy[0].tolist()
                out.append([x1, y1, x2, y2])
        return out

    def get_best_ball_in_roi_local(frame, roi, conf_min=0.10):
        rx1, ry1, rx2, ry2 = roi
        resb = ball_model(frame, verbose=False)[0]

        best = None
        best_conf = -1.0

        for b in resb.boxes:
            cls = int(b.cls[0])
            if cls != ball_class_index:
                continue
            conf = float(b.conf[0])
            if conf < conf_min:
                continue

            x1, y1, x2, y2 = b.xyxy[0].tolist()
            cx = 0.5 * (x1 + x2)
            cy = 0.5 * (y1 + y2)

            if rx1 <= cx <= rx2 and ry1 <= cy <= ry2:
                if conf > best_conf:
                    best_conf = conf
                    best = (cx, cy, conf)

        return best

    serve_times: List[float] = []
    last_debug_print_t = -1.0
    frame_idx = 0
    active_point = False # Assumes we start in dead time
    active_point_start_t = None

    # -------------------------------------------------
    # Player dynamics logging (court-plane, meters)
    # -------------------------------------------------
    dyn_rows = []  # will store per-frame raw values; we compute 2nd derivatives after the loop
    # each row will hold:
    #   time_s,
    #   pos_m=(X,Y),
    #   corners_m=[tl,tr,br,bl] in meters,
    #   area_m2


    while True:
        ok, frame = cap.read()
        if not ok:
            break

        frame_idx += 10

        time_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
        time_s = time_ms / 1000.0

        # If points.csv gave us point windows, skip frames outside points
        if not _time_in_windows(time_s, point_windows):
            continue

        # ----------------------------------------------
        # 1) Player detection
        # ----------------------------------------------
        boxes = run_yolo_players_local(frame)
        if not boxes:
            continue

        # ----------------------------------------------
        # 2) Choose player based on near_side_start flag
        #    near_side_start=True  -> closest to bottom baseline
        #    near_side_start=False -> closest to top baseline
        # ----------------------------------------------
        serve_candidates = []
        for box in boxes:
            x1, y1, x2, y2 = box
            cx = 0.5 * (x1 + x2)
            y_feet = y2
            P = (cx, y_feet)
            dist_top = point_line_distance_px(P, TL, TR)
            dist_bottom = point_line_distance_px(P, BL, BR)

            if near_side_start:
                if dist_bottom < dist_top:
                    serve_candidates.append((box, dist_bottom))
            else:
                if dist_top < dist_bottom:
                    serve_candidates.append((box, dist_top))

        if not serve_candidates:
            continue

        player_box = min(serve_candidates, key=lambda x: x[1])[0]

        # ----------------------------------------------
        # Player dynamics in court meters (assume on ground plane)
        # ----------------------------------------------
        x1, y1, x2, y2 = player_box

        # (2) player position = bottom-center of bbox in meters
        bc_px = (0.5 * (x1 + x2), y2)

        # (3) bbox corners projected onto court plane (meters)
        tl_px = (x1, y1)
        tr_px = (x2, y1)
        br_px = (x2, y2)
        bl_px = (x1, y2)

        pos_m = _px_points_to_court_m(H_px_to_m, [bc_px])[0]
        corners_m = _px_points_to_court_m(H_px_to_m, [tl_px, tr_px, br_px, bl_px])  # order: tl,tr,br,bl
        area_m2 = _poly_area_m2(corners_m)

        dyn_rows.append({
            "time_s": float(time_s),
            "pos_x_m": pos_m[0],
            "pos_y_m": pos_m[1],
            "tl_x_m": corners_m[0][0], "tl_y_m": corners_m[0][1],
            "tr_x_m": corners_m[1][0], "tr_y_m": corners_m[1][1],
            "br_x_m": corners_m[2][0], "br_y_m": corners_m[2][1],
            "bl_x_m": corners_m[3][0], "bl_y_m": corners_m[3][1],
            "area_m2": float(area_m2),
        })

        # ----------------------------------------------
        # 3) Trophy classifier (every frame)
        # ----------------------------------------------
        trophy_conf = 0.0
        crop = crop_with_pad(frame, player_box, pad=trophy_pad)
        if crop is not None:
            cls_res = trophy_model.predict(crop, verbose=False)[0]
            probs = getattr(cls_res, "probs", None)
            if probs is not None and getattr(probs, "data", None) is not None:
                arr = probs.data
                try:
                    arr_np = arr.detach().cpu().numpy() if hasattr(arr, "detach") else np.array(arr)
                    if len(arr_np) > trophy_class_index:
                        trophy_conf = float(arr_np[trophy_class_index])
                except Exception:
                    trophy_conf = 0.0

        # ----------------------------------------------
        # 4) Physics update (ready band + trophy)
        # ----------------------------------------------
        p_state = physics.update_player(player_box, time_s, trophy_conf=trophy_conf)
        if p_state is None:
            continue

        # ----------------------------------------------
        # 5) Ball detection ONLY when "armed"
        #    Armed = in_ready AND not in quiet
        # ----------------------------------------------
        quiet_now = physics.in_quiet(time_s)
        roi = toss_roi_from_player_box(frame.shape, player_box)

        ball_det = None
        if p_state.in_ready and (not quiet_now):
            ball_det = get_best_ball_in_roi_local(frame, roi, conf_min=ball_conf_min)

        ball_center = None
        if ball_det is not None:
            bx, by, bconf = ball_det
            ball_center = (float(bx), float(by))

        physics.update_ball(ball_center, time_s)

        # ----------------------------------------------
        # 6) Serve detection (toss_max + trophy_max)
        # ----------------------------------------------
        event = physics.detect_serve(p_state, time_s)
        serve_start_flag = 1 if event == "serve_start" else 0

        if event == "serve_start":
            print(f"[{time_s:0.3f}s] EVENT: serve_start (quiet until {physics.quiet_until_t:0.2f}s)")
            serve_times.append(float(time_s))
            active_point = True

        

        # ----------------------------------------------
        # 7) ACTIVEPLAY ball tracking (KF + windowed YOLO)
        # ----------------------------------------------
        if event == "serve_start":
            active_point = True
            active_point_start_t = time_s

            # Reset ONCE
            active_tracker.reset()

            # Prevent immediate timeout before first detection
            active_tracker.last_seen_t = time_s

            # Bootstrap search = toss ROI
            active_tracker.set_bootstrap_roi(roi, time_s=time_s, until_seen=True)

            # If we already detected the ball in toss ROI this same frame, seed KF
            if ball_det is not None:
                bx, by, _ = ball_det
                active_tracker.init_from_xy((bx, by), time_s=time_s)
                active_tracker.bootstrap_roi = None  # optional: since we already saw it


        if active_point:
            # If tracker isn't initialized yet, let it bootstrap inside toss ROI first.
            # (Optional) after some time, do ONE global seed attempt.
            if (not active_tracker.initialized) and (time_s - active_point_start_t) > 0.25:
                resb = ball_model(frame, verbose=False, conf=0.25)[0]
                best_seed = None
                best_conf = -1.0
                if resb.boxes:
                    for b in resb.boxes:
                        if int(b.cls[0]) != ball_class_index:
                            continue
                        conf = float(b.conf[0])
                        if conf > best_conf:
                            x1, y1, x2, y2 = b.xyxy[0].tolist()
                            best_seed = (0.5*(x1+x2), 0.5*(y1+y2))
                            best_conf = conf
                if best_seed is not None:
                    active_tracker.init_from_xy(best_seed, time_s=time_s)

            # STEP ONCE
            track_out = active_tracker.step(frame, time_s)

            # Draw search ROI + tracked point
            if show_ui and track_out.roi is not None:
                x1, y1, x2, y2 = track_out.roi
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                cv2.putText(frame, "KF search", (x1, max(20, y1 - 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            if show_ui and track_out.xy is not None:
                tx, ty = track_out.xy
                cv2.circle(frame, (tx, ty), 6, (0, 255, 255), -1)
                cv2.putText(frame, f"ACTIVE v={track_out.v_mps:.2f} m/s", (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

            # Terminate ACTIVEPLAY only after grace
            if (time_s - active_point_start_t) > 0.5:
                # Stronger rule: require at least one “seen” detection before allowing velocity-based stop
                # (Optional but recommended)
                if active_tracker.initialized and active_tracker.should_end_activeplay(time_s):
                    active_point = False
                    end_times.append(float(time_s))
                    active_tracker.reset()
        # ----------------------------------------------
        # 7) CSV log (optional)
        # ----------------------------------------------
        if csv_writer is not None:
            x1, y1, x2, y2 = player_box
            player_cx_px = 0.5 * (x1 + x2)
            player_feet_y_px = y2
            cy_ft = p_state.sm_cy_ft if p_state.sm_cy_ft is not None else 0.0
            in_ready = 1 if p_state.in_ready else 0

            bx, by, bconf = ("", "", "")
            if ball_det is not None:
                bx, by, bconf = ball_det

            csv_writer.writerow([
                time_s,
                player_cx_px, player_feet_y_px,
                cy_ft,
                in_ready,
                float(p_state.ready_duration_s),
                bool(quiet_now),
                float(trophy_conf),
                bx, by, bconf,
                float(getattr(physics.ball_state, "vy_up_pxps", 0.0)),
                int(getattr(physics.ball_state, "up_streak", 0)),
                float(physics.toss_score),
                float(physics.toss_max_ready),
                float(physics.trophy_max_ready),
                float(physics.serve_score),
                serve_start_flag,
            ])
            csv_file.flush()

        # ----------------------------------------------
        # 8) Visualization (optional)
        # ----------------------------------------------
        if show_ui:
            # Draw exclusion zones (if any) as semi-transparent overlays
            overlay = frame.copy()
            for zx1, zy1, zx2, zy2 in exclusion_zones:
                cv2.rectangle(overlay, (zx1, zy1), (zx2, zy2), (255, 0, 255), -1)
            frame = cv2.addWeighted(overlay, 0.3, frame, 0.7, 0)

            ready_ok = (
                p_state.in_ready and
                p_state.ready_duration_s >= float(physics.ready_min_s) and
                (not quiet_now)
            )
            box_color = (0, 255, 0) if ready_ok else (255, 255, 255)

            cv2.rectangle(
                frame,
                (int(player_box[0]), int(player_box[1])),
                (int(player_box[2]), int(player_box[3])),
                box_color, 2
            )

            if draw_toss_roi:
                rx1, ry1, rx2, ry2 = roi
                cv2.rectangle(frame, (rx1, ry1), (rx2, ry2), (80, 80, 80), 2)

            if ball_det is not None:
                cx, cy, conf = ball_det
                cv2.circle(frame, (int(cx), int(cy)), 6, (0, 200, 255), -1)

            # Bottom-right big overlay
            H, W = frame.shape[:2]
            lines = [
                f"Toss:   {physics.toss_score:.2f}  (max {physics.toss_max_ready:.2f})",
                f"Trophy: {trophy_conf:.2f}  (max {physics.trophy_max_ready:.2f})",
                f"Serve:  {physics.serve_score:.2f}  thr {physics.serve_score_thresh:.2f}",
            ]

            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 1.4
            thickness = 3
            pad = 18
            line_h = 38

            box_w = 0
            for txt in lines:
                (tw, th), _ = cv2.getTextSize(txt, font, font_scale, thickness)
                box_w = max(box_w, tw)

            box_h = line_h * len(lines)
            x0 = W - box_w - pad * 2
            y0 = H - box_h - pad * 2

            cv2.rectangle(frame, (x0, y0), (W, H), (0, 0, 0), -1)

            for i, txt in enumerate(lines):
                y = y0 + pad + (i + 1) * line_h
                cv2.putText(frame, txt, (x0 + pad, y), font, font_scale,
                            (255, 255, 255), thickness, cv2.LINE_AA)

        # ----------------------------------------------
        # 9) Debug prints every N seconds
        # ----------------------------------------------
        if last_debug_print_t < 0 or (time_s - last_debug_print_t) >= debug_print_interval:
            last_debug_print_t = time_s
            bs = physics.ball_state
            print(
                f"[DEBUG {time_s:7.2f}s] "
                f"active point={active_point}"
                f"in_ready={p_state.in_ready} ready_dur={p_state.ready_duration_s:4.2f}s quiet={quiet_now} | "
                f"ball_seen={'Y' if bs.last_ball_seen_t is not None else 'N'} "
                f"vy_up={bs.vy_up_pxps:7.1f}px/s up_streak={bs.up_streak:2d} onset={bs.toss_onset_t} | "
                f"toss={physics.toss_score:4.2f} toss_max={physics.toss_max_ready:4.2f} | "
                f"trophy={trophy_conf:4.2f} trophy_max={physics.trophy_max_ready:4.2f} | "
                f"serve={physics.serve_score:4.2f}"
            )

        if show_ui:
            cv2.imshow("Serve Detection Demo", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    if csv_file is not None:
        csv_file.close()
    cap.release()
    if show_ui:
        cv2.destroyAllWindows()

    # --- Player Dynamics CSV Output ---
    if dyn_rows:
        print("\n[INFO] Computing player dynamics (2nd derivatives) and saving CSV...")

        out_csv = "player_box_dynamics_court_m.csv"
        with open(out_csv, "w", newline="") as f:
            w = csv.writer(f)

            w.writerow([
                "time_s",

                # (2) bottom-center position (meters)
                "player_bc_x_m", "player_bc_y_m",

                # (3) projected bbox corners (meters)
                "tl_x_m", "tl_y_m",
                "tr_x_m", "tr_y_m",
                "bl_x_m", "bl_y_m",
                "br_x_m", "br_y_m",

                # helpful raw scalar
                "bbox_area_m2",

                # (4) second derivative of position (acceleration)
                "acc_x_mps2", "acc_y_mps2", "acc_mag_mps2",

                # (5) second derivative of area
                "area_ddot_m2ps2",
            ])

            n = len(dyn_rows)
            for i in range(n):
                r = dyn_rows[i]
                t = r["time_s"]

                # Defaults at boundaries (no symmetric neighbors)
                acc_x = acc_y = acc_mag = 0.0
                area_ddot = 0.0

                if 0 < i < n - 1:
                    r0 = dyn_rows[i - 1]
                    r1 = dyn_rows[i]
                    r2 = dyn_rows[i + 1]

                    t0, t1, t2 = r0["time_s"], r1["time_s"], r2["time_s"]

                    # position second derivative (component-wise)
                    acc_x = _second_derivative_nonuniform(t0, t1, t2, r0["pos_x_m"], r1["pos_x_m"], r2["pos_x_m"])
                    acc_y = _second_derivative_nonuniform(t0, t1, t2, r0["pos_y_m"], r1["pos_y_m"], r2["pos_y_m"])
                    acc_mag = float(math.hypot(acc_x, acc_y))

                    # area second derivative
                    area_ddot = _second_derivative_nonuniform(t0, t1, t2, r0["area_m2"], r1["area_m2"], r2["area_m2"])

                w.writerow([
                    t,
                    r["pos_x_m"], r["pos_y_m"],

                    r["tl_x_m"], r["tl_y_m"],
                    r["tr_x_m"], r["tr_y_m"],
                    r["bl_x_m"], r["bl_y_m"],
                    r["br_x_m"], r["br_y_m"],

                    r["area_m2"],

                    acc_x, acc_y, acc_mag,
                    area_ddot,
                ])

        print(f"[INFO] Player dynamics CSV saved to {out_csv}")
    return serve_times


# =====================================================
# CLI demo entrypoint (optional)
# =====================================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Detect serves in a video.")
    parser.add_argument("input_video", help="Path to the input video file.")
    parser.add_argument("--points_csv", help="Path to the points CSV file.", default="")
    parser.add_argument("--near_side_start", action="store_true", help="Flag to indicate the serve is from the near side.")
    parser.add_argument("--show_ui", action="store_true", help="Flag to show the UI.")

    args = parser.parse_args()

    # Example usage (edit paths as needed)
    serve_times = detect_serve_event_times(
        input_video=args.input_video,
        points_csv=args.points_csv,
        near_side_start=args.near_side_start,
        write_telemetry_csv=True,
        telemetry_csv_path="serve_log.csv",
        show_ui=args.show_ui,
    )
    print("\nServe start times (s):")
    print(serve_times)
