"""
Sample script for detecting serves from video using serve_physics.py

Requirements:
- opencv-python
- numpy
- serve_physics.py in same directory
- (optional) YOLO model for player & ball detection
"""

import cv2, pathlib, sys, time
import numpy as np
from dataclasses import dataclass
from typing import List, Optional, Tuple
import csv
import matplotlib.pyplot as plt




# ---- Robust imports (works as module or script) ----
try:
    from src.vision.court_mask import find_court_mask  # alias of load_or_calibrate
    from src.vision.serve_physics import ServePhysics
    from src.vision.player_debug_overlay import draw_player_state
#    from src.vision.players import PlayerTracker
except ImportError:
    root = pathlib.Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    from src.vision.court_mask import find_court_mask
    from src.vision.serve_physics import ServePhysics
#    from src.vision.players import PlayerTracker


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
    "serve_start"
])
csv_file.flush()

# =====================================================
# YOLO Setup (OPTIONAL — you can hardcode detections)
# =====================================================
use_yolo = True
video_path = "data/matches/2025-10-06/raw_video.mp4"     # <-- set your video path
points_path = "data/matches/2025-09-30/points.csv"
if use_yolo:
    from ultralytics import YOLO
    player_model = YOLO("yolov8n.pt")
    # ball_model   = YOLO("runs/detect/train6/weights/best.pt")
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("Error opening video")


# =====================================================
# Helper functions
# =====================================================


# ====================== Data structures ======================

@dataclass
class PointRecord:
    """Single row from points.csv."""
    index: int
    end_time_s: float          # when the point ENDS, in seconds
    winner: str                # e.g. 'P1' or 'P2' (or player name)
    p1_games: int
    p2_games: int
    p1_pts: int # for scoring purposes, this is the mapping: 0:0,1:15,2:30,3:40,4:AD
    p2_pts: int # note that score is the updated points
    server: Optional[str] = None   # optional, if present in CSV
    raw_score: Optional[str] = None  # e.g. '40-30', 'Ad-40'


@dataclass
class SegmentSpec:
    """Video time bounds and metadata per point."""
    point_idx: int
    segment_start_s: float
    segment_end_s: float
    server_near_side: bool     # True = server on near side, False = far side


# ====================== CSV & scoring helpers ======================

