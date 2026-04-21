import argparse
import csv
import os

import cv2
import numpy as np

from src.ai.anya_base import AnyaTelemetryProvider, TelemetryFrame
from src.ai.anya_transitions import TransitionEngine


def run_anya_pipeline(video_path, output_path="output.mp4", headless=False, start_frame=0):
    # ── Probe original video properties ───────────────────────────────────
    _probe = cv2.VideoCapture(video_path)
    orig_w   = int(_probe.get(cv2.CAP_PROP_FRAME_WIDTH))
    orig_h   = int(_probe.get(cv2.CAP_PROP_FRAME_HEIGHT))
    orig_fps = _probe.get(cv2.CAP_PROP_FPS)
    _probe.release()
    if orig_fps <= 0 or orig_fps > 300:
        orig_fps = 30.0

    # ── Initialize pipeline components ────────────────────────────────────
    # AnyaTelemetryProvider triggers interactive court selection on init.
    telemetry_provider = AnyaTelemetryProvider(video_path)
    engine = TransitionEngine(fps=telemetry_provider.fps)

    # ── Output video writer (clean original footage, ACTIVE frames only) ──
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, orig_fps, (orig_w, orig_h))

    # ── CSV telemetry writer ───────────────────────────────────────────────
    csv_path = os.path.splitext(output_path)[0] + "_telemetry.csv"
    _CSV_COLS = [
        "point", "frame", "timestamp", "state",
        "time_since_trace", "has_active_trace",
        "energy_bar_mode", "point_energy", "energy_status",
        "ball_count",
    ]
    csv_file   = open(csv_path, "w", newline="")
    csv_writer = csv.DictWriter(csv_file, fieldnames=_CSV_COLS)
    csv_writer.writeheader()

    # ── Main loop ──────────────────────────────────────────────────────────
    cap           = cv2.VideoCapture(video_path)
    point_number  = 0
    frame_in_point = 0

    # Seek to start frame if specified
    if start_frame > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        print(f"[DEBUG] Seeking to frame {start_frame}")

    # --- Updated section within run_anya_pipeline (run_anya.py) ---

    WAITING_STRIDE = 3

    while cap.isOpened():
        success, orig_frame = cap.read()
        if not success:
            break

        # Resize here so `frame` is always defined for the debug display below
        frame = cv2.resize(orig_frame, (960, 540), interpolation=cv2.INTER_LINEAR)

        skip_inference = (
            telemetry_provider.current_state == "WAITING"
            and telemetry_provider.frame_counter % WAITING_STRIDE != 0
            and bool(telemetry_provider.telemetry_history)
        )

        if skip_inference:
            # Advance the counter so timestamps stay continuous
            telemetry_provider.frame_counter += 1
            last = telemetry_provider.telemetry_history[-1]
            telemetry = TelemetryFrame(
                frame_id=telemetry_provider.frame_counter,
                timestamp=telemetry_provider.frame_counter / telemetry_provider.fps,
                state="WAITING",
                near_player_box=last.near_player_box,
                near_player_world=last.near_player_world,
                toss_ball_candidates=[],
                active_ball_candidates=[],
            )
            telemetry_provider.telemetry_history.append(telemetry)
        else:
            telemetry = telemetry_provider.process_frame(frame)

        new_state = engine.evaluate_transitions(
            telemetry_provider.telemetry_history,
            telemetry_provider.current_state,
        )

        if new_state != telemetry_provider.current_state:
            if new_state == "ACTIVE":
                point_number += 1
                frame_in_point = 0
            telemetry_provider.update_state(new_state)

        current_state = telemetry_provider.current_state

        # -- Write output video & CSV during ACTIVE --
        if current_state == "ACTIVE":
            # LABEL THE POINT NUMBER ON THE ORIGINAL FRAME
            cv2.putText(orig_frame, f"Point {point_number}", (50, 100),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.8, (0, 255, 0), 4, cv2.LINE_AA)
            
            writer.write(orig_frame)
            frame_in_point += 1
            _write_csv_row(csv_writer, engine, telemetry, point_number, frame_in_point)

        # ── Debug visualisation (skipped when headless) ────────────────────
        if not headless:
            render_frame(frame, telemetry, current_state, engine,
                         telemetry_provider.exclusion_zones,
                         telemetry_provider.active_zone_polygon)
            debug_panel = render_debug_panel(current_state, engine, telemetry_provider)
            cv2.imshow("Anya Pipeline", frame)
            cv2.imshow("Debug Panel", debug_panel)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    # ── Cleanup ────────────────────────────────────────────────────────────
    cap.release()
    writer.release()
    csv_file.close()
    if not headless:
        cv2.destroyAllWindows()

    print(f"\n[DONE] Output video  : {output_path}")
    print(f"[DONE] Telemetry CSV : {csv_path}")
    print(f"[DONE] Points recorded: {point_number}")


