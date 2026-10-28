"""
Configuration module for the motion detection and video recording system.
Settings can be defined here or overridden via environment variables / .env file.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if it exists
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _get_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


# ==========================================
# Camera Settings
# ==========================================
# 0 for default USB/built-in webcam, or RTSP URL like "rtsp://user:pass@192.168.1.50:554/stream"
CAMERA_SOURCE = os.getenv("CAMERA_SOURCE", "0")
FRAME_WIDTH = int(os.getenv("FRAME_WIDTH", "640"))
FRAME_HEIGHT = int(os.getenv("FRAME_HEIGHT", "480"))
TARGET_FPS = int(os.getenv("TARGET_FPS", "20"))

# ==========================================
# Recording Buffer Durations (in seconds)
# ==========================================
# 60s before motion + 60s after motion = 120s (2 minutes total)
PRE_BUFFER_SECONDS = float(os.getenv("PRE_BUFFER_SECONDS", "60.0"))
POST_BUFFER_SECONDS = float(os.getenv("POST_BUFFER_SECONDS", "60.0"))

# Buffer frame compression: JPEG quality (1-100) to keep RAM usage low (~50MB for 60s)
JPEG_QUALITY = int(os.getenv("JPEG_QUALITY", "85"))

# ==========================================
# Motion Detection Parameters
# ==========================================
# Minimum contour area in pixels to trigger detection (augmented from 1500 to 3500 to ignore tiny noise/typing)
MOTION_MIN_AREA = int(os.getenv("MOTION_MIN_AREA", "3500"))
# MOG2 background subtractor sensitivity (lower = more sensitive)
MOTION_VAR_THRESHOLD = int(os.getenv("MOTION_VAR_THRESHOLD", "25"))
# Number of consecutive frames with motion required to trigger (~0.4s at 20fps), eliminates single-frame noise
MOTION_CONSECUTIVE_FRAMES = int(os.getenv("MOTION_CONSECUTIVE_FRAMES", "8"))
# Cooldown period in seconds after a recording completes before a new event can be triggered
COOLDOWN_SECONDS = float(os.getenv("COOLDOWN_SECONDS", "30.0"))
# Seconds to wait at startup before motion can trigger (allows background model to learn)
MOTION_WARMUP_SECONDS = float(os.getenv("MOTION_WARMUP_SECONDS", "5.0"))
# Require pre-buffer to be nearly full (~50s) before first trigger to guarantee a full 1 min before
REQUIRE_FULL_BUFFER = _get_bool("REQUIRE_FULL_BUFFER", True)
# Maximum ratio of frame allowed to change (above this, e.g. 50%, it's treated as a lighting change)
MAX_MOTION_RATIO = float(os.getenv("MAX_MOTION_RATIO", "0.50"))
# Sudden jump in average frame brightness indicating a light switch or flash
LIGHTING_DELTA_THRESHOLD = float(os.getenv("LIGHTING_DELTA_THRESHOLD", "12.0"))

# ==========================================
# Storage and Overlay Settings
# ==========================================
RECORDINGS_DIR = Path(os.getenv("RECORDINGS_DIR", str(BASE_DIR / "recordings")))
KEEP_LOCAL_COPY = _get_bool("KEEP_LOCAL_COPY", True)
ADD_OVERLAY = _get_bool("ADD_OVERLAY", True)

# ==========================================
# Google Drive & Cloud Upload Settings
# ==========================================
# Upload method: 'gdrive_api', 'rclone', or 'none'
UPLOAD_METHOD = os.getenv("UPLOAD_METHOD", "gdrive_api")

# Google Drive API settings
GDRIVE_FOLDER_NAME = os.getenv("GDRIVE_FOLDER_NAME", "Surveillance_Videos")
GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID", "")
CREDENTIALS_FILE = Path(os.getenv("CREDENTIALS_FILE", str(BASE_DIR / "credentials.json")))
TOKEN_FILE = Path(os.getenv("TOKEN_FILE", str(BASE_DIR / "token.json")))

# Rclone settings (used if UPLOAD_METHOD == 'rclone')
RCLONE_REMOTE = os.getenv("RCLONE_REMOTE", "gdrive:Surveillance")

# ==========================================
# Email Notification Settings
# ==========================================
ENABLE_EMAIL_ALERTS = _get_bool("ENABLE_EMAIL_ALERTS", False)
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_TO = os.getenv("EMAIL_TO", "")


def parse_camera_source(source_str: str):
    """Convert camera source string to int if it's a numeric index, else keep as string."""
    try:
        return int(source_str)
    except ValueError:
        return source_str
