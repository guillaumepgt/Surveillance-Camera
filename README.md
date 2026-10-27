# 🎥 Surveillance Vidéo avec Sauvegarde Automatique sur Google Drive

Ce projet permet de capturer et sauvegarder automatiquement sur votre **Google Drive** une vidéo de **2 minutes** à chaque fois qu'un mouvement est détecté devant votre caméra :
- **1 minute AVANT** le déclenchement du mouvement (grâce à un tampon circulaire glissant en mémoire vive).
- **1 minute APRÈS** le mouvement.

---

## ⚡ Caractéristiques principales

- **Tampon circulaire intelligent (Rolling Buffer)** : Conserve en permanence les 60 dernières secondes en mémoire sous forme d'images compressées JPEG (empreinte RAM minime : ~50 Mo pour 1 minute à 20 FPS).
- **Détection de mouvement précise (MOG2)** : Algorithme de soustraction de fond adaptatif avec filtrage des ombres, flou gaussien et seuil de surface minimale pour éviter les faux positifs (reflets, bruit de capteur).
- **Encodage vidéo compatible Google Drive** : Génère un fichier MP4 encodé en H.264 (`yuv420p` + `faststart`) directement lisible en streaming dans l'interface web de Google Drive et sur smartphone.
- **Téléversement non bloquant** : L'encodage et l'envoi vers Google Drive sont gérés dans des threads en arrière-plan, garantissant une surveillance continue sans interruption ni perte d'images.
- **Deux méthodes d'envoi cloud au choix** :
  1. **Google Drive API (recommandé)** avec authentification OAuth 2.0 sécurisée.
  2. **Rclone** (si vous avez déjà un remote Google Drive configuré dans Rclone).
- **Assistant interactif** (`setup_gdrive.py`) pour tester la connexion Google Drive en 1 clic.

---

## 📂 Structure du projet

```
.
├── config.py             # Paramètres globaux et variables d'environnement
├── buffer_manager.py     # Gestionnaire de mémoire tampon circulaire (JPEG en RAM)
├── motion_detector.py    # Détection de mouvement par soustraction de fond (MOG2)
├── video_writer.py       # Assemblage des frames en MP4 H.264 via FFmpeg
├── gdrive_uploader.py    # Envoi vers Google Drive API / Rclone en tâche de fond
├── main.py               # Script principal de surveillance vidéo
├── setup_gdrive.py       # Assistant interactif de connexion Google Drive
├── test_system.py        # Suite de tests unitaires et d'intégration
├── requirements.txt      # Dépendances Python
├── .env.example          # Modèle de configuration personnalisée
└── recordings/           # Dossier local de stockage des vidéos générées
```

---

## 🚀 Installation rapide

Un environnement virtuel `venv` avec toutes les dépendances est déjà prêt dans ce dossier.

Si vous souhaitez le réinstaller ou l'installer ailleurs :

```bash
# 1. Créer l'environnement virtuel
python3 -m venv venv
source venv/bin/activate

# 2. Installer les dépendances
pip install -r requirements.txt
```

> **Note :** Le système utilise `/usr/bin/ffmpeg` pour l'encodage MP4 H.264 (déjà installé sur votre machine).

---

## 🔑 Configuration de Google Drive (en 5 minutes)

Pour envoyer les vidéos vers votre compte Google Drive via l'API officielle :

### Étape 1 : Obtenir vos identifiants Google (`credentials.json`)

