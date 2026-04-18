import cv2
from ultralytics import YOLO
from filterpy.kalman import KalmanFilter


def get_ball_position(frame, model):

    # model = YOLO("weights/ball/weights/best.pt")

    #0. Define the Kalman Filter
    kf = KalmanFilter(dim_x=4, dim_z=2)
    fps = 30.0 # Hard Code for now, but will change later
    dt = 1.0 / fps
    
    kf.F = np.array([[1, 0, dt, 0], [0, 1, 0, dt], [0, 0, 1, 0], [0, 0, 0, 1]])
    kf.H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]])
    kf.R = np.eye(2) * 10
    kf.Q = np.eye(4) * 0.1
    kf.P = np.eye(4) * 100

    #1. Get prediction from Kalman Filter
    kf.predict()
    pred_x = kf.x[0,0]
    pred_y = kf.x[1,0]
    uncertainty = np.trace(kf.P[:2,:2]) # how unsure the filter is

    #2. Define a dynamic search window (smaller for far side and larger for near side)
    base_size = 100
    perspective_factor = max(0.5, 1.0 - (pred_y / frame.shape[0]))
    margin = int((base_size + uncertainty) * perspective_factor)

    # Define crop boundaries with safety checks
    x1, y1 = max(0, int(pred_x - margin)), max(0, int(pred_y-margin))
    x2, y2 = min(frame.shape[1], int(pred_x + margin)), min(frame.shape[0],int(pred_y+margin))
    window = frame[y1:y2,x1:x2]

    #3. Use SAHI/YOLO only on this small window
    results = model.predict(window)

    if results:
        # DATA Association: if multiple balls, pick the one closest to the predicted center
        best_det = min(results, key=lambda d: dist(d.center, (margin,margin)))

        # Convert crop-coordinates back to full-frame coordinates
        actual_x = x1 + best_det.x
        actual_y = y1 + best_det.y 

        kf.update(actual_x, actual_y)
        return actual_x, actual_y
    else:
        # If missed, KF prediction stays as our best guess
        return None
