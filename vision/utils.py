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