def load_points_csv(csv_path: str) -> List[PointRecord]:
    points: List[PointRecord] = []
    with open(csv_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            idx = int(row.get("index", len(points)))
            end_time_s = float(row["end_time_s"])
            winner = row.get("winner", "")

            # 🔧 Make sure these are integers, not strings
            p1_games = int(row.get("p1_games", 0) or 0)
            p2_games = int(row.get("p2_games", 0) or 0)
            p1_pts   = int(row.get("p1_pts",   0) or 0)
            p2_pts   = int(row.get("p2_pts",   0) or 0)

            server = row.get("server") if "server" in row else None

            points.append(
                PointRecord(
                    index=idx,
                    end_time_s=end_time_s,
                    winner=winner,
                    server=server,
                    p1_games=p1_games,
                    p2_games=p2_games,
                    p1_pts=p1_pts,
                    p2_pts=p2_pts,
                )
            )

    points.sort(key=lambda p: p.end_time_s)
    return points

def compute_server_side_for_points(points: List[PointRecord],
                                   initial_server_near: bool):
    """
    NEW VERSION:
        Returns a list of tuples:
            [(end_time_s, "near" or "far"), ...]
        suitable for serve_side_at_time().
    """

    # ---- normalize initial_server_near to a bool ----
    if isinstance(initial_server_near, str):
        initial_near_bool = (initial_server_near.lower() == "near")
    else:
        initial_near_bool = bool(initial_server_near)

    def tiebreak_server_near(points_played: int, initial_near: bool) -> bool:
        b = points_played // 3
        r = points_played % 3

        if b % 2 == 0:
            original_side = (r == 1)
        else:
            original_side = (r in (1, 2))

        return initial_near if original_side else (not initial_near)

    ### CHANGED: renamed output from server_side (list of bools)
    ###           to side_list (list of tuples)
    side_list = []       # NEW

    for p in points:
        games_played  = p.p1_games + p.p2_games
        points_played = p.p1_pts   + p.p2_pts

        ### CHANGED: compute side_bool first, then convert to "near"/"far"
        # ------------------------------------------------------------------

        # ---- 1) Tiebreak ----
        if games_played == 12:
            side_bool = tiebreak_server_near(points_played, initial_near_bool)

        # ---- 2) Edge cases: first point of games ----
        elif points_played == 0 and games_played in {2, 6, 10}:
            side_bool = initial_near_bool
        elif points_played == 0 and games_played in {4, 8, 12}:
            side_bool = not initial_near_bool

        # ---- 3) Normal games ----
        elif games_played in {0, 1, 4, 5, 8, 9}:
            side_bool = initial_near_bool
        elif games_played in {2, 3, 6, 7, 10, 11}:
            side_bool = not initial_near_bool

        else:
            # Fallback
            side_bool = initial_near_bool

        ### CHANGED: convert bool → "near"/"far"
        side_str = "near" if side_bool else "far"     # NEW

        ### CHANGED: append (end_time, side_str) instead of bool
        side_list.append((p.end_time_s, side_str))    # NEW

    ### CHANGED: return side_list, not list of bools
    return side_list                                   # NEW

def compute_px_per_ft_poly(corners):
    # corners: [[p,q],[r,s],[t,u],[v,w]]
    TL, TR, BR, BL = corners
    
    # Extract y-values
    top_y = (TL[1] + TR[1]) / 2.0
    bottom_y = (BL[1] + BR[1]) / 2.0
    
    # Pixel width of court at top and bottom
    top_width_px = np.linalg.norm(np.array(TR) - np.array(TL))
    bottom_width_px = np.linalg.norm(np.array(BR) - np.array(BL))
    
    # Feet width of singles court
    ft_width = 36.0
    
    # px per ft at top and bottom
    ppf_top = top_width_px / ft_width
    ppf_bottom = bottom_width_px / ft_width
    
    # Compute linear polynomial: ppf(y) = a*y + b
    a = (ppf_bottom - ppf_top) / (bottom_y - top_y)
    b = ppf_top - a * top_y
    
    return np.poly1d([a, b])

def run_yolo_players(frame):
    results = player_model(frame, verbose=False)[0]
    boxes = []
    for b in results.boxes:
        if int(b.cls[0]) == 0:  # ensure only 'person'
            x1, y1, x2, y2 = b.xyxy[0].tolist()
            boxes.append([x1, y1, x2, y2])
    return boxes

def run_yolo_ball(frame):
    """Return (x,y) of ball center or None"""
    results = ball_model(frame, verbose=False)[0]
    if len(results.boxes) == 0:
        return None
    b = results.boxes[0]
    x1, y1, x2, y2 = b.xyxy[0].tolist()
    return (0.5*(x1+x2), 0.5*(y1+y2))

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
        return 1e9  # avoid division by zero

    return cross / denom

def serve_side_at_time (side_list, current_time):
    
     # Ensure the list is sorted by switch time
    side_list = sorted(side_list, key=lambda s: s[0])

    # ================================================
    # Initialize serve side as near
    serve_side = 'near'

    for side_row in side_list:
        if current_time > side_row[0]:
            serve_side = side_row[1]
        else:
            break
    return serve_side




# =====================================================
# MAIN
# =====================================================

def main():

    # =====================================================
    # Load your court polynomial (dummy example below)
    # Replace this with your actual poly
    # =====================================================
    # Example poly: ppf = a0 + a1*y + a2*y^2 ...

    # 1) Calibrate/load court mask & polygon
    res = find_court_mask(
        video_path=video_path,
        poly_json_path="data/court_poly.json",
        mask_playable_out="data/court_mask_playable.png",
        mask_extended_out="data/court_mask_extended.png",
        n_vertices=4,
        extend_px=0,
    )


    playable_mask = res.playable_mask
    extended_mask = res.extended_mask if res.extended_mask is not None else playable_mask
    court_poly    = res.poly
    poly = compute_px_per_ft_poly(court_poly)

    # Prepare physics engine
    court_vertices = res.poly   # same data used to compute px/ft poly
    physics = ServePhysics(poly, court_vertices)
    
    # For dt calculation
    prev_time_s = None

    print("\nStarting serve detection...\n")

    # TODO: Implement Near and Far Side From CSV

    #2) Load the points from the record
    points = load_points_csv(points_path)
    if not points:
        print("[error] No points found in CSV.")
        return 1
    side_list = compute_server_side_for_points(points, True) # (assume serve starts at near side)

    debug_far = True

    # =====================================================
    # Logging arrays for plotting
    # =====================================================
    times = []
    cy_ft_list = []
    v_cy_ftps_list = []
    ready_mask = []        # True/False for highlighting ready periods
    serve_start_times = []
    frame_idx = 0
    
    while True:
        ok, frame = cap.read()

        if not ok:
            break
        

        # OpenCV timestamp
        time_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
        time_s = time_ms / 1000.0
        serve_side = serve_side_at_time(side_list,time_s)

        # For Debugging, set serve_side to near
        serve_side = 'near'


        # ----------------------------------------------
        # 1. PLAYER DETECTION
        # ----------------------------------------------
        if use_yolo:
            boxes = run_yolo_players(frame)
        else:
            # DUMMY single player box — replace with your tracker
            H, W = frame.shape[:2]
            boxes = [[0.3*W, 0.3*H, 0.6*W, 0.9*H]]

        # If no boxes, skip
        if len(boxes) == 0:
            continue

        # ----------------------------------------------
        # SELECT CORRECT SERVER SIDE BY BASELINE DISTANCE
        # ----------------------------------------------

        # ------ FIX VERTEX ORDER ------
        # sort vertices by y position (top two first)
        sorted_by_y = sorted(court_vertices, key=lambda p: p[1])
        top_two    = sorted_by_y[:2]
        bottom_two = sorted_by_y[2:]

        # enforce left-right order
        TL, TR = sorted(top_two, key=lambda p: p[0])
        BL, BR = sorted(bottom_two, key=lambda p: p[0])
        # --------------------------------R

        serve_candidates = []

        for box in boxes:
            x1, y1, x2, y2 = box
            cx = 0.5 * (x1 + x2)
            y_feet = y2
            P = (cx, y_feet)

            # Distance (in pixels) to top and bottom baselines
            dist_top = point_line_distance_px(P, TL, TR)
            dist_bottom = point_line_distance_px(P, BL, BR)

            if serve_side == 'near':
                # Player must be closer to NEAR (bottom) baseline
                if dist_bottom < dist_top:
                    serve_candidates.append((box, dist_bottom))
            else:
                if dist_bottom > dist_top:
                    serve_candidates.append((box, dist_bottom))

        # If no candidates detected, skip frame
        if len(serve_candidates) == 0:
            continue

        # Pick player closest to baseline of choice
        # TODO: eventually I want to distinguish near from far as the serve physics would be different for each case
        player_box = min(serve_candidates, key=lambda x: x[1])[0]


        # ----------------------------------------------
        # 2. BALL DETECTION
        # ----------------------------------------------
        """
        if use_yolo:
            ball_xy = run_yolo_ball(frame)
        else:
            ball_xy = None  # optional for serve_start
        """
        # ----------------------------------------------
        # 3. PHYSICS UPDATE
        # ----------------------------------------------
        p_state = physics.update_player(player_box, time_s)
        # Draw player physics state on video
        frame = draw_player_state(frame, player_box, p_state, label="P1")

        # ---- center of mass ----
        x1, y1, x2, y2 = player_box
        cx_px = 0.5 * (x1 + x2)
        cy_px = y2  # feet position

        # physics output
        cy_ft = p_state.sm_cy_ft
        vcy = p_state.v_cy_ftps
        in_ready = 1 if p_state.in_ready else 0

        # serve events (1 only on the exact frame)
        serve_start_flag = 1 if p_state == "serve_start" else 0

        # ---- WRITE TO CSV ----
        csv_writer.writerow([
            time_s,
            cx_px, cy_px,
            cy_ft,
            vcy,
            in_ready,
            serve_start_flag
        ])
        csv_file.flush()

        # ----------------------------------------------
        # LOGGING FOR PLOTTING
        # ----------------------------------------------
        times.append(time_s)
        cy_ft_list.append(p_state.sm_cy_ft if p_state.sm_cy_ft is not None else 0)
        v_cy_ftps_list.append(p_state.v_cy_ftps)
        ready_mask.append(p_state.in_ready)

        b_state = None
        # if ball_xy is not None:
        #     b_state = physics.update_ball(ball_xy, time_s)

        # ----------------------------------------------
        # 4. SERVE DETECTION
        # ----------------------------------------------
        event = physics.detect_serve(p_state, time_s)
        if event:
            print(f"[{time_s:0.3f}s] EVENT: {event}")
            if event == "serve_start":
                serve_start_times.append(time_s)

        # ----------------------------------------------
        # 5. Show demo window (optional)
        # ----------------------------------------------
        cv2.rectangle(frame,
                    (int(player_box[0]), int(player_box[1])),
                    (int(player_box[2]), int(player_box[3])),
                    (0,255,0), 2)
        #cv2.putText(frame, f"Energy={p_state.swing_energy_up:.2f}",
        #            (20,40), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
        #            (0,255,0), 2)

        cv2.imshow("Serve Detection Demo", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # Clean Up #################################       
    csv_file.close()
    cap.release()
    cv2.destroyAllWindows()

    # =====================================================
    # PLOTTING SECTION
    # =====================================================
    print("Generating physics plot...")

    times_np = np.array(times)
    cy_np = np.array(cy_ft_list)
    vel_np = np.array(v_cy_ftps_list)
    ready_np = np.array(ready_mask)

    # --- Create Plot ---
    plt.figure(figsize=(15, 8))

    # Plot COM vertical position
    plt.plot(times_np, cy_np, label="COM Position (ft)", color='blue')

    # Plot velocity
    plt.plot(times_np, vel_np, label="Vertical Velocity (ft/s)", color='green')

    # Highlight ready-state periods
    for i in range(len(times_np)):
        if ready_np[i]:
            plt.axvspan(times_np[i], times_np[i]+0.03, color='red', alpha=0.15)

    # Plot serve_start markers
    for t in serve_start_times:
        plt.axvline(t, color='red', linestyle='--', linewidth=1.5)
        plt.scatter(t, 0, color='red', s=60, marker='o', label='Serve Start')

    plt.xlabel("Time (s)")
    plt.ylabel("Feet / ft/s")
    plt.title("Player COM Position & Velocity with Ready State + Serve Start Markers")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()

    


if __name__ == "__main__":
    main()