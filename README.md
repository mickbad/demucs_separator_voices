# Demucs Separator

Outil en ligne de commande qui utilise [Demucs](https://github.com/facebookresearch/demucs)
(modèle `htdemucs`) pour séparer un fichier audio en deux stems :

- **voix** (`vocals`)
- **instruments** (`no_vocals` = tout sauf la voix)

et produit deux fichiers MP3 à côté du fichier source :

```
mon_morceau.mp3
mon_morceau-voices.mp3
mon_morceau-instruments.mp3
```

Si le fichier source est un **MP3**, les tags **ID3** (titre, artiste, album,
pochette/cover, année, etc.) sont automatiquement recopiés dans les deux
fichiers générés.

Support indie dev here :)

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-☕-FFDD00?style=for-the-badge)](https://buymeacoffee.com/mickbad)

---

## 1. Contenu du dépôt

| Fichier                  | Rôle                                                        |
|---------------------------|-------------------------------------------------------------|
| `demucs_separator.py`     | Script principal (multiplateforme)                          |
| `requirements.txt`        | Dépendances Python                                          |
| `build_linux.sh`          | Compilation en exécutable autonome pour Linux                |
| `build_macos.sh`          | Compilation en exécutable autonome pour macOS                |
| `build_windows.bat`       | Compilation en exécutable autonome pour Windows              |
| `entitlements.plist`      | Entitlements macOS requis pour la signature (voir §4.2)      |
| `macos_notarize.sh`       | Signature + notarisation Apple de l'exécutable macOS          |
| `test_demucs.sh`          | Script de test rapide (macOS / Linux)                        |
| `test_demucs.bat`         | Script de test rapide (Windows)                               |
| `README.md`               | Cette documentation                                          |

---

## 2. Utilisation (avec Python installé)

```bash
python3 demucs_separator.py /chemin/vers/fichier_audio.mp3
```

Formats d'entrée : tout format lu par Demucs/ffmpeg (mp3, wav, flac, m4a, ogg...).

Sortie, dans le **même dossier** que le fichier d'entrée :

- `<nom>-voices.mp3`
- `<nom>-instruments.mp3`

### Afficher la version

```bash
python3 demucs_separator.py --version
# ou, une fois compilé :
demucs_separator --version        # Linux/macOS
demucs_separator.exe --version    # Windows
```

Affiche le numéro de version (`__version__` dans `demucs_separator.py`) et
quitte immédiatement (le programme ne traite aucun fichier dans ce cas).

### Tester rapidement l'exécutable compilé

Deux scripts sont fournis pour vérifier en une commande qu'un exécutable
compilé fonctionne correctement de bout en bout :

```bash
# macOS / Linux
./test_demucs.sh                      # utilise test.mp3 du même dossier
./test_demucs.sh /chemin/vers/fic.mp3 # ou un autre fichier audio
```

```bat
:: Windows
test_demucs.bat
test_demucs.bat C:\chemin\vers\fic.mp3
```

Chaque script :
1. vérifie la présence de l'exécutable `demucs_separator` (dossier du
   script, puis `PATH` — chemin explicite possible via la variable
   d'environnement `DEMUCS_BIN`) ;
2. teste `--version` ;
3. copie le fichier audio dans `./output` puis lance le traitement dessus
   (le programme écrivant toujours dans le dossier du fichier d'entrée,
   voir §2.2) ;
4. liste les fichiers produits dans `./output` en fin d'exécution.

### Étapes internes du script

1. Résolution des certificats SSL (voir §2.3) — nécessaire avant tout appel
   réseau, notamment pour le téléchargement du modèle Demucs.
2. Recherche de `ffmpeg` (voir §2.1).
3. Séparation Demucs en mode `--two-stems=vocals` (modèle `htdemucs`) →
   génère `vocals.wav` et `no_vocals.wav` dans un dossier temporaire.
4. Conversion des deux `.wav` en `.mp3` (320 kbps) via `ffmpeg`, avec suivi
   de progression réel (voir §2.2).
5. Si le fichier source est un `.mp3` : copie de toutes les frames ID3
   (y compris la pochette `APIC`) du fichier source vers les deux fichiers
   de sortie via `mutagen`.
6. Nettoyage systématique du dossier temporaire Demucs (`vocals.wav`,
   `no_vocals.wav`, dossier `htdemucs/...`), y compris en cas d'erreur en
   cours de traitement (bloc `finally`).

### 2.1. Résolution du chemin de ffmpeg

Le programme cherche l'exécutable `ffmpeg` dans cet ordre :

1. **Le répertoire d'exécution du programme** (le dossier contenant
   `demucs_separator.py`, ou le dossier contenant l'exécutable compilé
   `demucs_separator`/`demucs_separator.exe`) — utile pour distribuer un
   binaire *portable* en plaçant `ffmpeg`/`ffmpeg.exe` juste à côté.
