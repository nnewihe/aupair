"""
Serve detection demo using:
  - Court detector -> ready band
  - Player detector -> near-side player box
  - Trophy pose classifier -> trophy confidence
  - Ball detector -> ball motion upward persistence -> toss score
  - ServePhysics -> combines (max toss + max trophy) into serve_start events

Visualization:
  - Player bbox only (green when armed)
  - Optional toss ROI rectangle
  - Ball dot when detected
  - Bottom-right big overlay: Toss (live/max), Trophy (live/max), ServeScore

CSV:
  serve_log.csv includes per-frame telemetry + serve_start flag
"""

import cv2, pathlib, sys
import numpy as np
import csv

try:
    from src.vision.court_mask import find_court_mask
    from src.vision.serve_physics import ServePhysics
except ImportError:
    root = pathlib.Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    from src.vision.court_mask import find_court_mask
    from src.vision.serve_physics import ServePhysics


# =====================================================
# CONFIG YOU SHOULD EDIT
# =====================================================
use_yolo = True

match_path ="data/matches/2025-12-07/"
video_path = match_path + "raw_video.mp4"

# Trophy classifier
TROPHY_MODEL_PATH = "weights/trophy_pose_cls2/weights/best.pt"
TROPHY_CLASS_INDEX = 1
TROPHY_PAD = 0.15

# Ball detector (YOLO detection model)
BALL_MODEL_PATH = "weights/ball/weights/best.pt"
BALL_CLASS_INDEX = 0  # change if needed

# Debug prints
DEBUG_PRINT_INTERVAL = 0.5

# Ball detector confidence minimum (raise if too many false balls)
BALL_CONF_MIN = 0.10

# Draw ROI box for debugging
DRAW_TOSS_ROI = True


# =====================================================
# YOLO Setup
# =====================================================
if use_yolo:
    from ultralytics import YOLO

    player_model = YOLO("yolov8n.pt")
    trophy_model = YOLO(TROPHY_MODEL_PATH)
    ball_model = YOLO(BALL_MODEL_PATH)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Error opening video: {video_path}")


# =====================================================
# CSV logging
# =====================================================
csv_file = open("serve_log.csv", "w", newline="")
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


# =====================================================
# Helper functions
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


def run_yolo_players(frame):
    res = player_model(frame, verbose=False)[0]
    boxes = []
    for b in res.boxes:
        if int(b.cls[0]) == 0:  # person
            x1, y1, x2, y2 = b.xyxy[0].tolist()
            boxes.append([x1, y1, x2, y2])
    return boxes


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
    This is a simple heuristic ROI above/around the player's upper body.

    You can tune these constants per camera angle.
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


def get_best_ball_in_roi(frame, roi, conf_min=0.10):
    """
    Runs ball detector and returns best ball (cx, cy, conf) within ROI or None.
    """
    rx1, ry1, rx2, ry2 = roi

    res = ball_model(frame, verbose=False)[0]

    best = None
    best_conf = -1.0

    for b in res.boxes:
        cls = int(b.cls[0])
        if cls != BALL_CLASS_INDEX:
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


