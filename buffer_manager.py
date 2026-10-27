"""
Circular rolling buffer module.
Maintains a sliding time window (e.g. 60 seconds) of camera frames in memory.
Frames are stored compressed in JPEG format to keep memory usage minimal (~50MB for 1 minute).
"""

import threading
import time
from collections import deque
from typing import List, Tuple
import cv2
import numpy as np


class FrameBuffer:
    def __init__(self, max_duration_seconds: float = 60.0, jpeg_quality: int = 85):
        """
        Initialize the circular frame buffer.

        :param max_duration_seconds: Maximum time window in seconds to keep in memory.
        :param jpeg_quality: Quality of JPEG compression (1-100). Higher = better quality, more RAM.
        """
        self.max_duration = float(max_duration_seconds)
        self.jpeg_quality = int(jpeg_quality)
        self._encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
        self._buffer: deque = deque()
        self._lock = threading.Lock()

    def add_frame(self, frame: np.ndarray, timestamp: float | None = None, is_motion: bool = False) -> None:
        """
        Compress and append a frame to the rolling buffer.
        Automatically discards frames older than `max_duration_seconds`.
        """
        if timestamp is None:
            timestamp = time.time()

        success, encoded = cv2.imencode(".jpg", frame, self._encode_param)
        if not success:
            return

        frame_bytes = encoded.tobytes()

        with self._lock:
            self._buffer.append((timestamp, frame_bytes, is_motion))

            # Evict frames older than max_duration
            cutoff_time = timestamp - self.max_duration
            while self._buffer and self._buffer[0][0] < cutoff_time:
                self._buffer.popleft()

    def get_snapshot(self) -> List[Tuple[float, bytes, bool]]:
        """
        Returns an immutable snapshot list of all (timestamp, jpeg_bytes, is_motion) currently in buffer.
        """
        with self._lock:
            return list(self._buffer)

    def duration(self) -> float:
        """Returns the current duration in seconds stored in the buffer."""
        with self._lock:
            if len(self._buffer) < 2:
                return 0.0
            return self._buffer[-1][0] - self._buffer[0][0]

    def count(self) -> int:
        """Returns the number of frames currently in the buffer."""
        with self._lock:
            return len(self._buffer)

    def clear(self) -> None:
        """Clears all frames from the buffer."""
        with self._lock:
            self._buffer.clear()
