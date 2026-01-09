import cv2

from sahi import AutoDetectionModel
from sahi.predict import get_prediction, get_sliced_prediction, predict
from sahi.utils.cv import read_image

"""
sahi predict --model_path weights/balls/weights/best.pt --model_type ultralytics --source data/matches/2025-12-27/raw_video.MP4 --view_video

sahi predict --model_path weights/ball/weights/best.pt --model_type ultralytics --source data/matches/2025-12-27/raw_video.MP4 --view_video

from engine.sahi_object_detection import SAHIObjectDetection
"""
# sahi_od = SAHIObjectDetection("weights/balls/weights/best.pt")
detection_model = AutoDetectionModel.from_pretrained(
    model_type="ultralytics",
    model_path="weights/ball/weights/best.pt",  # any yolov8/yolov9/yolo11/yolo12/rt-detr det model is supported
    confidence_threshold=0.1,
    device="cpu",  # or 'cuda:0' if GPU is available
)

cap = cv2.VideoCapture("data/matches/2025-12-27/raw_video.MP4")

while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    # predictions = get_prediction(frame, detection_model,)
    
    predictions = get_sliced_prediction(
    frame,
    detection_model,
    slice_height=1024,
    slice_width=1024,
    overlap_height_ratio=0.2,
    overlap_width_ratio=0.2,
    # perform_standard_pred = False
    )
    predictions.export_visuals(export_dir="demo_data/", hide_conf=True)
    """
    for pred in predictions:
        bbox = pred.bbox
        class_id = pred.category.id 
        score = pred.score.value

        x, y, x2, y2 = bbox.minx, bbox.miny, bbox.maxx, bbox.maxy
        cv2.rectangle(frame, (x,y), (x2,y2), pred.colors[class_id], 3)
    """

    cv2.imshow( "Frame", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break
    
cap.release()
cv2.destroyAllWindows()
