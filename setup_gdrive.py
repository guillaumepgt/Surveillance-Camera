#!/usr/bin/env python3
"""
Assistant de configuration et de test pour Google Drive.
Vérifie les prérequis, guide l'utilisateur pour l'obtention de credentials.json,
réalise l'authentification OAuth2 et teste l'envoi d'un fichier.
"""

from datetime import datetime
import os
from pathlib import Path
import sys

from config import CREDENTIALS_FILE, TOKEN_FILE, GDRIVE_FOLDER_NAME
from gdrive_uploader import GoogleDriveUploader


def print_banner():
    print("=" * 70)
    print("   ASSISTANT DE CONFIGURATION GOOGLE DRIVE - CAMERA SURVEILLANCE")
    print("=" * 70)


def print_credentials_instructions(credentials_path: Path):
    print(f"\n[!] Le fichier '{credentials_path.name}' est introuvable dans ce dossier :")
    print(f"    {credentials_path.parent}\n")
    print("Pour connecter le script à votre Google Drive, suivez ces étapes rapides :")
    print("-" * 70)
    print("1. Rendez-vous sur la console Google Cloud :")
    print("   https://console.cloud.google.com/")
    print("\n2. Créez un nouveau projet (ou sélectionnez un projet existant).")
    print("\n3. Activez l'API Google Drive :")
    print("   - Menu 'API et services' > 'Bibliothèque' (Library)")
    print("   - Recherchez 'Google Drive API' et cliquez sur 'Activer'.")
    print("\n4. Configurez l'écran de consentement OAuth :")
    print("   - Menu 'API et services' > 'Écran de consentement OAuth'")
    print("   - Type d'utilisateur : 'Externe' (External)")
    print("   - Renseignez un nom (ex: 'CameraSurveillance') et votre email.")
    print("   - Dans la section 'Utilisateurs test' (Test users), AJOUTEZ votre adresse Gmail.")
    print("\n5. Créez les identifiants OAuth :")
    print("   - Menu 'API et services' > 'Identifiants' (Credentials)")
    print("   - Cliquez sur 'Créer des identifiants' > 'ID client OAuth'")
    print("   - Type d'application : 'Application pour ordinateur de bureau' (Desktop app)")
    print("   - Cliquez sur 'Créer', puis téléchargez le fichier JSON.")
    print(f"\n6. Renommez le fichier téléchargé en '{credentials_path.name}'")
    print(f"   et placez-le dans : {credentials_path.parent}")
    print("-" * 70)
    print("\nUne fois le fichier copié, relancez : python3 setup_gdrive.py\n")


def run_setup():
    print_banner()

    if not CREDENTIALS_FILE.exists():
        print_credentials_instructions(CREDENTIALS_FILE)
        sys.exit(1)

    print(f"[OK] Fichier '{CREDENTIALS_FILE.name}' détecté.")

    uploader = GoogleDriveUploader(
        credentials_file=CREDENTIALS_FILE,
        token_file=TOKEN_FILE,
        folder_name=GDRIVE_FOLDER_NAME,
    )

    print("\n[*] Initialisation de l'authentification Google Drive...")
    try:
        uploader.authenticate(interactive=True)
    except Exception as e:
        print(f"\n[ERREUR] Échec de l'authentification : {e}")
        sys.exit(1)

    print(f"[OK] Authentification réussie ! Jeton sauvegardé dans '{TOKEN_FILE.name}'.")
    print(f"[OK] Dossier Google Drive cible : '{GDRIVE_FOLDER_NAME}' (ID: {uploader.folder_id})")

    # Perform a test upload
    print("\n[*] Test d'envoi d'un fichier de vérification sur Google Drive...")
    test_file = Path("test_gdrive_sync.txt")
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        test_file.write_text(f"Test de synchronisation réussi !\nDate et heure : {now_str}\n")
        resp = uploader.upload_file(test_file)
        print(f"[OK] Fichier de test téléversé avec succès !")
        print(f"     Lien direct : {resp.get('webViewLink')}")
    except Exception as e:
        print(f"\n[ERREUR] Échec de l'envoi du fichier test : {e}")
        sys.exit(1)
    finally:
        test_file.unlink(missing_ok=True)

    print("\n" + "=" * 70)
    print("[SUCCÈS] La configuration Google Drive est prête et opérationnelle !")
    print("Vous pouvez maintenant démarrer la surveillance avec :")
    print("    python3 main.py")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_setup()
