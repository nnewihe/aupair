# court_mask.py Uses a prebuilt YOLO model to detect the court polygon from the first 200 valid court frames
# src/vision/court_mask.py
"""
Automatic court calibration using YOLO-based 6-keypoint court detector.

Workflow:
  - If court_poly JSON exists, load it and build masks (backward compatible).
  - Otherwise:
      * Run YOLO pose model over the video.
      * Collect up to N good frames with a court detection.
      * Average the 6 keypoints (CL, CC, CR, BR, BC, BL).
      * Fit a homography from canonical singles-court coordinates to image.
      * Project far-side singles corners using court dimensions.
      * Build a singles-court polygon in image coordinates.
      * Save polygon JSON and masks.
      * Also save a debug frame with the polygon overlaid in purple.

Result fields:
  CourtDetectResult.playable_mask   -> uint8(H,W) 255=inside singles-court polygon
  CourtDetectResult.extended_mask   -> uint8(H,W) dilated/extended playable mask
  CourtDetectResult.poly            -> float32 (N,2) polygon vertices CW
  CourtDetectResult.src_frame_shape -> (H,W,C)
"""

from __future__ import annotations
import os, json, cv2, numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple, List

# from .mask_utils import asymmetric_extend_mask  # if still needed elsewhere
from ultralytics import YOLO

@dataclass
class CourtDetectResult:
    playable_mask: Optional[np.ndarray]
    extended_mask: Optional[np.ndarray]
    poly: Optional[np.ndarray]               # (N,2) float32 CW
    src_frame_shape: Optional[Tuple[int,int,int]]


# ------------------------- configuration -------------------------

# Adjust this path if your weights live somewhere else.
# This assumes project_root/weights/court/weights/best.pt
_THIS_DIR = os.path.dirname(__file__)
_PROJECT_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))
YOLO_COURT_WEIGHTS = os.path.join(_PROJECT_ROOT, "weights", "court", "weights", "best.pt")

# How many good frames to average over when calibrating
CALIB_FRAMES_TARGET = 200


# ------------------------- utilities -------------------------