1. Rendez-vous sur la [Console Google Cloud](https://console.cloud.google.com/).
2. Créez un nouveau projet (ex: `Surveillance-Camera`).
3. Activez l'API Google Drive :
   - Allez dans **API et services** > **Bibliothèque**.
   - Recherchez **Google Drive API** et cliquez sur **Activer**.
4. Configurez l'écran de consentement OAuth :
   - Allez dans **API et services** > **Écran de consentement OAuth**.
   - Choisissez le type **Externe**, renseignez un nom et votre adresse email.
   - Dans la section **Utilisateurs test** (Test users), ajoutez impérativement votre adresse Gmail.
5. Générez les identifiants :
   - Allez dans **API et services** > **Identifiants**.
   - Cliquez sur **Créer des identifiants** > **ID client OAuth**.
   - Type d'application : **Application pour ordinateur de bureau** (Desktop application).
   - Téléchargez le fichier JSON résultant.
6. Renommez ce fichier en `credentials.json` et déposez-le à la racine de ce projet.

### Étape 2 : Valider l'authentification avec l'assistant

Lancez simplement la commande :

```bash
./venv/bin/python3 setup_gdrive.py
```

- Une page s'ouvrira dans votre navigateur web pour vous demander d'autoriser l'application.
- Un jeton sécurisé `token.json` sera généré automatiquement.
- L'assistant créera le dossier `Surveillance_Videos` sur votre Google Drive et y déposera un fichier de test.

---

## 🎬 Démarrer la surveillance

### Lancement standard

```bash
./venv/bin/python3 main.py
```

Le script démarre avec la webcam par défaut (`/dev/video0`), maintient les 60 secondes précédentes en mémoire, et dès qu'un mouvement est détecté, enregistre les 60 secondes suivantes avant d'envoyer la vidéo de 2 minutes sur Google Drive.

### Avec prévisualisation en direct à l'écran

Pour afficher une fenêtre en direct avec les rectangles de mouvement et les FPS :

```bash
./venv/bin/python3 main.py --preview
```
*(Appuyez sur `q` pour fermer proprement la fenêtre et arrêter le script).*

### Options courantes

| Option | Description | Valeur par défaut |
|---|---|---|
| `--camera` | Index de la webcam (`0`, `1`) ou URL RTSP de caméra IP | `0` |
| `--preview` | Ouvre une fenêtre affichant le flux vidéo et les détections | Désactivé |
| `--pre-duration` | Durée du tampon avant mouvement (en secondes) | `60.0` |
| `--post-duration` | Durée d'enregistrement après mouvement (en secondes) | `60.0` |
| `--min-area` | Sensibilité : surface minimale en pixels pour déclencher | `1500` |
| `--uploader` | Méthode d'envoi (`gdrive_api`, `rclone`, ou `none`) | `gdrive_api` |
| `--no-upload` | Mode local uniquement (aucun envoi cloud) | `False` |
| `--no-keep-local` | Supprime la copie locale après téléversement réussi | `False` (garde copie) |
| `--no-overlay` | Ne pas incruster l'heure et l'état sur la vidéo | `False` |
| `--fps` | Fréquence d'images cible | `20` |

### Exemples d'utilisation :

**1. Tester sans envoyer sur le cloud (enregistrement local uniquement) :**
```bash
./venv/bin/python3 main.py --no-upload --preview
```

**2. Utiliser une caméra IP (flux RTSP) :**
```bash
./venv/bin/python3 main.py --camera "rtsp://admin:motdepasse@192.168.1.50:554/stream"
```

**3. Ajuster la sensibilité :**
- Si le script détecte trop de mouvements parasites (arbres, reflets) : augmenter `--min-area 3000`
- Si le script ne détecte pas les mouvements discrets : baisser `--min-area 800`

---

## ⚙️ Configuration permanente via `.env`

Vous pouvez personnaliser les valeurs par défaut en copiant le fichier `.env.example` :

```bash
cp .env.example .env
```

Vous pouvez y définir :
- Le nom du dossier Google Drive (`GDRIVE_FOLDER_NAME=Surveillance_Videos`)
- La source de caméra par défaut (`CAMERA_SOURCE=0` ou flux RTSP)
- La suppression automatique des vidéos locales après upload (`KEEP_LOCAL_COPY=false`)
- Les durées de tampon (`PRE_BUFFER_SECONDS=60.0`, `POST_BUFFER_SECONDS=60.0`)

---

## 📧 Alertes par Email (avec photo et lien Google Drive)

Le système peut vous envoyer un email instantané à chaque détection avec :
- L'heure exacte de l'intrusion.
- La photo JPEG prise au moment précis du déclenchement.
- Un bouton direct pour regarder la vidéo de 2 minutes sur Google Drive.

### Configuration rapide :

1. Générez un **Mot de passe d'application** pour votre compte Gmail :
   - Rendez-vous sur : [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
   - Donnez-lui un nom (ex: `CameraSurveillance`) et cliquez sur **Créer**.
   - Notez le mot de passe de 16 lettres généré.

2. Éditez le fichier `.env` :
   ```env
   ENABLE_EMAIL_ALERTS=true
   SMTP_SERVER=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=votre.email@gmail.com
   SMTP_PASSWORD=abcd efgh ijkl mnop
   EMAIL_TO=votre.email@gmail.com
   ```

3. Testez l'envoi d'un email de vérification :
   ```bash
   ./venv/bin/python3 test_email.py
   ```

---

## 🧪 Lancer la suite de tests

Pour vérifier le bon fonctionnement du tampon mémoire, de la détection de mouvement et du moteur d'encodage vidéo :

```bash
./venv/bin/python3 test_system.py
```

