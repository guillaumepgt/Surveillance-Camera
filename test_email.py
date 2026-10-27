#!/usr/bin/env python3
"""
Script de test pour vérifier la configuration des alertes par email.
Envoie un email de test avec une image de démonstration vers votre adresse.
"""

from datetime import datetime
import os
import sys
import time
import cv2
import numpy as np

import config
from email_notifier import EmailNotifier


def main():
    print("=" * 70)
    print("   TEST DE NOTIFICATION EMAIL - CAMERA SURVEILLANCE")
    print("=" * 70)

    if not config.SMTP_USER or not config.SMTP_PASSWORD:
        print("\n[!] Les identifiants email ne sont pas encore configurés.")
        print("Veuillez renseigner dans votre fichier .env :")
        print("    SMTP_USER=votre.email@gmail.com")
        print("    SMTP_PASSWORD=votre_mot_de_passe_d_application")
        print("    EMAIL_TO=votre.email@gmail.com")
        print("\nPour Gmail : utilisez un 'Mot de passe d'application' (16 lettres)")
        print("généré depuis : https://myaccount.google.com/apppasswords\n")
        sys.exit(1)

    print(f"[*] Serveur SMTP : {config.SMTP_SERVER}:{config.SMTP_PORT}")
    print(f"[*] Expéditeur   : {config.SMTP_USER}")
    print(f"[*] Destinataire : {config.EMAIL_TO or config.SMTP_USER}")

    notifier = EmailNotifier(
        smtp_server=config.SMTP_SERVER,
        smtp_port=config.SMTP_PORT,
        smtp_user=config.SMTP_USER,
        smtp_password=config.SMTP_PASSWORD,
        recipient_emails=[config.EMAIL_TO or config.SMTP_USER],
    )

    # Generate dummy snapshot image with text
    img = np.zeros((300, 500, 3), dtype=np.uint8)
    cv2.putText(img, "TEST CAMERA", (50, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 2)
    dt_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cv2.putText(img, dt_str, (50, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1)
    _, enc = cv2.imencode(".jpg", img)
    snapshot_bytes = enc.tobytes()

    print("\n[*] Envoi de l'email de test en cours...")
    success = notifier.send_alert(
        timestamp=time.time(),
        gdrive_link="https://drive.google.com",
        video_filename="test_video_2min.mp4",
        snapshot_bytes=snapshot_bytes,
    )

    if success:
        print("\n[SUCCÈS] L'email de test a été envoyé ! Vérifiez votre boîte de réception.")
    else:
        print("\n[ERREUR] Échec de l'envoi. Vérifiez votre mot de passe d'application.")


if __name__ == "__main__":
    main()