def _extract_middle_frame(video_path: str) -> np.ndarray:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    mid = max(0, n // 2)
    cap.set(cv2.CAP_PROP_POS_FRAMES, mid)
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        raise RuntimeError("Failed to read middle frame for calibration.")
    return frame


def _fit_edge_line(points: np.ndarray) -> tuple[float, float, float, float]:
    """
    Least-squares fit of a line through 'points' and return it as
    a segment spanning the min..max X range of those points:
      (x1, y1, x2, y2)
    Handles near-vertical edges by returning x = const spanning min..max Y.
    """
    pts = np.asarray(points, dtype=float).reshape(-1, 2)
    xs, ys = pts[:, 0], pts[:, 1]

    if len(pts) < 2 or np.allclose(xs.max(), xs.min()):
        x0 = float(xs.mean())
        y1, y2 = float(ys.min()), float(ys.max())
        return (x0, y1, x0, y2)

    a, b = np.polyfit(xs, ys, 1)  # y = a x + b
    x1, x2 = float(xs.min()), float(xs.max())
    y1, y2 = float(a * x1 + b), float(a * x2 + b)
    return (x1, y1, x2, y2)


def _poly_baselines(poly: np.ndarray) -> tuple[tuple[float, float, float, float],
                                               tuple[float, float, float, float]]:
    """
    Compute approximate TOP and BOTTOM baseline line segments from an arbitrary polygon.
    Returns:
      top_line, bottom_line as (x1,y1,x2,y2)
    """
    P = np.asarray(poly, dtype=float).reshape(-1, 2)
    if P.shape[0] < 4:
        idx = np.argsort(P[:, 1])
        top_band = P[idx[:max(2, P.shape[0] // 2)]]
        bot_band = P[idx[-max(2, P.shape[0] // 2):]]
    else:
        K = max(2, int(0.35 * P.shape[0]))
        idx = np.argsort(P[:, 1])
        top_band = P[idx[:K]]
        bot_band = P[idx[-K:]]

    top_line = _fit_edge_line(top_band)
    bottom_line = _fit_edge_line(bot_band)
    return top_line, bottom_line


def _mask_from_polygon(shape_hw: Tuple[int,int], poly: np.ndarray) -> np.ndarray:
    mask = np.zeros(shape_hw, dtype=np.uint8)
    cv2.fillPoly(mask, [poly.astype(np.int32)], 255)
    return mask


def extend_far_side(mask: np.ndarray, top_base, bot_base, extend_px: int = 50):
    """
    Extend ONLY the far-side baseline upward by extend_px.
    mask: binary mask (H,W)
    top_base, bot_base: each (x1,y1,x2,y2)
    extend_px: pixels to extend above the far baseline
    """
    H, W = mask.shape

    def mid_y(seg): return 0.5 * (seg[1] + seg[3])
    far_base = top_base if mid_y(top_base) < mid_y(bot_base) else bot_base

    y1 = int(min(far_base[1], far_base[3]))
    y2 = int(max(far_base[1], far_base[3]))

    y_start = max(0, y1 - extend_px)
    y_end   = y1

    source_slice = mask[y1:y2].copy()
    for y in range(y_start, y_end):
        mask[y] |= source_slice[min(y2-y1-1, y_end-y-1)]

    return mask


def _dilate(mask: np.ndarray, px: int) -> np.ndarray:
    k = max(1, int(px))
    if k % 2 == 0:
        k += 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    return cv2.dilate(mask, kernel, iterations=1)


# ------------------------- YOLO-based court auto-calibration -------------------------

def _collect_yolo_court_keypoints(video_path: str,
                                  weights_path: str = YOLO_COURT_WEIGHTS,
                                  max_frames: int = CALIB_FRAMES_TARGET,
                                  conf: float = 0.6):
    """
    Run YOLO court pose model over video, collect up to `max_frames` good
    detections. Returns:
      avg_kps: (6,2) float32 averaged keypoints in image coords
      debug_frame: one of the frames used for detection (BGR)
    """
    if not os.path.exists(weights_path):
        raise FileNotFoundError(f"Court YOLO weights not found at: {weights_path}")

    model = YOLO(weights_path)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    kps_list = []
    debug_frame = None
    frame_idx = 0

    while len(kps_list) < max_frames:
        ok, frame = cap.read()
        if not ok or frame is None:
            break

        frame_idx +=1

        # if frame_idx < 200: # Allow 200 frames to account for camera initial jitter
        #     continue

        # YOLO inference on this frame
        results = model(frame, conf=conf, verbose=False)
        if not results:
            continue
        r = results[0]

        if r.boxes is None or r.keypoints is None or len(r.boxes) == 0:
            continue

        # Pick detection with highest confidence
        confs = r.boxes.conf.detach().cpu().numpy()
        idx = int(np.argmax(confs))

        kpts_xy = r.keypoints.xy[idx]  # shape (6,2) for our model
        kpts_xy = kpts_xy.detach().cpu().numpy()

        if kpts_xy.shape[0] != 6:
            # Unexpected kpt shape; skip
            continue

        kps_list.append(kpts_xy)
        if debug_frame is None:
            debug_frame = frame.copy()

    cap.release()

    if len(kps_list) == 0:
        raise RuntimeError("YOLO court detector found no courts in the video.")

    kps_arr = np.stack(kps_list, axis=0)   # (N,6,2)
    avg_kps = kps_arr.mean(axis=0).astype(np.float32)  # (6,2)

    return avg_kps, debug_frame


def _build_singles_polygon_from_6kps(avg_kps: np.ndarray) -> np.ndarray:
    """
    Given averaged 6 keypoints in image coords, build a singles-court polygon
    using tennis geometry and homography.

    Expected order of avg_kps:
      0: CL = C-left   (service line, left singles corner)
      1: CC = C-center (service line, center)
      2: CR = C-right  (service line, right singles corner)
      3: BR = B-right  (baseline, right singles corner)
      4: BC = B-center (baseline, center)
      5: BL = B-left   (baseline, left singles corner)

    Canonical court coordinates (feet, singles):
      x ∈ [-13.5, 13.5]     -> singles width = 27 ft
      baseline y = 0        -> closest to camera
      service line y = 18   -> 18 ft in from baseline
      far baseline y = 78   -> full court length
    """
    if avg_kps.shape != (6, 2):
        raise ValueError(f"Expected avg_kps shape (6,2), got {avg_kps.shape}")

    # Unpack for readability
    img_CL = avg_kps[0]
    img_CC = avg_kps[1]
    img_CR = avg_kps[2]
    img_BR = avg_kps[3]
    img_BC = avg_kps[4]
    img_BL = avg_kps[5]

    # Image-space points in the same logical order as the canonical court points below
    img_pts = np.stack(
        [img_CL, img_CC, img_CR, img_BR, img_BC, img_BL],
        axis=0
    ).astype(np.float32)

    # Canonical singles court coordinates (in feet)
    half_w = 27.0 / 2.0          # singles half width = 13.5 ft
    y_base = 0.0                 # baseline (near side)
    y_srv  = 18.0                # baseline -> service line
    y_far  = 78.0                # baseline -> far baseline

    # IMPORTANT: map C* to service line (y_srv), B* to baseline (y_base)
    court_pts = np.array([
        [-half_w, y_srv],   # CL -> service line left
        [     0., y_srv],   # CC -> service line center
        [ half_w, y_srv],   # CR -> service line right
        [ half_w, y_base],  # BR -> baseline right
        [     0., y_base],  # BC -> baseline center
        [-half_w, y_base],  # BL -> baseline left
    ], dtype=np.float32)

    # Solve homography: court space -> image space
    H, _ = cv2.findHomography(court_pts, img_pts, method=0)
    if H is None:
        raise RuntimeError("Failed to compute homography from 6 keypoints.")

    def project(pts_2d: np.ndarray) -> np.ndarray:
        """Project (N,2) court coords to image coords using H."""
        pts_2d = pts_2d.reshape(-1, 1, 2).astype(np.float32)
        out = cv2.perspectiveTransform(pts_2d, H)
        return out.reshape(-1, 2)

    # Near baseline singles corners in court space
    near_court = np.array([
        [-half_w, y_base],   # BL (near left baseline)
        [ half_w, y_base],   # BR (near right baseline)
    ], dtype=np.float32)

    # Far baseline singles corners in court space
    far_court = np.array([
        [ half_w, y_far],    # far right baseline
        [-half_w, y_far],    # far left baseline
    ], dtype=np.float32)

    near_img = project(near_court)   # (2,2)
    far_img  = project(far_court)    # (2,2)

    # Singles-court polygon in clockwise order:
    # near_left -> near_right -> far_right -> far_left
    poly = np.vstack([
        near_img[0],    # BL (near left)
        near_img[1],    # BR (near right)
        far_img[0],     # far right
        far_img[1],     # far left
    ]).astype(np.float32)

    return poly


def _save_debug_overlay(frame: np.ndarray, poly: np.ndarray, avg_kps: np.ndarray, out_path: str):
    """
    Draw the court polygon in purple and the 6 averaged keypoints in yellow,
    with text labels: CL, CC, CR, BR, BC, BL.
    """
    vis = frame.copy()

    # Draw polygon in purple
    pts = poly.reshape(-1, 1, 2).astype(np.int32)
    cv2.polylines(vis, [pts], isClosed=True, color=(255, 0, 255), thickness=3)  # BGR: purple

    # Labels for the 6 feature points in your order
    kp_labels = ["CL", "CC", "CR", "BR", "BC", "BL"]

    for (x, y), label in zip(avg_kps, kp_labels):
        cx, cy = int(x), int(y)

        # Draw the point itself (yellow dot)
        cv2.circle(vis, (cx, cy), 5, (0, 255, 255), -1)  # BGR: yellow

        # Draw label slightly offset so it doesn't sit on top of the dot
        cv2.putText(
            vis,
            label,
            (cx + 6, cy - 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 255),  # same yellow
            2,
            cv2.LINE_AA,
        )

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    cv2.imwrite(out_path, vis)


# ------------------------- public API -------------------------

def load_or_calibrate(
    video_path: str,
    poly_json_path: str,
    mask_playable_out: Optional[str] = None,
    mask_extended_out: Optional[str] = None,
    n_vertices: int = 6,    # unused now but kept for API compatibility
    extend_px: int = 48,
) -> CourtDetectResult:
    """
    Load saved polygon if present; otherwise auto-calibrate using YOLO 6-keypoint
    court detector and tennis geometry, then build playable & extended masks.

    Returns playable & extended masks plus the polygon in original frame coordinates.
    """

    # Use middle frame for shape info (for masks) regardless of how poly is obtained
    frame = _extract_middle_frame(video_path)
    H, W = frame.shape[:2]

    # 1) Load existing polygon if present
    if os.path.exists(poly_json_path) and os.path.getsize(poly_json_path) > 0:
        with open(poly_json_path, "r", encoding="latin-1") as f:
            data = json.load(f)
        poly = np.array(data, dtype=np.float32).reshape(-1, 2)

        playable = _mask_from_polygon((H, W), poly)
        top_line, bot_line = _poly_baselines(poly)

        extended = extend_far_side(playable.copy(), top_base=top_line, bot_base=bot_line, extend_px=extend_px)
        extended = _dilate(extended.copy(), extend_px) if extend_px > 0 else extended.copy()

        if mask_playable_out:
            os.makedirs(os.path.dirname(mask_playable_out) or ".", exist_ok=True)
            cv2.imwrite(mask_playable_out, playable)
        if mask_extended_out:
            os.makedirs(os.path.dirname(mask_extended_out) or ".", exist_ok=True)
            cv2.imwrite(mask_extended_out, extended)

        return CourtDetectResult(playable_mask=playable, extended_mask=extended, poly=poly, src_frame_shape=frame.shape)

    # 2) Auto-calibration using YOLO
    avg_kps, debug_frame = _collect_yolo_court_keypoints(video_path, YOLO_COURT_WEIGHTS, CALIB_FRAMES_TARGET, conf=0.6)
    poly = _build_singles_polygon_from_6kps(avg_kps)  # (4,2)

    # Save polygon JSON
    os.makedirs(os.path.dirname(poly_json_path) or ".", exist_ok=True)
    with open(poly_json_path, "w") as f:
        json.dump(poly.tolist(), f, indent=2)

    # Build masks
    playable = _mask_from_polygon((H, W), poly)
    top_line, bot_line = _poly_baselines(poly)

    extended = extend_far_side(playable.copy(), top_base=top_line, bot_base=bot_line, extend_px=100)
    extended = _dilate(extended.copy(), extend_px) if extend_px > 0 else extended.copy()

    # Optional outputs
    if mask_playable_out:
        os.makedirs(os.path.dirname(mask_playable_out) or ".", exist_ok=True)
        cv2.imwrite(mask_playable_out, playable)
    if mask_extended_out:
        os.makedirs(os.path.dirname(mask_extended_out) or ".", exist_ok=True)
        cv2.imwrite(mask_extended_out, extended)

    # Debug overlay: polygon on one of the calibration frames
    if debug_frame is not None:
        debug_path = os.path.splitext(poly_json_path)[0] + "_debug.png"
        _save_debug_overlay(debug_frame, poly, avg_kps, debug_path)

    return CourtDetectResult(playable_mask=playable, extended_mask=extended, poly=poly, src_frame_shape=frame.shape)


# Backward-compatible alias
find_court_mask = load_or_calibrate