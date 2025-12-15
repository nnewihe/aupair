# player_debug_overlay.py
# Draws player physics debug information on screen

import cv2

def draw_player_state(frame, box, state, label="PLAYER"):
    """
    Draws:
        - Bounding box
        - Ready status
        - Swing energy
        - Vertical velocity
        - Time in ready position
        - Raw vs smoothed vertical position

    box: [x1,y1,x2,y2]
    state: PlayerPhysicsState
    """

    if box is None or state is None:
        return frame

    x1, y1, x2, y2 = map(int, box)

    # Draw bounding box
    cv2.rectangle(frame, (x1, y1), (x2, y2), (0,255,0), 2)

    # Base text position
    tx = x1
    ty = y1 - 10
    dy = 18

    # Debug text lines
    lines = [
        f"{label}",
        f"READY: {state.in_ready}",
        f"ready_time: {state.ready_duration_s:.2f}s",
        f"v_cy_ftps: {state.v_cy_ftps:.2f}",
        f"cy_ft_sm: {state.sm_cy_ft:.2f}",
    ]

    # Draw each line
    for line in lines:
        cv2.putText(frame, line, (tx, ty),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    (255,255,255), 2)
        ty += dy

    return frame