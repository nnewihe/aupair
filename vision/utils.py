import numpy as np
import math
import time

# ================================================================
# Utility Functions
# ================================================================

def point_line_distance_px(P, A, B):
    """
    Returns pixel distance from point P to line AB.
    P, A, B are (x,y) tuples.
    """
    Px, Py = P
    Ax, Ay = A
    Bx, By = B

    # Line vector
    ABx = Bx - Ax
    ABy = By - Ay

    # Vector AP
    APx = Px - Ax
    APy = Py - Ay

    # Cross product magnitude
    cross = abs(ABx * APy - ABy * APx)

    # Line length
    denom = math.hypot(ABx, ABy)
    if denom == 0:
        return 0.0

    return cross / denom


def exp_smooth(prev, new, dt, tau):
    """
    Exponential smoothing with time-constant tau (seconds).
    If prev is None, returns new directly.
    """
    if prev is None:
        return new
    if tau <= 0:
        return new
    alpha = min(1.0, dt / tau)
    return (1.0 - alpha) * prev + alpha * new


# Simple wrapper for clarity; poly is already px/ft vs y
def pixels_per_foot(poly, y):
    return float(poly(y))

# ====================== Video helpers ======================

import subprocess
import os

def extract_subclip(video_path: str,
                    out_path: str,
                    t_start: float,
                    t_end: float,
                    ffmpeg_bin: str = "ffmpeg") -> None:
    """
    Extract [t_start, t_end] from video_path into out_path using ffmpeg.

    Uses stream copy (-c copy) for speed. Assumes t_start, t_end are in seconds
    from the beginning of the source video.
    """
    duration = max(0.0, float(t_end) - float(t_start))
    if duration <= 0.0:
        print(f"[warn] extract_subclip: non-positive duration ({duration:.3f}s); skipping {out_path}")
        return

    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    cmd = [
        ffmpeg_bin,
        "-y",                   # overwrite output if it exists
        "-ss", f"{t_start:.3f}",
        "-i", video_path,
        "-t", f"{duration:.3f}",
        "-c", "copy",           # no re-encode, just copy streams
        out_path,
    ]

    print("[ffmpeg extract]", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        print(f"[error] ffmpeg extract_subclip failed for {out_path}")
        print("        return code:", e.returncode)
        # Optionally print stderr for debugging:
        # print(e.stderr.decode("utf-8", errors="ignore"))
        # Make sure we don't leave a half-created file
        if os.path.exists(out_path):
            try:
                os.remove(out_path)
            except OSError:
                pass


import os
import subprocess
import tempfile
from typing import List

def stitch_clips_ffmpeg(
    clip_paths: List[str],
    out_path: str,
    reencode: bool = False,
    ffmpeg_bin: str = "ffmpeg",
) -> None:
    """
    Concatenate clips using ffmpeg concat demuxer.

    - clip_paths: list of input MP4 paths in order.
    - out_path: final stitched MP4 path.
    - reencode=False (default): uses `-c copy` (fast, no re-encode).
      All inputs must share codec/resolution/container.
    - reencode=True: re-encodes to H.264/AAC for maximum compatibility.
    """

    # Filter out missing / empty paths early
    valid_paths = [p for p in clip_paths if p and os.path.exists(p)]
    if not valid_paths:
        raise RuntimeError("No valid input clips to stitch.")

    # Create concat list file for ffmpeg
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tf:
        list_path = tf.name
        for p in valid_paths:
            abs_p = os.path.abspath(p)
            # Escape single quotes for ffmpeg concat file syntax
            esc_p = abs_p.replace("'", r"'\''")
            tf.write(f"file '{esc_p}'\n")

    # Build ffmpeg command
    cmd = [
        ffmpeg_bin,
        "-y",                 # overwrite output
        "-f", "concat",
        "-safe", "0",
        "-i", list_path,
    ]

    if reencode:
        # Slower, but robust: re-encode everything
        cmd += [
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-c:a", "aac",
            "-b:a", "160k",
            "-movflags", "+faststart",
        ]
    else:
        # Fast, no re-encode (requires matching codecs/params)
        cmd += [
            "-c", "copy",
        ]

    cmd.append(out_path)

    try:
        print("[ffmpeg] running:", " ".join(cmd))
        subprocess.run(cmd, check=True)
    finally:
        # Always clean up the temp list file
        try:
            os.remove(list_path)
        except OSError:
            pass

