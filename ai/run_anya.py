import cv2
import numpy as np
from src.ai.anya_base import AnyaTelemetryProvider
from src.ai.anya_transitions import TransitionEngine

def run_anya_pipeline(video_path):
    # 1. Initialize the components
    # This will trigger the interactive court selection (init_court) 
    # and analyze frame 300 for exclusion zones.
    telemetry_provider = AnyaTelemetryProvider(video_path)
    
    # Initialize the transition engine with the video's FPS
    engine = TransitionEngine(fps=telemetry_provider.fps)
    
    cap = cv2.VideoCapture(video_path)
    
    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            break

        # Resample frame to 960x540
        frame = cv2.resize(frame, (960, 540), interpolation=cv2.INTER_LINEAR)

        # 2. Process the frame to get telemetry
        # This runs the appropriate detectors based on the current state
        telemetry = telemetry_provider.process_frame(frame)

        # 3. Evaluate transitions using the 5-second buffer
        # We pass the rolling history and current state to the engine
        new_state = engine.evaluate_transitions(
            telemetry_provider.telemetry_history, 
            telemetry_provider.current_state
        )
        
        # 4. Update the provider's state if a transition occurred
        if new_state != telemetry_provider.current_state:
            telemetry_provider.update_state(new_state)

        # 5. Optional: Visualization for debugging
        render_frame(frame, telemetry, telemetry_provider.current_state, engine,
                     telemetry_provider.exclusion_zones,
                     telemetry_provider.active_zone_polygon)

        # 6. Debug panel in separate window
        debug_panel = render_debug_panel(telemetry_provider.current_state, engine, telemetry_provider)

        cv2.imshow("Anya Pipeline", frame)
        cv2.imshow("Debug Panel", debug_panel)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
            
    cap.release()
    cv2.destroyAllWindows()

def render_frame(frame, telemetry, state, engine=None, exclusion_zones=None,
                 active_zone_polygon=None):
    """Debug overlay — state badge, player box, balls, exclusion zones, and active polygon."""

    # Draw translucent light-green active-zone polygon in ACTIVE state
    if state == "ACTIVE" and active_zone_polygon is not None:
        overlay = frame.copy()
        cv2.fillPoly(overlay, [active_zone_polygon], (144, 238, 144))   # light green (BGR)
        cv2.addWeighted(overlay, 0.20, frame, 0.80, 0, frame)
        cv2.polylines(frame, [active_zone_polygon], True, (0, 200, 0), 1)

    color = (0, 255, 0) if state == "ACTIVE" else (0, 255, 255)
    cv2.putText(frame, f"STATE: {state}", (50, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)

    if telemetry.near_player_box:
        x1, y1, x2, y2 = telemetry.near_player_box
        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)

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

    if state == "ACTIVE" and telemetry.active_ball_candidates:
        for ball in telemetry.active_ball_candidates:
            bx1, by1, bx2, by2 = ball["box"]
            cv2.rectangle(frame, (int(bx1), int(by1)), (int(bx2), int(by2)), (0, 255, 0), 2)

    if (state == "ACTIVE"
            and engine is not None
            and telemetry.player_crop_rect is not None):
        cx1, cy1, cx2, cy2 = telemetry.player_crop_rect
        # engine._gait_analyzer.draw_debug(frame, cx1, cy1, cx2, cy2)

