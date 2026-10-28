"""
Motion detection module using MOG2 background subtraction with advanced illumination filtering.
Filters out global brightness shifts (lights turning on/off, sunbeams, webcam auto-exposure)
while preserving sensitivity to moving human bodies.
"""

from typing import List, Tuple
import cv2
import numpy as np


class MotionDetector:
    def __init__(
        self,
        min_area: int = 3500,
        max_area_ratio: float = 0.50,
        var_threshold: int = 25,
        history: int = 500,
        detect_shadows: bool = True,
        lighting_delta_threshold: float = 12.0,
    ):
        """
        Initialize the motion detector.

        :param min_area: Minimum contour area in pixels to trigger a motion detection.
        :param max_area_ratio: Maximum proportion of image area (0.0 - 1.0) allowed for valid motion.
                               If motion exceeds this ratio (e.g. 50%), it is treated as a lighting change.
        :param var_threshold: Variance threshold for pixel background model (lower = more sensitive).
        :param history: Number of past frames used to build the background model.
        :param detect_shadows: If True, shadows are marked as gray (127) and filtered out.
        :param lighting_delta_threshold: Jump in average frame brightness (0-255) indicating a sudden light change.
        """
        self.min_area = int(min_area)
        self.max_area_ratio = float(max_area_ratio)
        self.lighting_delta_threshold = float(lighting_delta_threshold)
        self.subtractor = cv2.createBackgroundSubtractorMOG2(
            history=history,
            varThreshold=var_threshold,
            detectShadows=detect_shadows,
        )
        self.kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        self.prev_mean_brightness: float | None = None

    def detect(self, frame: np.ndarray) -> Tuple[bool, List[Tuple[int, int, int, int]], float, bool]:
        """
        Analyze a frame for motion with sudden illumination change rejection.

        :param frame: BGR image from the camera.
        :return: (is_motion, list_of_bounding_boxes, max_contour_area, is_lighting_change)
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
            proc_w, proc_h = w, h

        # Apply Gaussian blur to reduce noise
        gray = cv2.cvtColor(proc_frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (21, 21), 0)

        # Track global mean brightness to detect sudden light switch or auto-exposure shift
        current_mean = float(np.mean(blurred))
        delta_brightness = 0.0
        if self.prev_mean_brightness is not None:
            delta_brightness = abs(current_mean - self.prev_mean_brightness)
        self.prev_mean_brightness = current_mean

        # Apply background subtractor
        fg_mask = self.subtractor.apply(blurred)

        # Filter out shadows (shadows are marked as 127 in MOG2, foreground is 255)
        _, thresh = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)

        total_pixels = proc_w * proc_h
        fg_pixels = np.count_nonzero(thresh)
        fg_ratio = fg_pixels / total_pixels

        # Check for global lighting change (e.g. room light switched on/off or cloud passing)
        if fg_ratio > self.max_area_ratio or (delta_brightness > self.lighting_delta_threshold and fg_ratio > 0.20):
            # Fast adapt background model to new light level so camera settles immediately
            self.subtractor.apply(blurred, learningRate=0.3)
            return False, [], 0.0, True

        # Dilate mask to merge nearby motion components and fill holes
        dilated = cv2.dilate(thresh, self.kernel, iterations=2)

        # Find external contours
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        bounding_boxes: List[Tuple[int, int, int, int]] = []
        max_area = 0.0
        is_motion = False

        # Scale factor adjustment for contour area
        area_scale = (1.0 / scale) ** 2 if scale != 1.0 else 1.0
        max_allowed_area = (total_pixels * area_scale) * self.max_area_ratio

        for contour in contours:
            area = cv2.contourArea(contour) * area_scale
            if self.min_area <= area <= max_allowed_area:
                x, y, cw, ch = cv2.boundingRect(contour)
                # Ignore contour if its bounding box spans almost the whole frame (screen flash)
                if cw < 0.85 * proc_w or ch < 0.85 * proc_h:
                    is_motion = True
                    if scale != 1.0:
                        inv_s = 1.0 / scale
                        bounding_boxes.append((int(x * inv_s), int(y * inv_s), int(cw * inv_s), int(ch * inv_s)))
                    else:
                        bounding_boxes.append((x, y, cw, ch))

                    if area > max_area:
                        max_area = area

        return is_motion, bounding_boxes, max_area, False
