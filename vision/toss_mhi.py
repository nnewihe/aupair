
import cv2
import numpy as np
from typing import List, Tuple, Optional

def create_toss_roi(player_box: Tuple[int, int, int, int], frame_shape: Tuple[int, int]) -> Tuple[int, int, int, int]:
    """
    Creates a region of interest (ROI) above the player's head for toss detection.

    Args:
        player_box: A tuple (x1, y1, x2, y2) representing the player's bounding box.
        frame_shape: A tuple (height, width) of the video frame.

    Returns:
        A tuple (x1, y1, x2, y2) representing the ROI.
    """
    x1, y1, x2, y2 = player_box
    player_height = y2 - y1
    player_width = x2 - x1

    # Define the ROI above the player's head
    roi_x1 = max(0, x1 - player_width // 2)
    roi_y1 = max(0, y1 - player_height)
    roi_x2 = min(frame_shape[1], x2 + player_width // 2)
    roi_y2 = y1

    return (roi_x1, roi_y1, roi_x2, roi_y2)

class TossDetectorMHI:
    """
    Detects tennis ball tosses on the far side of the court using Motion History Images (MHI).
    """

    def __init__(self, mhi_duration: float = 1.0, fps: float = 30.0, min_toss_area: int = 100, max_toss_area: int = 2000, min_upward_streak: int = 3, roi_size: Tuple[int, int] = (100, 100)):
        """
        Initializes the MHI-based toss detector.

        Args:
            mhi_duration: The duration of the motion history in seconds.
            fps: The frames per second of the video.
            min_toss_area: The minimum area of a toss contour.
            max_toss_area: The maximum area of a toss contour.
            min_upward_streak: The minimum number of consecutive upward movements to detect a toss.
            roi_size: The fixed size of the region of interest.
        """
        self.mhi_duration = mhi_duration
        self.fps = fps
        self.history_length = int(mhi_duration * fps)
        self.mhi = None
        self.prev_frame = None
        self.min_toss_area = min_toss_area
        self.max_toss_area = max_toss_area
        self.min_upward_streak = min_upward_streak
        self.centroid_history = []
        self.upward_streak = 0
        self.roi_size = roi_size

    def _update_mhi(self, frame_gray: np.ndarray) -> Optional[np.ndarray]:
        """
        Updates the Motion History Image (MHI) with the current frame.

        Args:
            frame_gray: The current grayscale frame.

        Returns:
            The updated MHI, or None if this is the first frame.
        """
        if self.prev_frame is None:
            self.prev_frame = frame_gray
            self.mhi = np.zeros_like(frame_gray, dtype=np.float32)
            return None, None

        frame_diff = cv2.absdiff(frame_gray, self.prev_frame)
        _, motion_mask = cv2.threshold(frame_diff, 30, 255, cv2.THRESH_BINARY)

        timestamp = cv2.getTickCount() / cv2.getTickFrequency()
        cv2.motempl.updateMotionHistory(motion_mask, self.mhi, timestamp, self.mhi_duration)
        
        self.prev_frame = frame_gray.copy()
        return self.mhi, motion_mask

    def detect(self, frame: np.ndarray, player_box: Tuple[int, int, int, int]) -> Tuple[bool, Optional[np.ndarray], List[np.ndarray], Optional[Tuple[int, int, int, int]]]:
        """
        Detects a toss in the current frame.

        Args:
            frame: The current video frame.
            player_box: The bounding box of the player on the far side.

        Returns:
            A tuple containing:
            - True if a toss is detected, False otherwise.
            - The visual MHI (for debugging).
            - A list of valid contours (for debugging).
            - The ROI coordinates (for debugging).
        """
        frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        roi = create_toss_roi(player_box, frame.shape[:2])
        frame_roi = frame_gray[roi[1]:roi[3], roi[0]:roi[2]]

        if frame_roi.size == 0:
            return False, None, [], roi

        frame_roi = cv2.resize(frame_roi, self.roi_size)

        mhi, motion_mask = self._update_mhi(frame_roi)
        if mhi is None:
            return False, None, [], roi

        # Normalize the MHI for visualization and analysis
        h, w = mhi.shape
        timestamp = cv2.getTickCount() / cv2.getTickFrequency()
        visual_mhi = np.uint8(np.clip((mhi - (timestamp - self.mhi_duration)) / self.mhi_duration, 0, 1) * 255)
        
        # Threshold the MHI to get recent motion
        _, recent_motion_mask = cv2.threshold(visual_mhi, 200, 255, cv2.THRESH_BINARY)
        
        # Find contours of motion blobs
        contours, _ = cv2.findContours(recent_motion_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        valid_contours = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if self.min_toss_area < area < self.max_toss_area:
                valid_contours.append(contour)
        
        if not valid_contours:
            self.upward_streak = 0
            return False, visual_mhi, valid_contours, roi

        # Get the centroid of the largest valid contour
        largest_contour = max(valid_contours, key=cv2.contourArea)
        M = cv2.moments(largest_contour)
        if M["m00"] == 0:
            self.upward_streak = 0
            return False, visual_mhi, valid_contours, roi
            
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])

        self.centroid_history.append(cy)
        if len(self.centroid_history) > self.history_length:
            self.centroid_history.pop(0)

        if len(self.centroid_history) > 1:
            # Check for upward movement (decreasing y-coordinate)
            if self.centroid_history[-1] < self.centroid_history[-2]:
                self.upward_streak += 1
            else:
                self.upward_streak = 0
        
        if self.upward_streak >= self.min_upward_streak:
            self.upward_streak = 0 # Reset after detection
            return True, visual_mhi, valid_contours, roi

        return False, visual_mhi, valid_contours, roi

def detect_far_side_toss(
    video_path: str,
    player_boxes: List[Tuple[int, int, int, int, int]], # (frame_idx, x1, y1, x2, y2)
    debug: bool = False,
) -> List[float]:
    """
    Main function to detect far-side tosses in a video.

    Args:
        video_path: The path to the video file.
        player_boxes: A list of player bounding boxes for each frame.
        debug: If True, save a debug video.

    Returns:
        A list of timestamps (in seconds) where a toss is detected.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    detector = TossDetectorMHI(fps=fps)
    toss_times = []
    frame_idx = 0

    writer = None
    if debug:
        debug_video_path = 'far_side_toss_detection_debug_v2.mp4'
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        # Adjust size for side-by-side view
        writer = cv2.VideoWriter(debug_video_path, fourcc, fps, (300, 200))

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        # Find the player box for the current frame
        current_player_box = None
        for box in player_boxes:
            if box[0] == frame_idx:
                current_player_box = box[1:]
                break
        
        if current_player_box:
            detected, visual_mhi, valid_contours, roi = detector.detect(frame, current_player_box)
            if detected:
                time_s = frame_idx / fps
                toss_times.append(time_s)
            
            if debug and writer is not None:
                # Create a composite frame for debugging
                debug_frame = np.zeros((200, 300, 3), dtype=np.uint8)

                # Draw original frame with player box and ROI
                frame_with_boxes = frame.copy()
                x1, y1, x2, y2 = current_player_box
                cv2.rectangle(frame_with_boxes, (x1, y1), (x2, y2), (0, 255, 0), 2)
                if roi:
                    rx1, ry1, rx2, ry2 = roi
                    cv2.rectangle(frame_with_boxes, (rx1, ry1), (rx2, ry2), (255, 0, 0), 2)
                
                # Resize and place on the left
                frame_with_boxes_resized = cv2.resize(frame_with_boxes, (150, 200))
                debug_frame[:, 0:150] = frame_with_boxes_resized

                if visual_mhi is not None:
                    # Draw MHI with contours
                    mhi_frame = cv2.cvtColor(visual_mhi, cv2.COLOR_GRAY2BGR)
                    cv2.drawContours(mhi_frame, valid_contours, -1, (0, 255, 0), 1)
                    
                    # Resize and place on the right
                    mhi_frame_resized = cv2.resize(mhi_frame, (150, 200))
                    debug_frame[:, 150:300] = mhi_frame_resized

                if detected:
                    cv2.putText(debug_frame, "TOSS DETECTED", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                
                writer.write(debug_frame)


        frame_idx += 1

    if writer is not None:
        writer.release()
    cap.release()
    return toss_times

if __name__ == '__main__':
    # This is an example of how you might use this module.
    # You would need to have a way to get player bounding boxes first.
    # For now, we'll just use a placeholder.
    
    # video_path = "path/to/your/far_side_video.mp4"
    # player_boxes = [] # You would load your player boxes here
    
    # if video_path and player_boxes:
    #     toss_times = detect_far_side_toss(video_path, player_boxes)
    #     print("Detected toss times:", toss_times)
    pass
