# 🎥 Surveillance Vidéo Intelligente (Caméra -> Google Drive & Email)

Système de vidéo-surveillance automatique en Python :
- Enregistre une vidéo de **2 minutes** à chaque mouvement : **1 minute AVANT** + **1 minute APRÈS** le mouvement.
- Sauvegarde automatiquement la vidéo sur votre **Google Drive** (dans le dossier `Surveillance_Videos`).
- Vous envoie un **email d'alerte instantané** avec la **photo du passage** et le **lien direct vers la vidéo**.

---

## ⚡ COMMENT LANCER LE PROJET (Démarrage Rapide)

### 1. Lancer la surveillance avec affichage en direct :
```bash
./venv/bin/python3 main.py --preview
```
*(Une fenêtre s'ouvre avec le flux vidéo et les rectangles verts de détection. Appuyez sur la touche `q` pour quitter).*

### 2. Lancer la surveillance en arrière-plan (sans fenêtre) :
```bash
./venv/bin/python3 main.py
```

### 3. Tester localement (sans envoyer sur Google Drive ni envoyer d'email) :
```bash
./venv/bin/python3 main.py --no-upload --preview
```

---

## 💻 INSTALLATION SUR UN NOUVEL ORDINATEUR

Si vous changez d'ordinateur ou clonez ce projet ailleurs, suivez ces 4 étapes simples :

### Étape 1 : Cloner le dépôt GitHub
```bash
git clone https://github.com/guillaumepgt/Surveillance-Camera.git
cd Surveillance-Camera
```

### Étape 2 : Créer et installer l'environnement virtuel
```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```
*(Assurez-vous que `ffmpeg` est installé sur le système : `sudo apt install ffmpeg` sur Ubuntu/Debian).*

### Étape 3 : Récupérer vos fichiers de configuration
Placez vos 3 fichiers secrets à la racine du dossier `Surveillance-Camera/` :
1. **`.env`** (vos réglages et mot de passe d'application Gmail)
2. **`credentials.json`** (vos identifiants Google Cloud)
3. **`token.json`** (votre jeton Google Drive déjà validé)

*(Si vous n'avez pas de sauvegarde de ces 3 fichiers, copiez `.env.example` en `.env` : `cp .env.example .env` et lancez `./venv/bin/python3 setup_gdrive.py`).*

### Étape 4 : Lancer !
```bash
./venv/bin/python3 main.py --preview
```

---

## 🧪 VÉRIFIER QUE TOUT FONCTIONNE

Des scripts de test indépendants sont inclus pour tout tester en 1 commande :

- **Tester la caméra et l'encodage vidéo (test complet) :**
  ```bash
  ./venv/bin/python3 test_system.py
  ```

- **Tester la connexion Google Drive :**
  ```bash
  ./venv/bin/python3 setup_gdrive.py
  ```

- **Tester l'envoi d'email d'alerte avec photo :**
  ```bash
  ./venv/bin/python3 test_email.py
  ```

---

## 🛠️ OPTIONS DE LANCEMENT DISPONIBLES

Vous pouvez personnaliser le comportement en ligne de commande :

| Option | Description | Exemple |
|---|---|---|
| `--preview` | Ouvre une fenêtre avec l'image en direct et les détections | `./venv/bin/python3 main.py --preview` |
| `--camera` | Choisir la caméra (0 pour webcam, ou URL RTSP de caméra IP) | `--camera "rtsp://192.168.1.50:554/stream"` |
| `--min-area` | Sensibilité : surface minimale en pixels pour déclencher (défaut : 3500) | `--min-area 5000` (moins sensible) |
| `--cooldown` | Délai de repos en secondes après un événement avant réarmement | `--cooldown 60` (attend 60s) |
| `--pre-duration` | Durée enregistrée avant le mouvement (défaut : 60s) | `--pre-duration 60` |
| `--post-duration` | Durée enregistrée après le mouvement (défaut : 60s) | `--post-duration 60` |
| `--no-upload` | Désactive l'envoi sur Google Drive (sauvegarde locale uniquement) | `--no-upload` |
| `--no-keep-local` | Supprime la vidéo du PC une fois envoyée sur Google Drive | `--no-keep-local` |

---

## 🔑 CONFIGURATION INITIALE DÉTAILLÉE

### 1. Google Drive (OAuth2)
1. Allez sur la [Console Google Cloud](https://console.cloud.google.com/).
2. Créez un projet et activez l'**API Google Drive** dans *API et services > Bibliothèque*.
3. Dans *Écran de consentement OAuth*, configurez en type **Externe** et ajoutez votre adresse Gmail dans **Utilisateurs test**.
4. Dans *Identifiants*, créez un **ID client OAuth** (Application pour ordinateur de bureau).
5. Téléchargez le JSON, renommez-le `credentials.json` et déposez-le dans le dossier du projet.
6. Lancez `./venv/bin/python3 setup_gdrive.py` pour valider l'accès.

### 2. Alertes par Email (Gmail)
1. Rendez-vous sur [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
2. Créez un mot de passe d'application nommé `CameraSurveillance`.
3. Renseignez-le dans votre fichier `.env` :
   ```env
   ENABLE_EMAIL_ALERTS=true
   SMTP_SERVER=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=votre.email@gmail.com
   SMTP_PASSWORD=abcd efgh ijkl mnop
   EMAIL_TO=votre.email@gmail.com
   ```
4. Testez avec `./venv/bin/python3 test_email.py`.

---

## 📂 STRUCTURE DES FICHIERS

```
Surveillance-Camera/
├── main.py               # Programme principal de surveillance
├── config.py             # Configuration globale et lecture du .env
├── buffer_manager.py     # Tampon circulaire glissant en mémoire vive (JPEG en RAM)
├── motion_detector.py    # Détection de mouvement par soustraction de fond (MOG2)
├── video_writer.py       # Génération des vidéos MP4 H.264 optimisées (FFmpeg)
├── gdrive_uploader.py    # Téléversement en tâche de fond sur Google Drive
├── email_notifier.py     # Envoi des alertes email avec photo et lien
├── setup_gdrive.py       # Assistant interactif Google Drive
├── test_email.py         # Test d'envoi d'email
├── test_system.py        # Suite de tests automatiques
├── requirements.txt      # Dépendances Python
├── .env.example          # Modèle de configuration
└── recordings/           # Dossier local des vidéos enregistrées
```
