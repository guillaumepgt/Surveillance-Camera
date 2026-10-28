"""
Test suite for motion detection, circular buffering, and video generation.
"""

from pathlib import Path
import time
import cv2
import numpy as np

from buffer_manager import FrameBuffer
from motion_detector import MotionDetector
from video_writer import create_video_from_frames


def test_frame_buffer():
    print("Testing FrameBuffer...")
    buf = FrameBuffer(max_duration_seconds=1.0, jpeg_quality=80)
    dummy = np.zeros((240, 320, 3), dtype=np.uint8)

    t0 = time.time()
    buf.add_frame(dummy, timestamp=t0)
    buf.add_frame(dummy, timestamp=t0 + 0.5)
    buf.add_frame(dummy, timestamp=t0 + 1.2)  # Should evict t0 (< t0+1.2 - 1.0 = t0+0.2)

    snapshot = buf.get_snapshot()
    assert len(snapshot) == 2, f"Expected 2 frames after eviction, got {len(snapshot)}"
    assert snapshot[0][0] == t0 + 0.5, "First frame should be t0 + 0.5"
    print("✓ FrameBuffer eviction and snapshot OK")


def test_motion_detector():
    print("Testing MotionDetector...")
    detector = MotionDetector(min_area=500, max_area_ratio=0.50, var_threshold=25)
    bg_frame = np.zeros((480, 640, 3), dtype=np.uint8)

    # Train background model on static frames
    for _ in range(20):
        detector.detect(bg_frame)

    # Static frame should have no motion
    is_motion, bboxes, _, is_light = detector.detect(bg_frame)
    assert not is_motion and not is_light, "Static frame should not trigger motion!"

    # Test lighting change (global illumination shift: 80% of image changes)
    light_frame = np.full((480, 640, 3), 150, dtype=np.uint8)
    is_motion_l, _, _, is_light = detector.detect(light_frame)
    assert not is_motion_l and is_light, "Lighting shift should be flagged as lighting change and ignored!"
    print("✓ Lighting change successfully filtered out")

    # Introduce local moving white rectangle
    motion_frame = light_frame.copy()
    cv2.rectangle(motion_frame, (100, 100), (300, 300), (255, 255, 255), -1)
    is_motion, bboxes, max_area, is_light2 = detector.detect(motion_frame)
    assert is_motion and not is_light2, "Moving object should trigger motion!"
    assert len(bboxes) > 0, "Should have detected at least one bounding box"
    print(f"✓ MotionDetector OK (detected area: {max_area:.0f} px)")


def test_video_writer():
    print("Testing VideoWriter...")
    buf = FrameBuffer(max_duration_seconds=5.0, jpeg_quality=85)
    t0 = time.time()

    # Generate 40 synthetic frames (2 seconds at 20 fps)
    for i in range(40):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        # moving circle
        cx = int(50 + i * 5)
        cv2.circle(frame, (cx, 120), 30, (0, 255, 0), -1)
        buf.add_frame(frame, timestamp=t0 + i * 0.05, is_motion=(i > 20))

    frames = buf.get_snapshot()
    test_video = Path("/tmp/test_surveillance_output.mp4")
    out = create_video_from_frames(frames, test_video, target_fps=20.0, add_overlay=True)

    assert out.exists(), "Output video file was not created!"
    assert out.stat().st_size > 1000, f"Video file too small: {out.stat().st_size} bytes"

    # Verify with cv2.VideoCapture
    cap = cv2.VideoCapture(str(out))
    assert cap.isOpened(), "Could not open generated video!"
    w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    test_video.unlink(missing_ok=True)

    assert w == 320 and h == 240, f"Expected 320x240, got {w}x{h}"
    assert count == 40, f"Expected 40 frames in video, got {count}"
    print(f"✓ VideoWriter OK (generated valid MP4 with {count} frames)")


if __name__ == "__main__":
    test_frame_buffer()
    test_motion_detector()
    test_video_writer()
    print("\nALL SYSTEM TESTS PASSED SUCCESSFULLY! 🎉")
