"""
Email notification module for motion detection alerts.
Sends HTML emails with embedded snapshot photos and direct Google Drive video links.
Operates asynchronously via background threading to never block video capture.
"""

from datetime import datetime
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging
from pathlib import Path
import smtplib
import threading
from typing import List, Optional

logger = logging.getLogger(__name__)


class EmailNotifier:
    def __init__(
        self,
        smtp_server: str = "smtp.gmail.com",
        smtp_port: int = 587,
        smtp_user: str = "",
        smtp_password: str = "",
        recipient_emails: Optional[List[str]] = None,
        use_tls: bool = True,
    ):
        self.smtp_server = smtp_server
        self.smtp_port = int(smtp_port)
        self.smtp_user = smtp_user.strip()
        self.smtp_password = smtp_password.strip()
        self.recipient_emails = recipient_emails or ([self.smtp_user] if self.smtp_user else [])
        self.use_tls = use_tls

    @property
    def is_configured(self) -> bool:
        """Returns True if email credentials and recipient are configured."""
        return bool(self.smtp_server and self.smtp_user and self.smtp_password and self.recipient_emails)

    def send_alert(
        self,
        timestamp: float,
        gdrive_link: str = "",
        video_filename: str = "",
        snapshot_bytes: Optional[bytes] = None,
    ) -> bool:
        """
        Send an email alert synchronously.
        """
        if not self.is_configured:
            logger.warning("Notification email ignorée : paramètres SMTP non configurés.")
            return False

        dt_str = datetime.fromtimestamp(timestamp).strftime("%d/%m/%Y à %H:%M:%S")
        subject = f"🚨 Alerte Surveillance : Mouvement détecté le {dt_str}"

        # Create root multipart message
        msg = MIMEMultipart("related")
        msg["Subject"] = subject
        msg["From"] = f"Caméra Surveillance <{self.smtp_user}>"
        msg["To"] = ", ".join(self.recipient_emails)

        # HTML content
        button_html = ""
        if gdrive_link:
            button_html = f"""
            <div style="margin: 25px 0;">
                <a href="{gdrive_link}" style="background-color: #1a73e8; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">
                    ▶ Voir la vidéo sur Google Drive
                </a>
            </div>
            """

        image_html = ""
        if snapshot_bytes:
            image_html = """
            <div style="margin-top: 20px;">
                <p style="font-size: 14px; color: #555;"><strong>Photo au moment du déclenchement :</strong></p>
                <img src="cid:snapshot_img" style="max-width: 100%; border-radius: 8px; border: 1px solid #ddd; box-shadow: 0 2px 5px rgba(0,0,0,0.1);" alt="Capture de mouvement"/>
            </div>
            """

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family: Arial, sans-serif; background-color: #f4f6f9; padding: 20px; margin: 0;">
            <div style="max-width: 600px; margin: auto; background-color: #ffffff; border-radius: 10px; overflow: hidden; border: 1px solid #e0e0e0; box-shadow: 0 4px 10px rgba(0,0,0,0.05);">
                <div style="background-color: #d93025; color: white; padding: 18px 25px;">
                    <h2 style="margin: 0; font-size: 20px;">🚨 Mouvement Détecté</h2>
                </div>
                <div style="padding: 25px; color: #333333; line-height: 1.5;">
                    <p style="font-size: 16px; margin-top: 0;">
                        Un mouvement a été détecté devant votre caméra le <strong>{dt_str}</strong>.
                    </p>
                    <div style="background-color: #f8f9fa; border-left: 4px solid #1a73e8; padding: 12px 16px; margin: 15px 0; font-size: 14px;">
                        <strong>Détails de l'enregistrement :</strong><br>
                        • Vidéo : 2 minutes (1 min avant + 1 min après le mouvement)<br>
                        • Fichier : <code>{video_filename or 'Enregistrement MP4'}</code>
                    </div>
                    {button_html}
                    {image_html}
                    <hr style="border: none; border-top: 1px solid #eee; margin: 25px 0 15px 0;" />
                    <p style="font-size: 12px; color: #888888; margin: 0;">
                        Notification automatique générée par votre système de surveillance vidéo.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        msg_alternative = MIMEMultipart("alternative")
        msg.attach(msg_alternative)

        # Plain text fallback
        plain_text = (
            f"Alerte Surveillance\n\n"
            f"Mouvement détecté le {dt_str}.\n"
            f"Vidéo de 2 minutes sauvegardée.\n"
        )
        if gdrive_link:
            plain_text += f"Lien Google Drive : {gdrive_link}\n"
        msg_alternative.attach(MIMEText(plain_text, "plain", "utf-8"))
        msg_alternative.attach(MIMEText(html_body, "html", "utf-8"))

        # Attach inline snapshot image if provided
        if snapshot_bytes:
            img = MIMEImage(snapshot_bytes, name="snapshot.jpg")
            img.add_header("Content-ID", "<snapshot_img>")
            img.add_header("Content-Disposition", "inline", filename="snapshot.jpg")
            msg.attach(img)

        # Connect and send
        try:
            logger.info(f"Envoi de l'email d'alerte à {', '.join(self.recipient_emails)}...")
            if self.smtp_port == 465:
                server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, timeout=15)
            else:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=15)
                if self.use_tls:
                    server.starttls()

            server.login(self.smtp_user, self.smtp_password)
            server.sendmail(self.smtp_user, self.recipient_emails, msg.as_string())
            server.quit()
            logger.info("Email d'alerte envoyé avec succès !")
            return True
        except Exception as e:
            logger.error(f"Échec de l'envoi de l'email d'alerte : {e}")
            return False

    def send_alert_async(
        self,
        timestamp: float,
        gdrive_link: str = "",
        video_filename: str = "",
        snapshot_bytes: Optional[bytes] = None,
    ):
        """Send email alert in a background thread to avoid blocking video processing."""
        thread = threading.Thread(
            target=self.send_alert,
            args=(timestamp, gdrive_link, video_filename, snapshot_bytes),
            daemon=True,
            name="EmailAlertThread",
        )
        thread.start()