# ── CSV helper ─────────────────────────────────────────────────────────────

def _write_csv_row(csv_writer, engine, telemetry, point_number, frame_in_point):
    """Write pure telemetry state and active transition data."""
    debug = engine.last_active_debug
    
    csv_writer.writerow({
        "point":            point_number,
        "frame":            frame_in_point,
        "timestamp":        round(telemetry.timestamp, 4),
        "state":            telemetry.state,
        "time_since_trace": round(debug.get("time_since_trace", 0.0), 3),
        "has_active_trace": debug.get("has_active_trace", False),
        "energy_bar_mode":  debug.get("energy_bar_mode", False),
        "point_energy":     round(debug.get("point_energy", 1.0), 3),
        "energy_status":    debug.get("energy_status", ""),
        "ball_count":       debug.get("ball_count", 0),
    })


# ── Debug visualisation ────────────────────────────────────────────────────

def render_frame(frame, telemetry, state, engine=None, exclusion_zones=None,
                 active_zone_polygon=None):
    """Debug overlay — state badge, player boxes, balls, exclusion zones, and active polygon."""

    # Draw translucent light-green active-zone polygon in ACTIVE state
    if state == "ACTIVE" and active_zone_polygon is not None:
        overlay = frame.copy()
        cv2.fillPoly(overlay, [active_zone_polygon], (144, 238, 144))   # light green (BGR)
        cv2.addWeighted(overlay, 0.20, frame, 0.80, 0, frame)
        cv2.polylines(frame, [active_zone_polygon], True, (0, 200, 0), 1)

    color = (0, 255, 0) if state == "ACTIVE" else (0, 255, 255)
    cv2.putText(frame, f"STATE: {state}", (50, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)

    # Near player — blue box
    if telemetry.near_player_box:
        x1, y1, x2, y2 = telemetry.near_player_box
        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)

    # Far player — pink box (ACTIVE only)
    if state == "ACTIVE" and telemetry.far_player_box:
        x1, y1, x2, y2 = telemetry.far_player_box
        cv2.rectangle(frame, (x1, y1), (x2, y2), (180, 105, 255), 2)   # pink (BGR)
        cv2.putText(frame, "FAR", (x1, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 105, 255), 1, cv2.LINE_AA)

    # Draw red bounding boxes for exclusion zones
    if exclusion_zones:
        for x1, y1, x2, y2 in exclusion_zones:
            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 0, 255), 2)

    # Draw yellow zone box for ARMED phase
    if state == "ARMED" and telemetry.z_box:
        x1, y1, x2, y2 = telemetry.z_box
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)

    # Draw green bounding boxes around detected balls
    if state == "ARMED" and telemetry.toss_ball_candidates:
        for ball in telemetry.toss_ball_candidates:
            bx1, by1, bx2, by2 = ball["box"]
            cv2.rectangle(frame, (int(bx1), int(by1)), (int(bx2), int(by2)), (0, 255, 0), 2)

    if state == "ACTIVE" and engine is not None:
        # ── Ball trace (fading orange trail) ──────────────────────────────
        trace = list(engine._ball_trace_pixels)
        n = len(trace)
        if n >= 2:
            for i in range(1, n):
                age = i / (n - 1)          # 0 = oldest segment end, 1 = newest
                color = (0, int(120 * age), int(255 * age))   # dark → orange (BGR)
                thickness = max(1, int(3 * age))
                pt1 = (int(trace[i - 1][0]), int(trace[i - 1][1]))
                pt2 = (int(trace[i][0]),     int(trace[i][1]))
                cv2.line(frame, pt1, pt2, color, thickness, cv2.LINE_AA)
        if n >= 1:
            tip = (int(trace[-1][0]), int(trace[-1][1]))
            cv2.circle(frame, tip, 5, (0, 200, 255), -1, cv2.LINE_AA)   # bright orange dot

        # ── Current-frame ball detections ─────────────────────────────────
        if telemetry.active_ball_candidates:
            for ball in telemetry.active_ball_candidates:
                bx1, by1, bx2, by2 = ball["box"]
                cv2.rectangle(frame, (int(bx1), int(by1)), (int(bx2), int(by2)),
                              (0, 255, 255), 2)   # cyan box around live detection


