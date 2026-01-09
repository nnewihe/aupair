import os
import sys
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Tuple

# Ensure the project root is in the Python path
try:
    from src.vision.detect_serves import detect_serve_event_times, _load_point_windows
    from src.vision.utils import extract_subclip, stitch_clips_ffmpeg
    from src.vision.toss_mhi import detect_far_side_toss
    import cv2
except ImportError:
    # If running as a script, add the project root to the path
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    from src.vision.detect_serves import detect_serve_event_times, _load_point_windows
    from src.vision.utils import extract_subclip, stitch_clips_ffmpeg
    from src.vision.toss_mhi import detect_far_side_toss
    import cv2



@dataclass(frozen=True)
class VideoInputs:
    near_video: Path
    far_video: Optional[Path] = None

def run_yolo_players_local(frame):
    from ultralytics import YOLO
    player_model = YOLO("yolov8n.pt")
    
    res0 = player_model(frame, verbose=False)[0]
    out = []
    for b in res0.boxes:
        if int(b.cls[0]) == 0:  # person
            x1, y1, x2, y2 = b.xyxy[0].tolist()
            out.append([int(x1), int(y1), int(x2), int(y2)])
    return out

def detect_serves(video_path: Path, side: str, points_csv_path: Optional[str]) -> List[float]:
    """Wrapper for detect_serve_event_times."""
    return detect_serve_event_times(
        input_video=str(video_path),
        points_csv=points_csv_path if points_csv_path else "",
        near_side_start=side == "near",
        show_ui=True,
    )

def load_point_end_times(points_csv_path: str) -> List[float]:
    """Loads point end times from a CSV file."""
    windows = _load_point_windows(points_csv_path)
    if not windows:
        return []
    return [end for _, end in windows]

def infer_point_segments(serve_times: List[float], point_end_times: List[float]) -> List[Tuple[float, float]]:
    """
    Infers point segments from serve times and point end times.
    Each serve is associated with the next available point end time.
    """
    segments = []
    end_times = sorted(point_end_times)
    
    for serve_time in serve_times:
        # Find the smallest end time that is greater than the serve time
        next_end_time = next((t for t in end_times if t > serve_time), None)
        if next_end_time:
            segments.append((serve_time, next_end_time))
            # Remove the used end time to prevent re-use
            end_times.remove(next_end_time)
            
    return segments

def render_compilation(primary_video: Path, segments: List[Tuple[float, float]], out_path: str) -> str:
    """
    Renders a compilation video from the given segments.
    """
    clip_paths = []
    temp_dir = Path("./temp_clips")
    temp_dir.mkdir(exist_ok=True)

    print(f"Found {len(segments)} segments to compile.")

    for i, (start, end) in enumerate(segments):
        clip_path = temp_dir / f"clip_{i}.mp4"
        print(f"Extracting segment {i+1}/{len(segments)}: {start:.2f}s to {end:.2f}s")
        extract_subclip(str(primary_video), str(clip_path), start, end)
        if clip_path.exists():
            clip_paths.append(str(clip_path))

    if not clip_paths:
        print("No clips were extracted. The output video will be empty.")
        return ""

    print("Stitching clips together...")
    stitch_clips_ffmpeg(clip_paths, out_path, reencode=True)
    
    print("Cleaning up temporary files...")
    for clip_path in clip_paths:
        try:
            os.remove(clip_path)
        except OSError as e:
            print(f"Error removing temporary file {clip_path}: {e}")
    try:
        os.rmdir(temp_dir)
    except OSError as e:
        print(f"Error removing temporary directory {temp_dir}: {e}")


    return out_path

import cv2

def cut_dead_time(near_video: str, far_video: Optional[str] = None, *, detect_both_sides: bool = True, force_detection: bool = False, debug_far_side_toss: bool = False):
    
    videos = VideoInputs(Path(near_video), Path(far_video) if far_video else None)
    
    points_csv_path = videos.near_video.parent / "points.csv"
    points_csv_str = str(points_csv_path) if points_csv_path.exists() else None

    serve_times_far: List[float] = []
    far_video_path = ""
    if detect_both_sides:
        print("Detecting serves on far side...")
        if videos.far_video:
            far_video_path = videos.far_video
        else:
            far_video_path = videos.near_video

        player_boxes_csv = Path(far_video_path).parent / "player_boxes.csv"

        if player_boxes_csv.exists() and not force_detection:
            print(f"Loading player boxes from {player_boxes_csv}...")
            player_boxes = []
            with open(player_boxes_csv, 'r') as f:
                reader = csv.reader(f)
                for row in reader:
                    player_boxes.append(tuple(map(lambda x: int(float(x)), row)))
            print(f"Loaded {len(player_boxes)} player boxes.")
        else:
            print("Running YOLO player detection...")
            cap = cv2.VideoCapture(str(far_video_path))
            if not cap.isOpened():
                raise RuntimeError(f"Could not open video: {far_video_path}")

            player_boxes = []
            frame_idx = 0
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                if frame_idx % 100 == 0:
                    print(f"  Processing frame {frame_idx} for player detection...")
                boxes = run_yolo_players_local(frame)
                if boxes:
                    player_boxes.append((frame_idx, *boxes[0]))
                frame_idx += 1
            cap.release()
            print(f"YOLO player detection complete. Found {len(player_boxes)} player boxes.")

            print(f"Saving player boxes to {player_boxes_csv}...")
            with open(player_boxes_csv, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerows(player_boxes)

        print("Detecting far side tosses...")
        serve_times_far = detect_far_side_toss(str(far_video_path), player_boxes, debug=debug_far_side_toss)
        print(f"Found {len(serve_times_far)} far side tosses.")

    print("Detecting serves on near side...")
    serve_times_near = detect_serves(videos.near_video, side="near", points_csv_path=points_csv_str)
    print(f"Found {len(serve_times_near)} near side tosses.")
    
    serve_times = sorted(serve_times_near + serve_times_far)
    print(f"Total serves detected: {len(serve_times)}")

    print("Loading point end times...")
    point_end_times = load_point_end_times(points_csv_str) if points_csv_str else []
    print(f"Found {len(point_end_times)} point end times.")

    if not point_end_times:
        print("Warning: No point end times found. The resulting video may be empty.")

    print("Inferring point segments...")
    segments = infer_point_segments(serve_times, point_end_times)
    print(f"Inferred {len(segments)} point segments.")

    print("Rendering final compilation...")
    output_mp4 = render_compilation(
        primary_video=videos.near_video,
        segments=segments,
        out_path="final.mp4",
    )
    print("Final compilation rendered.")
    return output_mp4

if __name__ == '__main__':
    # Example usage:
    # python -m src.vision.cut_dead_time
    near_video_path = "data/matches/2025-09-30/short_video.mp4"
    far_video_path = "data/matches/2025-09-30/short_video.mp4"
    
    if not Path(near_video_path).exists():
        print(f"Video file not found: {near_video_path}")
    elif not Path(far_video_path).exists():
        print(f"Video file not found: {far_video_path}")
    else:
        print("Starting to process video to cut dead time...")
        cut_dead_time(near_video_path, far_video=far_video_path, detect_both_sides=True, force_detection=False, debug_far_side_toss=True)
        print("Video processing complete. Output saved to final.mp4")
