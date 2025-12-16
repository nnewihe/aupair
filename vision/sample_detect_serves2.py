"""
Sample script for detecting serves from video using serve_physics.py

Requirements:
- opencv-python
- numpy
- serve_physics.py in same directory
- YOLO models for player detection + trophy classification
"""

import cv2, pathlib, sys
import numpy as np
from dataclasses import dataclass
from typing import List, Optional
import csv
import matplotlib.pyplot as plt

# ---- Robust imports (works as module or script) ----
try:
    from src.vision.court_mask import find_court_mask
    from src.vision.serve_physics2 import ServePhysics
    # [REMOVED] from src.vision.player_debug_overlay import draw_player_state
except ImportError:
    root = pathlib.Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    from src.vision.court_mask import find_court_mask
    from src.vision.serve_physics2 import ServePhysics

# Live CSV logging
csv_file = open("server_motion_log.csv", "w", newline="")
csv_writer = csv.writer(csv_file)

# CSV header
csv_writer.writerow([
    "time_s",
    "cx_px", "cy_px",
    "cy_ft",
    "v_cy_ftps",
    "in_ready",
    "trophy_conf",
    "serve_start"
])
csv_file.flush()

# =====================================================
# YOLO Setup
# =====================================================
use_yolo = True
video_path = "data/matches/2025-11-27/raw_video.mp4"
points_path = "data/matches/2025-09-30/points.csv"

TROPHY_MODEL_PATH = "weights/trophy_pose_cls2/weights/best.pt"
TROPHY_CLASS_INDEX = 1
TROPHY_PAD = 0.15

if use_yolo:
    from ultralytics import YOLO
    player_model = YOLO("yolov8n.pt")
    trophy_model = YOLO(TROPHY_MODEL_PATH)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("Error opening video")

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
    results = player_model(frame, verbose=False)[0]
    boxes = []
    for b in results.boxes:
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

# =====================================================
# MAIN
# =====================================================

