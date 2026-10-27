"""
Motion detection module using MOG2 background subtraction.
Optimized for low CPU usage with image downscaling, Gaussian blur, and shadow filtering.
"""

from typing import List, Tuple
import cv2
import numpy as np


class MotionDetector:
    def __init__(
        self,
        min_area: int = 1500,
        var_threshold: int = 25,
        history: int = 500,
        detect_shadows: bool = True,
    ):
        """
        Initialize the motion detector.

        :param min_area: Minimum contour area in pixels to trigger a motion detection.
        :param var_threshold: Variance threshold for pixel background model (lower = more sensitive).
        :param history: Number of past frames used to build the background model.
        :param detect_shadows: If True, shadows are marked as gray (127) and filtered out.
        """
        self.min_area = int(min_area)
        self.subtractor = cv2.createBackgroundSubtractorMOG2(
            history=history,
            varThreshold=var_threshold,
            detectShadows=detect_shadows,
        )
        self.kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))

    def detect(self, frame: np.ndarray) -> Tuple[bool, List[Tuple[int, int, int, int]], float]:
        """
        Analyze a frame for motion.

        :param frame: BGR image from the camera.
        :return: (is_motion, list_of_bounding_boxes, max_contour_area)
                 where bounding_box is (x, y, w, h) in the original frame coordinates.
        """
        h, w = frame.shape[:2]

        # Downscale for faster processing if frame is large
        scale = 1.0
        if w > 640:
            scale = 640.0 / w
            proc_w, proc_h = int(w * scale), int(h * scale)
            proc_frame = cv2.resize(frame, (proc_w, proc_h), interpolation=cv2.INTER_LINEAR)
        else:
            proc_frame = frame

        # Apply Gaussian blur to reduce noise
        gray = cv2.cvtColor(proc_frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (21, 21), 0)

        # Apply background subtractor
        fg_mask = self.subtractor.apply(blurred)

        # Filter out shadows (shadows are marked as 127 in MOG2, foreground is 255)
        _, thresh = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)

        # Dilate mask to merge nearby motion components and fill holes
        dilated = cv2.dilate(thresh, self.kernel, iterations=2)

        # Find external contours
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        bounding_boxes: List[Tuple[int, int, int, int]] = []
        max_area = 0.0
        is_motion = False

        # Scale factor adjustment for contour area
        area_scale = (1.0 / scale) ** 2 if scale != 1.0 else 1.0

        for contour in contours:
            area = cv2.contourArea(contour) * area_scale
            if area > max_area:
                max_area = area

            if area >= self.min_area:
                is_motion = True
                x, y, cw, ch = cv2.boundingRect(contour)
                if scale != 1.0:
                    inv_s = 1.0 / scale
                    bounding_boxes.append((int(x * inv_s), int(y * inv_s), int(cw * inv_s), int(ch * inv_s)))
                else:
                    bounding_boxes.append((x, y, cw, ch))

        return is_motion, bounding_boxes, max_area
