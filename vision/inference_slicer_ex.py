import cv2
import supervision as sv
from ultralytics import YOLO
import numpy as np

image = cv2.imread('data/tennis_ball/2025-12-27_frame_1930.jpg')
model = YOLO('weights/ball/weights/best.pt')

def callback(image_slice: np.ndarray) -> sv.Detections:
    result = model(image_slice)[0]
    return sv.Detections.from_ultralytics(result)

slicer = sv.InferenceSlicer(callback = callback)

detections = slicer(image)

# Annotate the image
box_annotator = sv.BoxAnnotator(
    thickness=2
)
annotated_frame = box_annotator.annotate(
    scene=image.copy(),
    detections=detections
)

# Display the annotated image
sv.plot_image(annotated_frame, (8, 8))