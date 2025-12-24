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
import csv
from typing import List, Optional, Tuple

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


# =====================================================
# Helper functions (pure)
# =====================================================
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
    rx1 = int(x1 - 0.6 * bw)
    rx2 = int(x2 + 0.6 * bw)

    # Vertical: from above head down to upper chest
    ry1 = int(y1 - 0.9 * bh)
    ry2 = int(y1 + 0.45 * bh)

    rx1 = max(0, min(W - 1, rx1))
    rx2 = max(0, min(W - 1, rx2))
    ry1 = max(0, min(H - 1, ry1))
    ry2 = max(0, min(H - 1, ry2))

    # Ensure valid box
    if rx2 <= rx1 + 2 or ry2 <= ry1 + 2:
        return (0, 0, W - 1, H - 1)

    return (rx1, ry1, rx2, ry2)


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

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        frame_idx += 1

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

    return serve_times


# =====================================================
# CLI demo entrypoint (optional)
# =====================================================
if __name__ == "__main__":
    # Example usage (edit paths as needed)
    serve_times = detect_serve_event_times(
        input_video="data/matches/2025-10-06-clean/raw_video.mp4",
        points_csv="data/matches/2025-10-06-clean/points.csv",
        near_side_start=True,
        write_telemetry_csv=True,
        telemetry_csv_path="serve_log.csv",
        show_ui=True,
    )
    print("\nServe start times (s):")
    print(serve_times)