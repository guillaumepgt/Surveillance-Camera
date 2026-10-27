"""
Google Drive and cloud storage upload module.
Handles authentication, folder creation, resumable uploads, and background worker queue.
Supports both native Google Drive API (OAuth2) and Rclone.
"""

import logging
from pathlib import Path
import queue
import subprocess
import threading
import time
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

# Scopes needed for Google Drive: drive.file only grants access to files created by this app
SCOPES = ["https://www.googleapis.com/auth/drive.file"]


class GoogleDriveUploader:
    """Handles authentication and file uploads via the official Google Drive API v3."""

    def __init__(
        self,
        credentials_file: Path | str = "credentials.json",
        token_file: Path | str = "token.json",
        folder_name: str = "Surveillance_Videos",
        folder_id: Optional[str] = None,
    ):
        self.credentials_file = Path(credentials_file)
        self.token_file = Path(token_file)
        self.folder_name = folder_name
        self.folder_id = folder_id
        self._service = None

    def authenticate(self, interactive: bool = True) -> bool:
        """
        Authenticate with Google Drive API using stored token.json or interactive OAuth2 flow.
        """
        creds = None

        if self.token_file.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)
            except Exception as e:
                logger.warning(f"Impossible de lire {self.token_file}: {e}. Renouvellement nécessaire.")

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    logger.info("Renouvellement du jeton Google Drive en cours...")
                    creds.refresh(Request())
                except Exception as e:
                    logger.warning(f"Échec du renouvellement du jeton: {e}")
                    creds = None

            if not creds:
                if not self.credentials_file.exists():
                    raise FileNotFoundError(
                        f"Fichier '{self.credentials_file}' introuvable. "
                        "Veuillez télécharger les identifiants OAuth Client ID (Desktop) depuis Google Cloud Console "
                        "ou lancez 'python3 setup_gdrive.py' pour être guidé pas à pas."
                    )

                if not interactive:
                    raise RuntimeError("Authentification interactive requise, mais mode interactif désactivé.")

                logger.info("Ouverture du navigateur pour autoriser l'accès à Google Drive...")
                flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_file), SCOPES)
                creds = flow.run_local_server(port=0)

            # Save the valid credentials for subsequent runs
            with open(self.token_file, "w") as token:
                token.write(creds.to_json())
                logger.info(f"Nouveau jeton enregistré dans {self.token_file}")

        self._service = build("drive", "v3", credentials=creds)

        # Resolve or create target folder
        if not self.folder_id and self.folder_name:
            self.folder_id = self._get_or_create_folder(self.folder_name)

        return True

    def _get_or_create_folder(self, folder_name: str) -> str:
        """Find an existing folder by name or create it on Google Drive."""
        if not self._service:
            raise RuntimeError("Le service Google Drive n'est pas initialisé.")

        query = (
            f"mimeType = 'application/vnd.google-apps.folder' and "
            f"name = '{folder_name}' and trashed = false"
        )
        response = self._service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
        files = response.get("files", [])

        if files:
            folder_id = files[0]["id"]
            logger.info(f"Dossier Google Drive existant trouvé : '{folder_name}' (ID: {folder_id})")
            return folder_id

        # Folder does not exist, create it
        file_metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        folder = self._service.files().create(body=file_metadata, fields="id").execute()
        folder_id = folder.get("id")
        logger.info(f"Nouveau dossier Google Drive créé : '{folder_name}' (ID: {folder_id})")
        return folder_id

    def upload_file(self, file_path: Path | str) -> dict:
        """
        Upload a file to Google Drive using resumable upload.
        """
        if not self._service:
            self.authenticate()

        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Fichier local introuvable : {file_path}")

        file_metadata = {"name": file_path.name}
        if self.folder_id:
            file_metadata["parents"] = [self.folder_id]

        media = MediaFileUpload(
            str(file_path),
            mimetype="video/mp4",
            resumable=True,
            chunksize=5 * 1024 * 1024,  # 5 MB chunks
        )

        logger.info(f"Début de l'envoi vers Google Drive : {file_path.name} ({file_path.stat().st_size / (1024*1024):.2f} MB)...")
        request = self._service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, name, webViewLink",
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info(f"Progression de l'envoi : {int(status.progress() * 100)}%")

        logger.info(f"Fichier téléversé avec succès sur Google Drive ! Lien : {response.get('webViewLink')}")
        return response


class RcloneUploader:
    """Alternative uploader using the rclone CLI."""

    def __init__(self, remote_dest: str = "gdrive:Surveillance"):
        self.remote_dest = remote_dest

    def upload_file(self, file_path: Path | str) -> bool:
        file_path = Path(file_path)
        logger.info(f"Envoi via rclone de {file_path.name} vers {self.remote_dest}...")
        cmd = ["rclone", "copy", str(file_path), self.remote_dest]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            logger.error(f"Erreur rclone (code {res.returncode}): {res.stderr}")
            raise RuntimeError(f"Rclone copy échoué : {res.stderr}")
        logger.info(f"Fichier téléversé avec succès via rclone : {file_path.name}")
        return True


class UploadWorker:
    """
    Background worker that uploads files asynchronously without blocking video capture.
    """

    def __init__(self, uploader, keep_local_copy: bool = True, on_success_callback=None):
        self.uploader = uploader
        self.keep_local_copy = keep_local_copy
        self.on_success_callback = on_success_callback
        self._queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="UploadWorkerThread")
        self._thread.start()

    def enqueue(self, file_path: Path | str, metadata: Optional[dict] = None):
        """Add a video file and optional event metadata to the background upload queue."""
        self._queue.put((Path(file_path), metadata or {}))
        logger.info(f"Vidéo ajoutée à la file d'attente d'envoi ({self._queue.qsize()} en attente) : {Path(file_path).name}")

    def _run(self):
        while not self._stop_event.is_set() or not self._queue.empty():
            try:
                file_path, metadata = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            # Attempt upload with retries
            success = False
            upload_result = None
            for attempt in range(1, 4):
                try:
                    logger.info(f"[UploadWorker] Tentative {attempt}/3 pour {file_path.name}...")
                    if self.uploader:
                        upload_result = self.uploader.upload_file(file_path)
                    success = True
                    break
                except Exception as e:
                    logger.error(f"[UploadWorker] Erreur tentative {attempt}: {e}")
                    time.sleep(3.0 * attempt)

            # Trigger success callback (e.g. email notification)
            if success and self.on_success_callback:
                try:
                    self.on_success_callback(file_path, upload_result, metadata)
                except Exception as e:
                    logger.error(f"[UploadWorker] Erreur dans le callback après envoi : {e}")

            if success and not self.keep_local_copy:
                try:
                    file_path.unlink(missing_ok=True)
                    logger.info(f"[UploadWorker] Copie locale supprimée : {file_path.name}")
                except Exception as e:
                    logger.warning(f"Impossible de supprimer la copie locale : {e}")

            self._queue.task_done()

    def wait_completion(self, timeout: float = 30.0):
        """Wait for pending uploads to finish."""
        logger.info("Attente de la fin des envois en attente...")
        self._queue.join()

    def stop(self):
        """Signal the worker to stop."""
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=5.0)
