#!/usr/bin/env python3
"""
Application principale de surveillance vidéo avec détection de mouvement.
Enregistre automatiquement des vidéos de 2 minutes :
- 1 minute avant le déclenchement du mouvement (tampon circulaire en mémoire)
- 1 minute après le mouvement
Puis téléverse automatiquement le fichier MP4 sur Google Drive.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import logging
import os
from pathlib import Path
import signal
import sys
import time
from typing import List, Tuple

import cv2
import numpy as np

import config
from buffer_manager import FrameBuffer
from motion_detector import MotionDetector
from video_writer import create_video_from_frames
from gdrive_uploader import GoogleDriveUploader, RcloneUploader, UploadWorker
from email_notifier import EmailNotifier

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("Surveillance")


class SurveillanceCamera:
    def __init__(
        self,
        camera_source=config.CAMERA_SOURCE,
        frame_width: int = config.FRAME_WIDTH,
        frame_height: int = config.FRAME_HEIGHT,
        target_fps: int = config.TARGET_FPS,
        pre_buffer_sec: float = config.PRE_BUFFER_SECONDS,
        post_buffer_sec: float = config.POST_BUFFER_SECONDS,
        min_area: int = config.MOTION_MIN_AREA,
        cooldown_sec: float = config.COOLDOWN_SECONDS,
        consecutive_frames: int = config.MOTION_CONSECUTIVE_FRAMES,
        require_full_buffer: bool = config.REQUIRE_FULL_BUFFER,
        uploader_type: str = config.UPLOAD_METHOD,
        keep_local_copy: bool = config.KEEP_LOCAL_COPY,
        show_preview: bool = False,
        add_overlay: bool = config.ADD_OVERLAY,
    ):
        self.camera_source = config.parse_camera_source(str(camera_source))
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.target_fps = target_fps
        self.pre_buffer_sec = pre_buffer_sec
        self.post_buffer_sec = post_buffer_sec
        self.min_area = min_area
        self.cooldown_sec = cooldown_sec
        self.consecutive_frames = consecutive_frames
        self.require_full_buffer = require_full_buffer
        self.uploader_type = uploader_type
        self.keep_local_copy = keep_local_copy
        self.show_preview = show_preview
        self.add_overlay = add_overlay

        # State management
        self.is_running = False
        self.state = "BUFFERING"  # "BUFFERING" or "RECORDING"
        self.motion_trigger_time: float = 0.0
        self.last_event_end_time: float = 0.0
        self.consecutive_motion_frames: int = 0
        self.calm_start_time: float = 0.0
        self.is_armed: bool = False

        # Memory buffer for pre-motion frames (1 minute)
        self.pre_buffer = FrameBuffer(
            max_duration_seconds=self.pre_buffer_sec,
            jpeg_quality=config.JPEG_QUALITY,
        )

        # Buffer for snapshot of pre-motion frames and active post-motion frames
        self.event_pre_frames: List[Tuple[float, bytes, bool]] = []
        self.event_post_frames: List[Tuple[float, bytes, bool]] = []

        # Motion detector with illumination change filtering
        self.detector = MotionDetector(
            min_area=self.min_area,
            max_area_ratio=config.MAX_MOTION_RATIO,
            var_threshold=config.MOTION_VAR_THRESHOLD,
            lighting_delta_threshold=config.LIGHTING_DELTA_THRESHOLD,
        )

        # Email notifier
        self.email_notifier = EmailNotifier(
            smtp_server=config.SMTP_SERVER,
            smtp_port=config.SMTP_PORT,
            smtp_user=config.SMTP_USER,
            smtp_password=config.SMTP_PASSWORD,
            recipient_emails=[config.EMAIL_TO or config.SMTP_USER],
        )
        if self.email_notifier.is_configured:
            logger.info(f"Notifications email activées vers : {config.EMAIL_TO or config.SMTP_USER}")
        else:
            logger.info("Notifications email désactivées (renseignez SMTP_USER et SMTP_PASSWORD dans .env pour activer).")

        # Upload worker & video processing pool
        self.upload_worker = None
        self._init_uploader()
        self.video_encoder_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="VideoEncoder")

        # Storage directory
        self.recordings_dir = Path(config.RECORDINGS_DIR)
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        self.current_event_snapshot: Optional[bytes] = None

    def _on_upload_completed(self, file_path: Path, upload_result, metadata: dict):
        """Callback invoked when a video is processed and uploaded."""
        if not self.email_notifier.is_configured:
            return

        gdrive_link = ""
        if isinstance(upload_result, dict):
            gdrive_link = upload_result.get("webViewLink", "")

        trigger_time = metadata.get("trigger_time", time.time())
        snapshot_bytes = metadata.get("snapshot_bytes")

        logger.info(f"Envoi de l'email d'alerte pour {file_path.name}...")
        self.email_notifier.send_alert_async(
            timestamp=trigger_time,
            gdrive_link=gdrive_link,
            video_filename=file_path.name,
            snapshot_bytes=snapshot_bytes,
        )

    def _init_uploader(self):
        """Initialize the requested uploader (Google Drive API, Rclone, or None)."""
        uploader = None
        if self.uploader_type == "gdrive_api":
            logger.info("Initialisation de l'uploader Google Drive API...")
            try:
                gdrive = GoogleDriveUploader(
                    credentials_file=config.CREDENTIALS_FILE,
                    token_file=config.TOKEN_FILE,
                    folder_name=config.GDRIVE_FOLDER_NAME,
                    folder_id=config.GDRIVE_FOLDER_ID or None,
                )
                gdrive.authenticate(interactive=False)
                uploader = gdrive
                logger.info(f"Google Drive connecté avec succès (dossier : {config.GDRIVE_FOLDER_NAME})")
            except Exception as e:
                logger.warning(
                    f"Authentification Google Drive non initialisée : {e}\n"
                    "--> Lancez 'python3 setup_gdrive.py' pour configurer vos identifiants Google.\n"
                    "--> Les vidéos seront conservées localement dans le dossier recordings/ en attendant."
                )
        elif self.uploader_type == "rclone":
            logger.info(f"Initialisation de l'uploader Rclone vers {config.RCLONE_REMOTE}...")
            uploader = RcloneUploader(remote_dest=config.RCLONE_REMOTE)
        elif self.uploader_type == "none":
            logger.info("Téléversement cloud désactivé (--uploader none). Enregistrement local uniquement.")

        self.upload_worker = UploadWorker(
            uploader=uploader,
            keep_local_copy=self.keep_local_copy,
            on_success_callback=self._on_upload_completed,
        )

    def _async_encode_and_upload(
        self,
        all_frames: List[Tuple[float, bytes, bool]],
        output_path: Path,
        metadata: Optional[dict] = None,
    ):
        """Asynchronously encodes the assembled frames to MP4 and sends to upload worker."""
        try:
            create_video_from_frames(
                frames=all_frames,
                output_path=output_path,
                target_fps=self.target_fps,
                add_overlay=self.add_overlay,
            )
            # Once video file is written, enqueue for upload
            if self.upload_worker:
                self.upload_worker.enqueue(output_path, metadata=metadata)
        except Exception as e:
            logger.error(f"Erreur lors de l'encodage vidéo de {output_path.name} : {e}", exc_info=True)

    def run(self):
        """Main camera capture loop with motion detection and circular buffering."""
        logger.info(f"Ouverture de la caméra (source : {self.camera_source})...")
        cap = cv2.VideoCapture(self.camera_source)

        if not cap.isOpened():
            logger.error(f"Impossible d'ouvrir la caméra '{self.camera_source}'. Vérifiez la connexion ou les permissions.")
            return

        # Attempt to set camera properties
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.frame_width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.frame_height)
        cap.set(cv2.CAP_PROP_FPS, self.target_fps)

        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = cap.get(cv2.CAP_PROP_FPS)
        logger.info(f"Caméra prête : {actual_w}x{actual_h} @ {actual_fps:.1f} FPS demandés")
        logger.info(f"Tampon pré-mouvement : {self.pre_buffer_sec}s | Enregistrement post-mouvement : {self.post_buffer_sec}s")
        logger.info("Démarrage de la surveillance... (Ctrl+C pour quitter)")

        self.is_running = True
        start_time = time.time()
        frame_count = 0
        fps_calc_time = time.time()
        fps_current = 0.0

        try:
            while self.is_running:
                ret, frame = cap.read()
                if not ret or frame is None:
                    logger.warning("Échec de lecture de frame depuis la caméra. Nouvelle tentative...")
                    time.sleep(0.1)
                    continue

                now = time.time()
                frame_count += 1

                # Calculate live FPS every second
                if now - fps_calc_time >= 1.0:
                    fps_current = frame_count / (now - fps_calc_time)
                    frame_count = 0
                    fps_calc_time = now

                # Motion detection with illumination filtering
                is_motion, bboxes, max_area, is_lighting_change = self.detector.detect(frame)

                # Warmup check: ignore triggers during initial stabilization seconds
                in_warmup = (now - start_time) < config.MOTION_WARMUP_SECONDS

                # Always keep the circular pre-buffer populated with the latest frames
                self.pre_buffer.add_frame(frame, timestamp=now, is_motion=is_motion)

                # If a sudden lighting change is detected, reset motion counter and calm timer
                if is_lighting_change:
                    self.consecutive_motion_frames = 0
                    self.calm_start_time = 0.0

                # Track consecutive motion frames to avoid single-frame noise
                if is_motion and not is_lighting_change:
                    self.consecutive_motion_frames += 1
                else:
                    self.consecutive_motion_frames = 0
                confirmed_motion = self.consecutive_motion_frames >= self.consecutive_frames

                # Check if buffer has filled enough (at least 85% of target duration)
                buffer_ready = (not self.require_full_buffer) or (
                    self.pre_buffer.duration() >= min(50.0, self.pre_buffer_sec * 0.85)
                )

                # Cooldown check
                in_cooldown = (now - self.last_event_end_time) < self.cooldown_sec

                # Re-arming logic: require scene to be calm for at least 3 seconds
                if not self.is_armed and not in_warmup and buffer_ready and not in_cooldown and self.state == "BUFFERING":
                    if not is_motion:
                        if self.calm_start_time == 0.0:
                            self.calm_start_time = now
                        elif (now - self.calm_start_time) >= 3.0:
                            self.is_armed = True
                            logger.info("[RE-ARMEMENT] La scène est stable et calme. Système armé et prêt à détecter un nouveau mouvement !")
                    else:
                        self.calm_start_time = 0.0

                # STATE MACHINE
                if self.state == "BUFFERING":
                    # Check if motion confirmed and system is armed
                    if confirmed_motion and self.is_armed:
                        logger.info(
                            f"[ALERTE MOUVEMENT] Mouvement confirmé ({self.consecutive_motion_frames} frames, zone max: {int(max_area)} px) ! "
                            f"Instanciation de l'événement (tampon avant: {self.pre_buffer.duration():.1f}s)..."
                        )
                        self.state = "RECORDING"
                        self.is_armed = False
                        self.calm_start_time = 0.0
                        self.motion_trigger_time = now

                        # Take snapshot of the pre-motion buffer (up to 60s before)
                        self.event_pre_frames = self.pre_buffer.get_snapshot()

                        # Encode first post-motion frame and snapshot for email
                        success, enc = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, config.JPEG_QUALITY])
                        if success:
                            frame_bytes = enc.tobytes()
                            self.event_post_frames = [(now, frame_bytes, is_motion)]
                            self.current_event_snapshot = frame_bytes
                        else:
                            self.event_post_frames = []
                            self.current_event_snapshot = None

                elif self.state == "RECORDING":
                    # Accumulate post-motion frames
                    success, enc = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, config.JPEG_QUALITY])
                    if success:
                        self.event_post_frames.append((now, enc.tobytes(), is_motion))

                    elapsed_post = now - self.motion_trigger_time

                    # Check if post-motion recording duration (60s) has elapsed
                    if elapsed_post >= self.post_buffer_sec:
                        total_frames = len(self.event_pre_frames) + len(self.event_post_frames)
                        pre_dur = (
                            self.event_pre_frames[-1][0] - self.event_pre_frames[0][0]
                            if len(self.event_pre_frames) > 1
                            else 0.0
                        )
                        logger.info(
                            f"[FIN D'ÉVÉNEMENT] Enregistrement terminé : {pre_dur:.1f}s avant + {elapsed_post:.1f}s après "
                            f"({total_frames} frames au total). Génération de la vidéo..."
                        )

                        # Output file path
                        timestamp_str = datetime.fromtimestamp(self.motion_trigger_time).strftime("%Y%m%d_%H%M%S")
                        output_file = self.recordings_dir / f"motion_{timestamp_str}.mp4"

                        # Asynchronously write video and dispatch to Google Drive with email metadata
                        combined_frames = list(self.event_pre_frames) + list(self.event_post_frames)
                        metadata = {
                            "trigger_time": self.motion_trigger_time,
                            "snapshot_bytes": self.current_event_snapshot,
                        }
                        self.video_encoder_pool.submit(self._async_encode_and_upload, combined_frames, output_file, metadata)

                        # Reset state back to BUFFERING with cooldown and wait for calm
                        self.state = "BUFFERING"
                        self.event_pre_frames = []
                        self.event_post_frames = []
                        self.last_event_end_time = now
                        self.is_armed = False
                        self.consecutive_motion_frames = 0
                        self.calm_start_time = 0.0
                        logger.info(f"Période de repos / cooldown activée ({self.cooldown_sec:.0f}s). En attente du calme pour réarmer.")

                # Optional GUI Preview
                if self.show_preview:
                    preview_frame = frame.copy()

                    # Draw motion bounding boxes
                    for x, y, bw, bh in bboxes:
                        cv2.rectangle(preview_frame, (x, y), (x + bw, y + bh), (0, 255, 0), 2)

                    # Top status overlay banner
                    if is_lighting_change:
                        status_str = "VARIATION DE LUMINOSITE DETECTEE (IGNORE)"
                        color = (0, 165, 255)
                    elif in_warmup:
                        status_str = f"STABILISATION INITIALE ({int(config.MOTION_WARMUP_SECONDS - (now - start_time))}s)"
                        color = (0, 165, 255)
                    elif not buffer_ready:
                        status_str = f"REMPLISSAGE DU TAMPON ({self.pre_buffer.duration():.0f}s / {self.pre_buffer_sec:.0f}s)"
                        color = (0, 200, 200)
                    elif self.state == "RECORDING":
                        elapsed = now - self.motion_trigger_time
                        status_str = f"ENREGISTREMENT POST-MOUVEMENT ({elapsed:.1f}s / {self.post_buffer_sec:.0f}s)"
                        color = (0, 0, 255)
                    elif in_cooldown:
                        rem = int(self.cooldown_sec - (now - self.last_event_end_time))
                        status_str = f"COOLDOWN / REPOS ({rem}s)"
                        color = (255, 165, 0)
                    elif not self.is_armed:
                        calm_dur = (now - self.calm_start_time) if self.calm_start_time > 0 else 0.0
                        status_str = f"EN ATTENTE DU CALME ({calm_dur:.1f}s / 3.0s)"
                        color = (200, 200, 0)
                    else:
                        status_str = f"SURVEILLANCE ACTIVE - ARME (tampon: {self.pre_buffer.duration():.1f}s)"
                        color = (0, 255, 0)

                    cv2.putText(
                        preview_frame,
                        f"[{status_str}]  FPS: {fps_current:.1f}",
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        color,
                        2,
                    )

                    cv2.imshow("Surveillance Camera (Touche 'q' pour quitter)", preview_frame)
                    key = cv2.waitKey(1) & 0xFF
                    if key in (ord("q"), 27):  # 'q' or ESC
                        logger.info("Touche 'q' détectée. Arrêt demandé par l'utilisateur.")
                        self.is_running = False

        except KeyboardInterrupt:
            logger.info("Interruption clavier détectée (Ctrl+C).")
        finally:
            self.stop(cap)

    def stop(self, cap=None):
        """Release camera and gracefully wait for encoders and uploads to finish."""
        if not self.is_running:
            return
        self.is_running = False
        logger.info("Fermeture de la caméra...")
        if cap and cap.isOpened():
            cap.release()
        if self.show_preview:
            cv2.destroyAllWindows()

        logger.info("Attente de la fin des encodages vidéo en cours...")
        self.video_encoder_pool.shutdown(wait=True)

        if self.upload_worker:
            logger.info("Attente de la fin des téléversements en cours...")
            self.upload_worker.wait_completion(timeout=30.0)
            self.upload_worker.stop()

        logger.info("Système de surveillance arrêté proprement.")


def main():
    parser = argparse.ArgumentParser(
        description="Script de surveillance vidéo avec sauvegarde sur Google Drive (1min avant + 1min après le mouvement)."
    )
    parser.add_argument(
        "--camera",
        type=str,
        default=config.CAMERA_SOURCE,
        help="Source de la caméra (0 pour webcam USB, ou URL RTSP).",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Afficher la fenêtre de prévisualisation en direct avec les détections.",
    )
    parser.add_argument(
        "--pre-duration",
        type=float,
        default=config.PRE_BUFFER_SECONDS,
        help=f"Durée du tampon avant mouvement en secondes (défaut : {config.PRE_BUFFER_SECONDS}s).",
    )
    parser.add_argument(
        "--post-duration",
        type=float,
        default=config.POST_BUFFER_SECONDS,
        help=f"Durée d'enregistrement après mouvement en secondes (défaut : {config.POST_BUFFER_SECONDS}s).",
    )
    parser.add_argument(
        "--min-area",
        type=int,
        default=config.MOTION_MIN_AREA,
        help=f"Surface minimale en pixels pour déclencher le mouvement (défaut : {config.MOTION_MIN_AREA}).",
    )
    parser.add_argument(
        "--cooldown",
        type=float,
        default=config.COOLDOWN_SECONDS,
        help=f"Délai d'apaisement en secondes après une vidéo avant réarmement (défaut : {config.COOLDOWN_SECONDS}s).",
    )
    parser.add_argument(
        "--consecutive-frames",
        type=int,
        default=config.MOTION_CONSECUTIVE_FRAMES,
        help=f"Nombre de frames consécutives avec mouvement pour confirmer (défaut : {config.MOTION_CONSECUTIVE_FRAMES}).",
    )
    parser.add_argument(
        "--no-wait-buffer",
        action="store_true",
        help="Ne pas attendre que le tampon initial de 60s soit plein avant le premier déclenchement.",
    )
    parser.add_argument(
        "--uploader",
        choices=["gdrive_api", "rclone", "none"],
        default=config.UPLOAD_METHOD,
        help="Méthode de téléversement : 'gdrive_api' (défaut), 'rclone', ou 'none'.",
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Désactive l'envoi cloud (identique à --uploader none).",
    )
    parser.add_argument(
        "--no-keep-local",
        action="store_true",
        help="Supprime la copie locale une fois le téléversement réussi.",
    )
    parser.add_argument(
        "--no-overlay",
        action="store_true",
        help="Ne pas incruster la date et l'heure sur la vidéo.",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=config.TARGET_FPS,
        help=f"Nombre d'images par seconde cible (défaut : {config.TARGET_FPS}).",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=config.FRAME_WIDTH,
        help=f"Largeur de l'image (défaut : {config.FRAME_WIDTH}).",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=config.FRAME_HEIGHT,
        help=f"Hauteur de l'image (défaut : {config.FRAME_HEIGHT}).",
    )

    args = parser.parse_args()

    uploader_choice = "none" if args.no_upload else args.uploader
    keep_local = not args.no_keep_local

    surveillance = SurveillanceCamera(
        camera_source=args.camera,
        frame_width=args.width,
        frame_height=args.height,
        target_fps=args.fps,
        pre_buffer_sec=args.pre_duration,
        post_buffer_sec=args.post_duration,
        min_area=args.min_area,
        cooldown_sec=args.cooldown,
        consecutive_frames=args.consecutive_frames,
        require_full_buffer=not args.no_wait_buffer,
        uploader_type=uploader_choice,
        keep_local_copy=keep_local,
        show_preview=args.preview,
        add_overlay=not args.no_overlay,
    )

    # Intercept termination signals
    def handle_signal(sig, frame):
        surveillance.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    surveillance.run()


if __name__ == "__main__":
    main()