2. **Le `PATH` du système**, sinon.

Le chemin complet trouvé est résolu une seule fois au démarrage et conservé
dans une variable (`ffmpeg_bin`) réutilisée pour tous les appels de
conversion. Si `ffmpeg` est introuvable dans les deux emplacements, le
programme s'arrête avec une erreur JSON (voir §2.2).

### 2.2. Sorties écran (format JSON, une ligne = un événement)

Le programme n'affiche **que des lignes JSON sur stdout**, pensées pour être
lues et parsées par un programme appelant (une ligne = un objet JSON
complet, séparé par `\n`).

**Pendant le traitement**, une ligne à chaque étape/mise à jour de
progression :

```json
{"running": true, "eta": 15, "progress": 22.5}
```

- `running` : toujours `true` tant que le traitement est en cours.
- `eta` : temps restant estimé en secondes, fourni uniquement pendant la
  phase Demucs (`null` pendant les conversions ffmpeg, où seule
  l'avancée en pourcentage est disponible).
- `progress` : avancement global en pourcentage (0 à 100), réparti ainsi :
  - **0 → 90** : séparation Demucs (étape la plus longue).
  - **90 → 95** : conversion MP3 de la piste voix.
  - **95 → 99** : conversion MP3 de la piste instruments.
  - **99 → 100** : copie des tags ID3 (le cas échéant) puis fin.

  Les conversions ffmpeg (90-95 et 95-99) sont suivies en temps réel via
  `ffmpeg -progress pipe:1` : la durée du fichier source est d'abord
  déterminée, puis chaque valeur `out_time_ms` renvoyée par ffmpeg est
  convertie en pourcentage et mappée linéairement dans la plage
  correspondante. Si la durée n'a pas pu être déterminée pour un fichier
  donné, le programme continue sans granularité intermédiaire pour cette
  étape (pas d'erreur, juste moins de mises à jour).

**À la fin du traitement (succès)**, une dernière ligne :

```json
{"running": false, "voice": "/chemin/vers/fichier-voices.mp3", "intruments": "/chemin/vers/fichier-instruments.mp3", "err": null}
```

**En cas d'erreur** (fichier introuvable, ffmpeg absent, échec Demucs,
échec de conversion...), une seule ligne d'erreur, et le programme quitte
avec un code de sortie `1` :

```json
{"running": false, "err": "message décrivant l'erreur"}
```

### 2.3. Certificats SSL (téléchargement du modèle Demucs)

Le tout premier lancement télécharge les poids du modèle `htdemucs` via
`torch.hub` (HTTPS). Dans un **exécutable compilé** (PyInstaller), l'OpenSSL
embarqué ne trouve pas toujours le magasin de certificats CA du système sur
la machine cible, notamment lorsque l'exécutable a été signé/notarisé sur
une machine puis distribué sur une autre. Cela provoque une erreur du type :

```
CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate
```

Pour éviter ce problème, `demucs_separator.py` force explicitement
l'utilisation du magasin de certificats fourni par le paquet Python
`certifi` (variables d'environnement `SSL_CERT_FILE` et
`REQUESTS_CA_BUNDLE`, positionnées en tout début de script, avant tout
import réseau). C'est pourquoi :

- `certifi` doit être présent dans `requirements.txt` ;
- les scripts de build doivent collecter ses données (`--collect-data
  certifi` dans la commande PyInstaller, voir §4).

---

## 3. Prérequis — Exécution du script Python (mode « source »)

Sur **toutes les plateformes** (Windows, Linux, macOS) :

- **Python 3.9 ou supérieur**
- **ffmpeg**, nécessaire pour la conversion WAV → MP3 (indépendamment de
  Demucs). Le programme le cherche d'abord **à côté du script/exécutable**,
  puis dans le **`PATH`** (voir §2.1) :
  - Windows : télécharger sur https://ffmpeg.org/download.html et soit
    ajouter le dossier `bin` au `PATH`, soit copier `ffmpeg.exe` dans le
    même dossier que `demucs_separator.py`/`demucs_separator.exe` ;
    alternative : `choco install ffmpeg` / `winget install ffmpeg`
  - macOS : `brew install ffmpeg`, ou copier le binaire `ffmpeg` à côté du
    script/exécutable
  - Linux (Debian/Ubuntu) : `sudo apt install ffmpeg`, ou copier le binaire
    `ffmpeg` à côté du script/exécutable
- Dépendances Python (voir `requirements.txt`, y compris `certifi` — voir
  §2.3) :
  ```bash
  pip install -r requirements.txt
  ```
- **Connexion Internet lors de la première utilisation** : Demucs télécharge
  automatiquement les poids du modèle `htdemucs` (~80-300 Mo selon le modèle)
  dans un cache local (`~/.cache/torch/hub/checkpoints` sous Linux/macOS,
  `%USERPROFILE%\.cache\torch\hub\checkpoints` sous Windows). Les exécutions
  suivantes n'ont plus besoin d'Internet.
- Un GPU CUDA est **optionnel** : le script fonctionne en CPU par défaut
  (plus lent mais sans configuration supplémentaire).

### Note sur torch/torchaudio — pourquoi les versions sont épinglées

`requirements.txt` fixe volontairement `torch==2.5.1` et `torchaudio==2.5.1`
(au lieu de simples bornes minimales). C'est nécessaire car **depuis
torchaudio 2.9**, les fonctions `torchaudio.save()`/`load()` (utilisées en
interne par Demucs pour écrire les fichiers `.wav` des stems) reposent sur
**TorchCodec**, un paquet séparé non installé par défaut et qui nécessite
en plus des bibliothèques FFmpeg natives liées à une version précise.
Sans cette épingle de version, `pip install -r requirements.txt` peut
installer la dernière version de torchaudio et le programme échoue avec :

```json
{"running": false, "err": "TorchCodec is required for save_with_torchcodec. Please install torchcodec to use this function."}
```

En restant sur `torchaudio==2.5.1`, Demucs utilise l'ancien backend
(FFmpeg/SoundFile intégré à torchaudio) qui fonctionne nativement sur
Windows, macOS et Linux sans dépendance supplémentaire. **Ne modifiez pas
ces versions** sans vérifier que TorchCodec (et ses bibliothèques FFmpeg
natives compatibles) est bien installé et fonctionnel sur les trois
plateformes cibles.

Si malgré tout une version incompatible de torchaudio se retrouve installée
(environnement partagé, dépendance transitive d'un autre paquet...), le
programme le détecte et renvoie un message d'erreur explicite invitant à
réinstaller les dépendances épinglées via `pip install -r requirements.txt`.

---

## 4. Compilation en exécutable autonome

Chaque script de build crée un environnement virtuel, installe les
dépendances, puis utilise [PyInstaller](https://pyinstaller.org/) pour
produire un exécutable unique (`--onefile`) embarquant Python, Demucs et
PyTorch.

⚠️ **PyInstaller ne fait pas de compilation croisée.** Il faut compiler
**sur** chaque plateforme cible (compiler sous Windows pour obtenir un
`.exe`, sous macOS pour un binaire macOS, sous Linux pour un binaire Linux).

### 4.1. Linux

```bash
chmod +x build_linux.sh
./build_linux.sh
```

**Prérequis pour compiler :**
- Python 3.9+ et `python3-venv`
- `pip`
- Connexion Internet (téléchargement des paquets pip)

Résultat : `dist/demucs_separator`

**Prérequis pour exécuter le binaire sur une autre machine Linux :**
- Même architecture CPU (généralement `x86_64`)
- Une **glibc de version égale ou supérieure** à celle de la machine de
  build (compiler idéalement sur une distribution assez ancienne/stable,
  ex. Ubuntu 20.04/22.04, pour une compatibilité maximale)
- `ffmpeg` installé sur la machine cible (non embarqué dans l'exécutable)
- Connexion Internet lors de la toute première exécution (téléchargement
  du modèle Demucs, sauf si le cache `~/.cache/torch` est déjà pré-rempli
  et copié sur la machine cible)

### 4.2. macOS

#### Build

```bash
chmod +x build_macos.sh
./build_macos.sh
```

**Prérequis pour compiler :**
- Python 3.12 (le script vérifie explicitement cette version — voir le
  contenu de `build_macos.sh`)
- Xcode Command Line Tools (`xcode-select --install`)
- Connexion Internet

La commande PyInstaller inclut notamment `--collect-data certifi`, requis
pour embarquer le magasin de certificats CA (voir §2.3) — ne pas l'omettre
en cas de modification du script de build.

Résultat : `dist/demucs_separator`

#### Signature et notarisation

Un exécutable macOS destiné à être distribué **hors de la machine de
build** doit être signé (et notarisé pour éviter tout avertissement
Gatekeeper). C'est le rôle de `macos_notarize.sh` :

```bash
./macos_notarize.sh                  # signe + notarise auprès d'Apple
./macos_notarize.sh --skip-notarize  # signature locale uniquement
```

Le script :
1. teste que `dist/demucs_separator --version` fonctionne ;
2. sélectionne (ou demande de choisir) un certificat **Developer ID
   Application** présent dans le trousseau ;
3. signe l'exécutable avec le **Hardened Runtime** (`--options runtime`)
   et le fichier `entitlements.plist` fourni à la racine du dépôt ;
4. valide la signature (`codesign --verify`) et, en mode complet, envoie
   l'exécutable à l'Apple Notary Service (`xcrun notarytool submit --wait`).

**Pourquoi `entitlements.plist` est indispensable ici :** l'exécutable est
compilé en `--onefile` : à l'exécution, PyInstaller extrait `Python.framework`
et les bibliothèques natives (torch, etc.) dans un dossier temporaire. Ces
fichiers conservent leur signature d'origine (celle de la machine de build),
différente du Developer ID utilisé pour signer l'exécutable final. Avec le
Hardened Runtime, macOS applique par défaut la *Library Validation*, qui
refuse de charger du code signé par un Team ID différent — d'où une erreur
au lancement de type :

```
Failed to load Python shared library ... (code signature ... not valid for
use in process: mapping process and mapped file (non-platform) have
different Team IDs)
```

L'entitlement `com.apple.security.cs.disable-library-validation` (avec
`allow-unsigned-executable-memory`, `allow-jit` et
`allow-dyld-environment-variables`, présents dans `entitlements.plist`)
lève cette restriction spécifiquement pour cet exécutable, tout en restant
compatible avec la notarisation Apple. Sans ce fichier, l'exécutable
fonctionne sur la machine de build mais échoue au lancement sur toute autre
machine, une fois signé avec Hardened Runtime.

**Prérequis pour exécuter le binaire sur une autre machine macOS :**
- Même architecture que la machine de build : un binaire compilé sur
  **Apple Silicon (arm64)** ne fonctionne pas nativement sur **Intel
  (x86_64)**, et inversement. Pour distribuer sur les deux, compilez une
  fois sur chaque type de machine (ou lancez le build sous Rosetta 2 côté
  Apple Silicon pour produire un binaire x86_64).
- `ffmpeg` installé sur la machine cible
- Un exécutable **non signé** est bloqué par défaut par Gatekeeper : en
  usage interne/personnel uniquement, l'utilisateur peut autoriser
  manuellement l'exécution via
  *Préférences Système → Confidentialité et sécurité → Autoriser quand même*
  ou `xattr -d com.apple.quarantine demucs_separator`. Pour une
  distribution publique, utilisez `macos_notarize.sh` (voir ci-dessus).
- Connexion Internet lors de la toute première exécution (téléchargement
  du modèle Demucs)

### 4.3. Windows

Depuis une invite de commandes (`cmd.exe`) :

```bat
build_windows.bat
```

**Prérequis pour compiler :**
- Python 3.9+ installé avec l'option **« Add python.exe to PATH »** cochée
- Connexion Internet

Résultat : `dist\demucs_separator.exe`

**Prérequis pour exécuter le binaire sur une autre machine Windows :**
- Windows 10/11 64 bits (même architecture que la machine de build,
  généralement `x86_64`)
- `ffmpeg.exe` installé et présent dans le `PATH` de la machine cible
- Le Windows Defender SmartScreen peut avertir au premier lancement d'un
  exécutable non signé : l'utilisateur devra cliquer sur
  *Informations complémentaires → Exécuter quand même*. Pour éviter cet
  avertissement en distribution publique, il faut signer l'exécutable avec
  un certificat de signature de code.
- Connexion Internet lors de la toute première exécution (téléchargement
  du modèle Demucs)

---

## 5. Résumé des prérequis « machine cible » (exécutable compilé)

Quelle que soit la plateforme, sur la machine qui **exécute** l'exécutable
compilé (et non celle qui l'a compilé) :

1. **ffmpeg** doit être disponible séparément (il n'est pas embarqué dans
   l'exécutable PyInstaller) : soit copié dans le même dossier que
   l'exécutable, soit installé et accessible dans le `PATH` (voir §2.1
   pour l'ordre de recherche exact).
2. **Accès Internet** requis lors du tout premier lancement, le temps que
   Demucs télécharge les poids du modèle `htdemucs` (mise en cache ensuite) —
   voir §2.3 en cas d'erreur de certificat SSL au moment du téléchargement.
3. **Même architecture/OS** que la machine de compilation (voir détails
   par plateforme ci-dessus) — pas de compilation croisée avec PyInstaller.
4. Sur macOS, un exécutable destiné à être distribué doit être signé via
   `macos_notarize.sh` (§4.2) — un exécutable simplement copié depuis
   `dist/` sans signature ne fonctionnera pas correctement sur une autre
   machine une fois le Hardened Runtime appliqué sans les bons entitlements.
5. Espace disque : l'exécutable autonome est volumineux (plusieurs centaines
   de Mo à ~1-2 Go) car il embarque PyTorch ; prévoir de l'espace disque en
   conséquence, ainsi que pour le cache du modèle Demucs.

---

## 6. Dépannage

- **`{"running": false, "err": "TorchCodec is required for save_with_torchcodec..."}`** :
  une version de torchaudio ≥ 2.9 a été installée au lieu de la version
  épinglée `2.5.1`. Réinstallez avec les versions exactes du dépôt :
  ```bash
  pip uninstall -y torch torchaudio
  pip install -r requirements.txt
  ```
  Voir la section 3 (« Note sur torch/torchaudio ») pour le détail du
  problème.
- **`{"running": false, "err": "ffmpeg introuvable (ni dans le répertoire
  d'exécution, ni dans le PATH)"}`** : soit copiez `ffmpeg`/`ffmpeg.exe`
  dans le même dossier que le script/exécutable, soit installez-le et
  vérifiez avec `ffmpeg -version` dans un terminal.
- **`CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate`**
  lors du téléchargement du modèle : voir §2.3. Vérifiez que `certifi` est
  bien présent dans `requirements.txt` et que le build macOS/Windows/Linux
  a bien été fait avec `--collect-data certifi` dans la commande
  PyInstaller.
- **`Failed to load Python shared library ... different Team IDs`** au
  lancement d'un exécutable macOS signé : signature effectuée sans
  `entitlements.plist` (voir §4.2). Re-signez avec
  `codesign --entitlements entitlements.plist ...` (déjà géré par
  `macos_notarize.sh`) et re-notarisez.
- **Téléchargement du modèle très lent / bloqué** (le programme reste
  bloqué sur la ligne `{"running": true, "eta": null, "progres": 0}`) :
  vérifiez la connexion Internet et les éventuels pare-feux/proxy
  d'entreprise ; le modèle Demucs est téléchargé depuis les serveurs de
  Meta/Demucs lors du tout premier lancement.
- **Erreur mémoire / très lent sur CPU** : la séparation Demucs est
  gourmande en calcul ; sur une machine sans GPU, comptez plusieurs fois la
  durée du morceau en temps de traitement.
- **Le binaire compilé ne se lance pas sur une autre machine** : vérifiez
  que l'architecture et l'OS correspondent exactement à la machine de
  compilation (voir §4), et sur macOS que l'exécutable a bien été signé
  avec `entitlements.plist` (voir ci-dessus).
- **Fichiers temporaires** : le dossier temporaire créé par Demucs
  (`vocals.wav`, `no_vocals.wav`, etc.) est automatiquement supprimé en fin
  de traitement, que celui-ci réussisse ou échoue. Si le processus est tué
  brutalement (`kill -9`, coupure de courant), il peut rester un dossier
  résiduel dans le répertoire temporaire du système (`/tmp/demucs_*` sous
  Linux/macOS, `%TEMP%\demucs_*` sous Windows) qu'il faudra alors supprimer
  manuellement.
  