def render_debug_panel(state, engine, telemetry_provider):
    """
    Create a debug visualization panel showing energy and serve scores.
    Returns an image to display in a separate window.
    """
    panel_width, panel_height = 400, 350
    panel = np.ones((panel_height, panel_width, 3), dtype=np.uint8) * 240  # Light gray bg

    if state == "ACTIVE":
        render_active_debug(panel, engine)
    elif state == "ARMED":
        render_armed_debug(panel, engine)
    else:
        # WAITING state
        cv2.putText(panel, "WAITING", (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

    return panel

def render_active_debug(panel, engine):
    """Render energy bar, player and ball contributions during ACTIVE state."""
    # Title
    cv2.putText(panel, "ACTIVE - Energy", (10, 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)

    # Current energy bar
    energy_bar_y = 22
    bar_width = 120
    bar_height = 12
    bar_x = 10

    # Draw background bar
    cv2.rectangle(panel, (bar_x, energy_bar_y), (bar_x + bar_width, energy_bar_y + bar_height),
                  (200, 200, 200), -1)

    # Draw energy fill
    energy_fill = int(engine.point_energy * bar_width)
    cv2.rectangle(panel, (bar_x, energy_bar_y), (bar_x + energy_fill, energy_bar_y + bar_height),
                  (0, 200, 255), -1)  # Cyan

    # Energy value text
    cv2.putText(panel, f"{engine.point_energy:.2f}", (bar_x + bar_width + 5, energy_bar_y + 11),
                cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 0, 0), 1)

    # Individual contributions
    deltas = engine.last_energy_deltas
    y_offset = 42
    line_height = 13
    bar_x = 10
    bar_width = 80
    bar_height = 7

    # Player contributions
    player_scale = deltas.get("player_scale", 1.0)
    player_contributions = [
        ("Spr", deltas.get("sprint_delta", 0.0)),
        ("Act", deltas.get("action_delta", 0.0)),
        ("Wlk", deltas.get("walk_delta", 0.0)),
        ("Gai", deltas.get("gait_delta", 0.0)),
        ("Mis", deltas.get("missing_delta", 0.0)),
        ("Var", deltas.get("variance_delta", 0.0)),
    ]

    for label, delta in player_contributions:
        scaled_delta = delta * player_scale
        color = (0, 255, 0) if scaled_delta > 0 else (0, 0, 255)

        if abs(scaled_delta) > 0.0001:
            bar_len = max(1, int(min(abs(scaled_delta) * 400, bar_width)))
            cv2.rectangle(panel, (bar_x, y_offset), (bar_x + bar_len, y_offset + bar_height),
                          color, -1)

        cv2.putText(panel, f"{label}:{scaled_delta:+.2f}", (bar_x, y_offset + 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.25, (0, 0, 0), 1)
        y_offset += line_height

    # Ball contributions
    y_offset += 4
    ball_scale = deltas.get("ball_scale", 1.0)
    ball_contributions = [
        ("Fast", deltas.get("ball_fast_delta", 0.0)),
        ("Roll", deltas.get("ball_rolling_delta", 0.0)),
        ("Occ", deltas.get("ball_occluded_delta", 0.0)),
        ("Dead", deltas.get("ball_dead_delta", 0.0)),
        ("AZone", deltas.get("ball_action_zone_delta", 0.0)),
    ]

    for label, delta in ball_contributions:
        scaled_delta = delta * ball_scale
        color = (0, 255, 0) if scaled_delta > 0 else (0, 0, 255)

        if abs(scaled_delta) > 0.0001:
            bar_len = max(1, int(min(abs(scaled_delta) * 400, bar_width)))
            cv2.rectangle(panel, (bar_x, y_offset), (bar_x + bar_len, y_offset + bar_height),
                          color, -1)

        cv2.putText(panel, f"{label}:{scaled_delta:+.2f}", (bar_x, y_offset + 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.25, (0, 0, 0), 1)
        y_offset += line_height

def render_armed_debug(panel, engine):
    """Render serve scores during ARMED state."""
    # Title
    cv2.putText(panel, "ARMED - Serve Scores", (10, 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)

    scores = engine.last_serve_scores
    trophy = scores.get("trophy_score", 0.0)
    toss = scores.get("toss_score", 0.0)
    serve = scores.get("serve_score", 0.0)

    # Score bars
    y_offset = 32
    bar_width = 120
    bar_height = 10
    bar_x = 10
    line_height = 22

    # Trophy score
    cv2.putText(panel, "Trophy:", (bar_x, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 0, 0), 1)
    cv2.rectangle(panel, (bar_x + 50, y_offset - 8), (bar_x + 50 + bar_width, y_offset - 8 + bar_height),
                  (200, 200, 200), -1)
    trophy_fill = int(trophy * bar_width)
    cv2.rectangle(panel, (bar_x + 50, y_offset - 8), (bar_x + 50 + trophy_fill, y_offset - 8 + bar_height),
                  (255, 165, 0), -1)  # Orange
    cv2.putText(panel, f"{trophy:.2f}", (bar_x + 50 + bar_width + 5, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 0, 0), 1)

    y_offset += line_height

    # Toss score
    cv2.putText(panel, "Toss:", (bar_x, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 0, 0), 1)
    cv2.rectangle(panel, (bar_x + 50, y_offset - 8), (bar_x + 50 + bar_width, y_offset - 8 + bar_height),
                  (200, 200, 200), -1)
    toss_fill = int(toss * bar_width)
    cv2.rectangle(panel, (bar_x + 50, y_offset - 8), (bar_x + 50 + toss_fill, y_offset - 8 + bar_height),
                  (0, 200, 200), -1)  # Cyan
    cv2.putText(panel, f"{toss:.2f}", (bar_x + 50 + bar_width + 5, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 0, 0), 1)

    y_offset += line_height

    # Combined serve score
    cv2.putText(panel, "Serve:", (bar_x, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 0, 0), 1)
    cv2.rectangle(panel, (bar_x + 50, y_offset - 8), (bar_x + 50 + bar_width, y_offset - 8 + bar_height),
                  (200, 200, 200), -1)
    serve_fill = int(serve * bar_width)
    color = (0, 255, 0) if serve >= 0.55 else (0, 165, 255)  # Green if above threshold, orange otherwise
    cv2.rectangle(panel, (bar_x + 50, y_offset - 8), (bar_x + 50 + serve_fill, y_offset - 8 + bar_height),
                  color, -1)
    cv2.putText(panel, f"{serve:.2f}", (bar_x + 50 + bar_width + 5, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 0, 0), 1)

if __name__ == "__main__":
    run_anya_pipeline("/Users/tennis/Desktop/snippet.mp4")