def render_debug_panel(state, engine, telemetry_provider):
    """
    Create a debug visualization panel showing timeout status and serve scores.
    Returns an image to display in a separate window.
    """
    panel_width, panel_height = 500, 300
    panel = np.ones((panel_height, panel_width, 3), dtype=np.uint8) * 240  # Light gray bg

    if state == "ACTIVE":
        render_active_debug(panel, engine)
    elif state == "ARMED":
        render_armed_debug(panel, engine)
    else:
        cv2.putText(panel, "WAITING FOR PLAYER", (10, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (80, 80, 80), 1)

    return panel


def render_active_debug(panel, engine):
    """
    Visualizes the hybrid ball-trace / energy-bar state for ACTIVE -> WAITING.
    """
    x0, y, lh = 15, 35, 30
    fs = 0.5

    cv2.putText(panel, "ACTIVE — BALL TRACE / ENERGY BAR", (x0, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (50, 50, 50), 2)

    d = engine.last_active_debug

    # 1. Active ball trace
    has_trace = d.get("has_active_trace", False)
    tst       = d.get("time_since_trace", 0.0)
    trace_color = (0, 180, 0) if has_trace else (0, 0, 200)
    trace_label = "YES" if has_trace else f"NO  ({tst:.1f}s ago)"
    cv2.putText(panel, f"Active Trace: {trace_label}",
                (x0, y), cv2.FONT_HERSHEY_SIMPLEX, fs, trace_color, 1)
    y += lh


    # 2. Energy bar (shown when active, greyed out when trace is present)
    energy_mode = d.get("energy_bar_mode", False)
    energy      = d.get("point_energy", 1.0)
    status      = d.get("energy_status", "--")

    bar_label = "ENERGY BAR" if energy_mode else "Energy (dormant)"
    bar_color = (0, 180, 0) if not energy_mode else (
        (0, 0, 220) if energy < 0.3 else (0, 165, 255) if energy < 0.6 else (0, 200, 0)
    )
    cv2.putText(panel, f"{bar_label}: {energy:.2f}  [{status}]",
                (x0, y), cv2.FONT_HERSHEY_SIMPLEX, fs, bar_color, 2 if energy_mode else 1)
    y += 6

    # Energy bar graphic (only meaningful in energy bar mode)
    bar_w   = 200
    bar_x   = x0
    bar_y   = y
    bg_col  = (180, 180, 180) if not energy_mode else (100, 100, 100)
    cv2.rectangle(panel, (bar_x, bar_y), (bar_x + bar_w, bar_y + 14), bg_col, -1)
    if energy_mode and energy > 0:
        fill_col = (0, 0, 220) if energy < 0.3 else (0, 165, 255) if energy < 0.6 else (0, 200, 0)
        cv2.rectangle(panel, (bar_x, bar_y), (bar_x + int(energy * bar_w), bar_y + 14), fill_col, -1)
    y += 24

    # 3. Ball count
    ball_count = d.get("ball_count", 0)
    cv2.putText(panel, f"Balls detected: {ball_count}",
                (x0, y), cv2.FONT_HERSHEY_SIMPLEX, fs, (80, 80, 80), 1)


def render_armed_debug(panel, engine):
    """Render serve scores during ARMED state."""
    x0      = 12
    bar_w   = 200
    bar_h   = 14
    lh      = 30
    label_w = 110

    cv2.putText(panel, "ARMED  —  Serve Detection", (x0, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 2, cv2.LINE_AA)

    scores = engine.last_serve_scores
    rows = [
        ("Trophy Score", scores.get("trophy_score", 0.0), (0, 120, 255)),
        ("Toss Score",   scores.get("toss_score",   0.0), (0, 200, 200)),
        ("Serve Score",  scores.get("serve_score",  0.0), None),
    ]

    y = 65
    for label, value, color in rows:
        if color is None:
            color = (0, 220, 0) if value >= 0.55 else (0, 140, 255)
        cv2.putText(panel, f"{label}:", (x0, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (20, 20, 20), 1, cv2.LINE_AA)
        bx = x0 + label_w
        cv2.rectangle(panel, (bx, y - bar_h + 2), (bx + bar_w, y + 2), (190, 190, 190), -1)
        cv2.rectangle(panel, (bx, y - bar_h + 2), (bx + int(value * bar_w), y + 2), color, -1)
        cv2.putText(panel, f"{value:.3f}", (bx + bar_w + 6, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
        if label == "Serve Score":
            thresh_x = bx + int(0.55 * bar_w)
            cv2.line(panel, (thresh_x, y - bar_h + 2), (thresh_x, y + 2), (0, 0, 0), 2)
        y += lh


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Anya Tennis Point Detection Pipeline"
    )
    parser.add_argument(
        "input",
        help="Path to input video file",
    )
    parser.add_argument(
        "--output",
        default="output.mp4",
        help="Path to output MP4 file (default: output.mp4)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without displaying video windows",
    )
    parser.add_argument(
        "--start-frame",
        type=int,
        default=0,
        help="Start processing from this frame number (default: 0)",
    )
    args = parser.parse_args()
    run_anya_pipeline(args.input, args.output, args.headless, args.start_frame)