# =====================================================
# MAIN
# =====================================================
def main():
    res = find_court_mask(
        video_path=video_path,
        poly_json_path=match_path+"court_poly.json",
        mask_playable_out=match_path+"court_mask_playable.png",
        mask_extended_out=match_path+"court_mask_extended.png",
        n_vertices=4,
        extend_px=0,
    )

    court_vertices = res.poly
    poly = compute_px_per_ft_poly(court_vertices)
    physics = ServePhysics(poly, court_vertices)

    print("\nStarting serve detection...\n")
    print(f"[INFO] Trophy model: {TROPHY_MODEL_PATH}")
    print(f"[INFO] Ball model:   {BALL_MODEL_PATH}")
    print(f"[INFO] ServeScore = 0.5 * toss_max_ready + 0.5 * trophy_max_ready")
    print(f"[INFO] Threshold={physics.serve_score_thresh} quiet={physics.quiet_period_s}s ready_min={physics.ready_min_s}s grace={physics.ready_grace_s}s\n")

    last_debug_print_t = -1.0

    # Fix vertex order for near-side selection
    sorted_by_y = sorted(court_vertices, key=lambda p: p[1])
    top_two = sorted_by_y[:2]
    bottom_two = sorted_by_y[2:]
    TL, TR = sorted(top_two, key=lambda p: p[0])
    BL, BR = sorted(bottom_two, key=lambda p: p[0])

    frame_idx = 0

    while True:
        ok, frame = cap.read()

        if not ok:
            break

        frame_idx += 1

        time_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
        time_s = time_ms / 1000.0

        # ----------------------------------------------
        # 1) Player detection
        # ----------------------------------------------
        boxes = run_yolo_players(frame) if use_yolo else []
        if not boxes:
            continue

        # ----------------------------------------------
        # 2) Choose near-side player (closest to bottom baseline)
        # ----------------------------------------------
        serve_candidates = []
        for box in boxes:
            x1, y1, x2, y2 = box
            cx = 0.5 * (x1 + x2)
            y_feet = y2
            P = (cx, y_feet)
            dist_top = point_line_distance_px(P, TL, TR)
            dist_bottom = point_line_distance_px(P, BL, BR)
            if dist_bottom < dist_top:
                serve_candidates.append((box, dist_bottom))

        if not serve_candidates:
            continue

        player_box = min(serve_candidates, key=lambda x: x[1])[0]

        # ----------------------------------------------
        # 3) Trophy classifier (every frame)
        # ----------------------------------------------
        trophy_conf = 0.0
        crop = crop_with_pad(frame, player_box, pad=TROPHY_PAD)
        if crop is not None:
            cls_res = trophy_model.predict(crop, verbose=False)[0]
            probs = getattr(cls_res, "probs", None)
            if probs is not None and getattr(probs, "data", None) is not None:
                arr = probs.data
                try:
                    arr_np = arr.detach().cpu().numpy() if hasattr(arr, "detach") else np.array(arr)
                    if len(arr_np) > TROPHY_CLASS_INDEX:
                        trophy_conf = float(arr_np[TROPHY_CLASS_INDEX])
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
            ball_det = get_best_ball_in_roi(frame, roi, conf_min=BALL_CONF_MIN)

        # ServePhysics.update_ball expects (cx,cy) or None
        ball_center = None
        ball_conf = ""
        if ball_det is not None:
            bx, by, bconf = ball_det
            ball_center = (float(bx), float(by))
            ball_conf = float(bconf)

        physics.update_ball(ball_center, time_s)

        # ----------------------------------------------
        # 6) Serve detection (toss_max + trophy_max)
        # ----------------------------------------------
        event = physics.detect_serve(p_state, time_s)
        serve_start_flag = 1 if event == "serve_start" else 0

        if event == "serve_start":
            print(f"[{time_s:0.3f}s] EVENT: serve_start (quiet until {physics.quiet_until_t:0.2f}s)")

        # ----------------------------------------------
        # 7) CSV log
        # ----------------------------------------------
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
        # 8) Visualization
        # ----------------------------------------------
        ready_ok = (
            p_state.in_ready and
            p_state.ready_duration_s >= float(physics.ready_min_s) and
            (not quiet_now)
        )
        box_color = (0, 255, 0) if ready_ok else (255, 255, 255)

        cv2.rectangle(frame,
                      (int(player_box[0]), int(player_box[1])),
                      (int(player_box[2]), int(player_box[3])),
                      box_color, 2)

        if DRAW_TOSS_ROI:
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
        # 9) Debug prints every 0.5s
        # ----------------------------------------------
        if last_debug_print_t < 0 or (time_s - last_debug_print_t) >= DEBUG_PRINT_INTERVAL:
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

        cv2.imshow("Serve Detection Demo", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    csv_file.close()
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()