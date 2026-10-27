"""
Video writer module.
Assembles buffered JPEG frames into standard H.264 MP4 videos using FFmpeg
(with fallback to OpenCV VideoWriter if FFmpeg is unavailable).
Ensures full compatibility with Google Drive web preview streaming via -movflags +faststart.
"""

from datetime import datetime
import logging
from pathlib import Path
import shutil
import subprocess
from typing import List, Tuple
import cv2
import numpy as np

logger = logging.getLogger(__name__)


def _draw_overlay(frame: np.ndarray, timestamp: float, is_motion: bool) -> np.ndarray:
    """Draw timestamp and status overlay on the frame with high contrast."""
    dt_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S.%f")[:-4]
    status_text = "MOTION" if is_motion else "REC"
    text = f"{dt_str}  [{status_text}]"

    # Font properties
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.55
    thickness = 1
    pos = (15, 25)

    # Black outline for readability against light background
    cv2.putText(frame, text, pos, font, scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
    # Status color: red for motion, yellow/white for normal
    text_color = (0, 0, 255) if is_motion else (255, 255, 255)
    cv2.putText(frame, text, pos, font, scale, text_color, thickness, cv2.LINE_AA)
    return frame


def create_video_from_frames(
    frames: List[Tuple[float, bytes, bool]],
    output_path: Path | str,
    target_fps: float = 20.0,
    add_overlay: bool = True,
) -> Path:
    """
    Assemble a list of (timestamp, jpeg_bytes, is_motion) into an MP4 file.

    :param frames: List of buffered frames.
    :param output_path: Destination path for the MP4 video.
    :param target_fps: Fallback FPS if real duration cannot be computed.
    :param add_overlay: Whether to burn date/time and motion status on frames.
    :return: Path to the generated video.
    """
    if not frames:
        raise ValueError("Cannot create video from empty frame list.")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Decode first frame to get dimensions
    first_ts, first_bytes, _ = frames[0]
    sample_img = cv2.imdecode(np.frombuffer(first_bytes, np.uint8), cv2.IMREAD_COLOR)
    if sample_img is None:
        raise ValueError("Failed to decode sample frame from buffer.")

    h, w = sample_img.shape[:2]

    # Calculate real framerate from timestamps
    num_frames = len(frames)
    duration = frames[-1][0] - frames[0][0]
    if duration > 1.0 and num_frames > 1:
        computed_fps = (num_frames - 1) / duration
        # Keep within reasonable bounds
        effective_fps = max(5.0, min(60.0, computed_fps))
    else:
        effective_fps = float(target_fps)

    has_ffmpeg = shutil.which("ffmpeg") is not None

    if has_ffmpeg:
        # Use FFmpeg to create H.264 video with yuv420p & faststart (playable on Google Drive web & mobile)
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "rawvideo",
            "-vcodec",
            "rawvideo",
            "-s",
            f"{w}x{h}",
            "-pix_fmt",
            "bgr24",
            "-r",
            f"{effective_fps:.2f}",
            "-i",
            "-",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-movflags",
            "+faststart",
            str(output_path),
        ]

        logger.info(
            f"Encoding {num_frames} frames ({duration:.1f}s, {effective_fps:.1f} fps) to {output_path.name} via FFmpeg..."
        )
        proc = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )

        try:
            for ts, frame_bytes, is_motion in frames:
                frame = cv2.imdecode(np.frombuffer(frame_bytes, np.uint8), cv2.IMREAD_COLOR)
                if frame is None:
                    continue
                if add_overlay:
                    frame = _draw_overlay(frame, ts, is_motion)
                proc.stdin.write(frame.tobytes())
            proc.stdin.close()
            _, stderr = proc.communicate()
            if proc.returncode != 0:
                logger.error(f"FFmpeg encoding error (code {proc.returncode}): {stderr.decode('utf-8', errors='ignore')}")
                raise RuntimeError(f"FFmpeg failed with code {proc.returncode}")
        except Exception as e:
            if proc.poll() is None:
                proc.kill()
            raise e

    else:
        # Fallback to OpenCV VideoWriter
        logger.warning("FFmpeg not found in PATH; falling back to OpenCV VideoWriter.")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(output_path), fourcc, effective_fps, (w, h))

        try:
            for ts, frame_bytes, is_motion in frames:
                frame = cv2.imdecode(np.frombuffer(frame_bytes, np.uint8), cv2.IMREAD_COLOR)
                if frame is None:
                    continue
                if add_overlay:
                    frame = _draw_overlay(frame, ts, is_motion)
                writer.write(frame)
        finally:
            writer.release()

    logger.info(f"Successfully generated video: {output_path} ({output_path.stat().st_size / (1024*1024):.2f} MB)")
    return output_path