def main():
    res = find_court_mask(
        video_path=video_path,
        poly_json_path="data/court_poly.json",
        mask_playable_out="data/court_mask_playable.png",
        mask_extended_out="data/court_mask_extended.png",
        n_vertices=4,
        extend_px=0,
    )

    # [DEBUG / SCORING PARAMS]
    V_SCORE_MARGIN = 4.0   # ft/s above swing_vel_threshold that maps to v_score = 1.0

    court_vertices = res.poly
    poly = compute_px_per_ft_poly(court_vertices)
    physics = ServePhysics(poly, court_vertices)

    print("\nStarting serve detection...\n")

    # Debug overlay timing
    DEBUG_PRINT_INTERVAL = 0.5  # seconds
    last_debug_print_t = -1.0
    
    # ---- FIX VERTEX ORDER (used for serve-side selection) ----
    sorted_by_y = sorted(court_vertices, key=lambda p: p[1])
    top_two    = sorted_by_y[:2]
    bottom_two = sorted_by_y[2:]
    TL, TR = sorted(top_two, key=lambda p: p[0])
    BL, BR = sorted(bottom_two, key=lambda p: p[0])

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        time_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
        time_s = time_ms / 1000.0

        # ----------------------------------------------
        # 1) PLAYER DETECTION
        # ----------------------------------------------
        boxes = run_yolo_players(frame) if use_yolo else []
        if len(boxes) == 0:
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
        # 3) [CHANGED] Trophy classifier runs EVERY frame
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
        # 4) [CHANGED] Update physics with trophy_conf each frame
        # ----------------------------------------------
        p_state = physics.update_player(player_box, time_s, trophy_conf=trophy_conf)
        if p_state is None:
            continue

        # ----------------------------------------------
        # 5) [CHANGED] Serve detection (simplified) + quiet period
        # ----------------------------------------------
        event = physics.detect_serve(p_state, time_s)
        serve_start_flag = 1 if event == "serve_start" else 0

        # ----------------------------------------------
        # 6) CSV log (kept same fields)
        # ----------------------------------------------
        x1, y1, x2, y2 = player_box
        cx_px = 0.5 * (x1 + x2)
        cy_px = y2
        cy_ft = p_state.sm_cy_ft
        vcy = p_state.v_cy_ftps
        in_ready = 1 if p_state.in_ready else 0

        csv_writer.writerow([
            time_s,
            cx_px, cy_px,
            cy_ft,
            vcy,
            in_ready,
            trophy_conf,
            serve_start_flag
        ])
        csv_file.flush()

        # Compute V-score explicitly
        v_score = 0.0
        if p_state is not None:
            v = float(p_state.v_cy_ftps)
            V0 = float(physics.swing_vel_threshold)
            V1 = V0 + V_SCORE_MARGIN

            # IMPORTANT: keep sign explicit for debugging
            if v <= V0:
                v_score = 0.0
            elif v >= V1:
                v_score = 1.0
            else:
                v_score = (v - V0) / (V1 - V0)
        # ----------------------------------------------
        # 7) [CHANGED] Box-only visualization
        #     - Green only when ready-time satisfied AND not in quiet period
        # ----------------------------------------------
        ready_ok = (
            p_state.in_ready and
            p_state.ready_duration_s >= 1.0 and
            time_s >= physics.quiet_until_t
        )

        box_color = (0, 255, 0) if ready_ok else (255, 255, 255)

        cv2.rectangle(frame,
                      (int(player_box[0]), int(player_box[1])),
                      (int(player_box[2]), int(player_box[3])),
                      box_color, 2)

        # ----------------------------------------------
        # 8) [NEW] Bottom-right big live scores (every frame)
        # ----------------------------------------------
        # --- Bottom-right debug overlay ---
        H, W = frame.shape[:2]

        v_max = physics.v_score_max_ready
        t_max = physics.trophy_score_max_ready
        serve_score = physics.serve_score

        lines = [
            f"Trophy Max: {t_max:.2f}",
            f"Vel Max:    {v_max:.2f}",
            f"ServeScore: {serve_score:.2f}",
        ]

        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 1.8
        thickness = 4
        pad = 20
        line_h = 45

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
            cv2.putText(
                frame,
                txt,
                (x0 + pad, y),
                font,
                font_scale,
                (255, 255, 255),
                thickness,
                cv2.LINE_AA
            )

        # =====================================================
        # DEBUG OVERLAY (every 0.5s)
        # =====================================================
        if last_debug_print_t < 0 or (time_s - last_debug_print_t) >= DEBUG_PRINT_INTERVAL:
            last_debug_print_t = time_s

            ready_dur = p_state.ready_duration_s if p_state is not None else 0.0
            in_ready  = p_state.in_ready if p_state is not None else False
            v_raw     = p_state.v_cy_ftps if p_state is not None else 0.0

            v_max = getattr(physics, "v_score_max_ready", 0.0)
            t_max = getattr(physics, "trophy_score_max_ready", 0.0)
            serve_score = getattr(physics, "serve_score", 0.0)

            quiet = False
            if hasattr(physics, "quiet_until_t") and physics.quiet_until_t is not None:
                quiet = time_s < physics.quiet_until_t

            print(
                f"[DEBUG {time_s:7.2f}s] "
                f"in_ready={in_ready} "
                f"ready_dur={ready_dur:4.2f}s | "
                f"v_raw={v_raw:6.2f} "
                f"v_score={v_score:4.2f} "
                f"v_max={v_max:4.2f} | "
                f"trophy={trophy_conf:4.2f} "
                f"t_max={t_max:4.2f} | "
                f"serve_score={serve_score:4.2f} "
                f"quiet={quiet}"
            )
        # ----------------------------------------------
        # Show
        # ----------------------------------------------
        if event == "serve_start":
            print(f"[{time_s:0.3f}s] EVENT: serve_start")

        cv2.imshow("Serve Detection Demo", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    csv_file.close()
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()