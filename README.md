# Demucs Separator

Outil en ligne de commande qui utilise [Demucs](https://github.com/facebookresearch/demucs)
pour séparer un fichier audio en **2, 4 ou 6 stems** (voir §2 « Nombre de
stems »), et produit un fichier MP3 par stem, à côté du fichier source :

```
mon_morceau.mp3
mon_morceau-voices.mp3
mon_morceau-instruments.mp3
```
(et éventuellement `-percussions.mp3`, `-basse.mp3`, `-guitare.mp3`,
`-piano.mp3` selon `--stems`, voir §2).

Si le fichier source est un **MP3**, les tags **ID3** (titre, artiste, album,
pochette/cover, année, etc.) sont automatiquement recopiés dans **tous**
les fichiers générés.

---

## 1. Contenu du dépôt

| Fichier                  | Rôle                                                        |
|---------------------------|-------------------------------------------------------------|
| `demucs_separator.py`     | Script principal (multiplateforme)                          |
| `requirements.txt`        | Dépendances Python                                          |
| `build_linux.sh`          | Compilation en exécutable autonome pour Linux                |
| `build_macos.sh`          | Compilation en exécutable autonome pour macOS                |
| `build_windows.bat`       | Compilation en exécutable autonome pour Windows              |
| `entitlements.plist`      | Entitlements macOS requis pour la signature (voir §5.2)      |
| `macos_notarize.sh`       | Signature + notarisation Apple de l'exécutable macOS          |
| `test_demucs.sh`          | Script de test rapide (macOS / Linux)                        |
| `test_demucs.bat`         | Script de test rapide (Windows)                               |
| `README.md`               | Cette documentation                                          |

---

## 2. Utilisation (avec Python installé)

```bash
python3 demucs_separator.py /chemin/vers/fichier_audio.mp3
```

Sans option, la séparation reste en 2 stems (voix / instruments) comme dans
la version précédente ; seul le dispositif de calcul change : il est
désormais choisi automatiquement (`--device auto`, voir ci-dessous) au lieu
d'être toujours forcé sur `cpu`. Sur une machine sans GPU détecté, le
comportement (et les performances) restent identiques à avant.

Formats d'entrée : tout format lu par Demucs/ffmpeg (mp3, wav, flac, m4a, ogg...).

### Options

```bash
python3 demucs_separator.py fichier.mp3 [--stems {2,4,6}] [--device {cpu,cuda,mps}]
```

- **`--stems`** (défaut `2`) : nombre de pistes à produire.
  - `2` : `voix` / `instruments` — modèle `htdemucs`, mode rapide
    `--two-stems` (comportement historique, inchangé).
  - `4` : `voix` / `percussions` / `instruments` — modèle `htdemucs`,
    séparation complète des 4 stems natifs (`vocals`/`drums`/`bass`/`other`),
    `instruments` étant le mélange de `bass`+`other`.
  - `6` : `voix` / `percussions` / `basse` / `guitare` / `piano` /
    `instruments` — modèle `htdemucs_6s` (6 stems natifs), `instruments`
    correspondant ici uniquement au reliquat `other` (ce qui n'est ni voix,
    ni batterie, ni basse, ni guitare, ni piano).

  ⚠️ Plus `--stems` est élevé, plus le calcul est long : la séparation
  complète (4 ou 6 stems) est plus coûteuse que le mode rapide 2 stems, et
  le modèle 6 stems (`htdemucs_6s`) est lui-même un peu plus lourd que
  `htdemucs`.

- **`--device`** (défaut `auto`) : dispositif de calcul pour Demucs.
  - `auto` : choisit automatiquement le meilleur dispositif disponible sur
    la machine, dans l'ordre de préférence **cuda > mps > cpu**. C'est le
    choix recommandé pour ne pas avoir à se soucier de la machine cible ;
    le dispositif effectivement retenu est indiqué sur **stderr**
    (`--device auto : dispositif sélectionné = ...`).
  - `cpu` : force le CPU, fonctionne partout, sans configuration
    supplémentaire.
  - `cuda` : force le GPU NVIDIA (accélère fortement le traitement).
  - `mps` : force le GPU Apple Silicon (M1/M2/M3...).
  - Si un dispositif demandé **explicitement** (`cuda` ou `mps`) n'est pas
    disponible sur la machine, le programme **replie automatiquement sur
    `cpu`** ; un message d'avertissement est alors envoyé sur **stderr**
    (jamais sur stdout, qui reste réservé aux lignes JSON, voir §2.2).

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

1. Résolution des certificats SSL (voir §2.4) — nécessaire avant tout appel
   réseau, notamment pour le téléchargement du/des modèle(s) Demucs.
2. Recherche de `ffmpeg` (voir §2.3).
3. Résolution du dispositif de calcul (`--device`), avec repli sur cpu si
   indisponible.
4. Séparation Demucs (voir §2.1 pour le modèle/mode selon `--stems`) →
   génère les fichiers wav bruts dans un dossier temporaire (inchangé
   depuis la version précédente pour `--stems 2`).
5. Pour chaque stem final : mixage éventuel de plusieurs pistes brutes
   (ex. `bass.wav` + `other.wav` pour `instruments` en mode 4 stems),
   normalisation anti-écrêtage si besoin, puis conversion en `.mp3`
   (320 kbps) via `ffmpeg`, avec suivi de progression réel.
6. Si le fichier source est un `.mp3` : copie de toutes les frames ID3
   (y compris la pochette `APIC`) du fichier source vers **chacun** des
   fichiers de sortie générés, via `mutagen`.
7. Nettoyage systématique du dossier temporaire Demucs, y compris en cas
   d'erreur en cours de traitement (bloc `finally`).

### 2.1. Modèles Demucs utilisés selon `--stems`

| `--stems` | Modèle        | Mode                          | Téléchargement |
|-----------|---------------|--------------------------------|-----------------|
| 2         | `htdemucs`    | rapide (`--two-stems vocals`) | automatique, 1ère utilisation |
| 4         | `htdemucs`    | séparation complète            | automatique, 1ère utilisation (partagé avec le mode 2 stems si déjà téléchargé) |
| 6         | `htdemucs_6s` | séparation complète            | automatique, 1ère utilisation (modèle distinct, téléchargement supplémentaire) |

Aucune action manuelle n'est requise : la librairie `demucs` télécharge et
met en cache le modèle nécessaire dès qu'il est utilisé pour la première
fois (voir §3, prérequis réseau).

### 2.2. Sorties écran (format JSON, une ligne = un événement)

Le programme n'affiche **que des lignes JSON sur stdout**, pensées pour être
lues et parsées par un programme appelant (une ligne = un objet JSON
complet, séparé par `\n`). Les éventuels messages d'avertissement (ex. repli
`--device` sur cpu) partent sur **stderr**, jamais sur stdout.

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
  - **0 → 70** : séparation Demucs (étape la plus longue, quel que soit
    `--stems`).
  - **70 → 99** : conversions MP3, une piste après l'autre. La plage
    restante (70-99) est répartie **à parts égales entre le nombre de
    stems demandé** : par exemple avec `--stems 4`, chaque piste
    (voix/percussions/instruments) reçoit environ 9,7 points de
    progression ; avec `--stems 2` (comportement historique), les deux
    conversions se répartissent la plage comme avant.
  - **99 → 100** : copie des tags ID3 (le cas échéant) puis fin.

  Les conversions ffmpeg sont suivies en temps réel via
  `ffmpeg -progress pipe:1` : la durée du fichier source est d'abord
  déterminée, puis chaque valeur `out_time_ms` renvoyée par ffmpeg est
  convertie en pourcentage et mappée linéairement dans la sous-plage
  correspondante. Si la durée n'a pas pu être déterminée pour un fichier
  donné, le programme continue sans granularité intermédiaire pour cette
  étape (pas d'erreur, juste moins de mises à jour).

**À la fin du traitement (succès)**, une dernière ligne dont les **clés
présentes dépendent de `--stems`** — seules les pistes effectivement
produites apparaissent, aucune clé "vide" ou `null` pour un stem non
demandé :

```json
// --stems 2 (défaut, comportement historique inchangé)
{"running": false, "voice": "/chemin/fichier-voices.mp3", "intruments": "/chemin/fichier-instruments.mp3", "err": null}

// --stems 4 (ajoute "percussions")
{"running": false, "voice": "...", "percussions": "...", "intruments": "...", "err": null}

// --stems 6 (ajoute "percussions", "basse", "guitare", "piano")
{"running": false, "voice": "...", "percussions": "...", "basse": "...", "guitare": "...", "piano": "...", "intruments": "...", "err": null}
```

> Note : la clé `intruments` (sans "s" après le "t") est un intitulé
> historique conservé volontairement pour ne pas casser la compatibilité
> avec les intégrations existantes qui consomment déjà cette sortie en
> mode 2 stems.

**En cas d'erreur** (fichier introuvable, ffmpeg absent, échec Demucs,
échec de conversion...), une seule ligne d'erreur, et le programme quitte
avec un code de sortie `1` :

```json
{"running": false, "err": "message décrivant l'erreur"}
```

### 2.3. Résolution du chemin de ffmpeg

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

### 2.4. Certificats SSL (téléchargement des modèles Demucs)

Le tout premier lancement pour un modèle donné (`htdemucs` ou
`htdemucs_6s`) télécharge ses poids via `torch.hub` (HTTPS). Dans un
**exécutable compilé** (PyInstaller), l'OpenSSL embarqué ne trouve pas
toujours le magasin de certificats CA du système sur la machine cible,
notamment lorsque l'exécutable a été signé/notarisé sur une machine puis
distribué sur une autre. Cela provoque une erreur du type :

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
  certifi` dans la commande PyInstaller, voir §5).

---

## 3. Prérequis — Exécution du script Python (mode « source »)

Sur **toutes les plateformes** (Windows, Linux, macOS) :

- **Python 3.9 ou supérieur**
- **ffmpeg**, nécessaire pour la conversion WAV → MP3 (indépendamment de
  Demucs). Le programme le cherche d'abord **à côté du script/exécutable**,
  puis dans le **`PATH`** (voir §2.3) :
  - Windows : télécharger sur https://ffmpeg.org/download.html et soit
    ajouter le dossier `bin` au `PATH`, soit copier `ffmpeg.exe` dans le
    même dossier que `demucs_separator.py`/`demucs_separator.exe` ;
    alternative : `choco install ffmpeg` / `winget install ffmpeg`
  - macOS : `brew install ffmpeg`, ou copier le binaire `ffmpeg` à côté du
    script/exécutable
  - Linux (Debian/Ubuntu) : `sudo apt install ffmpeg`, ou copier le binaire
    `ffmpeg` à côté du script/exécutable
- Dépendances Python (voir `requirements.txt`, y compris `certifi` — voir
  §2.4) :
  ```bash
  pip install -r requirements.txt
  ```
- **Connexion Internet lors de la première utilisation de chaque modèle** :
  Demucs télécharge automatiquement les poids du modèle utilisé
  (`htdemucs` pour `--stems 2/4`, `htdemucs_6s` pour `--stems 6` — environ
  80-300 Mo chacun) dans un cache local
  (`~/.cache/torch/hub/checkpoints` sous Linux/macOS,
  `%USERPROFILE%\.cache\torch\hub\checkpoints` sous Windows). Les
  exécutions suivantes utilisant le même modèle n'ont plus besoin
  d'Internet. Si tu comptes utiliser `--stems 6`, prévois donc une
  connexion Internet au moins une fois pour ce modèle supplémentaire.
- Un **GPU est optionnel** : le script fonctionne en CPU par défaut (plus
  lent mais sans configuration supplémentaire). Utilise `--device cuda`
  (NVIDIA) ou `--device mps` (Apple Silicon) si disponible pour accélérer
  nettement le traitement, en particulier avec `--stems 4` ou `6` qui
  demandent une séparation complète plus coûteuse que le mode rapide
  2 stems.

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

### Dépendance ajoutée : `numpy`

Le mixage de plusieurs pistes brutes en une seule sortie (par exemple
`bass.wav` + `other.wav` pour la piste `instruments` en mode `--stems 4`)
nécessite `numpy` en plus de `soundfile` (déjà présent). `numpy` est déjà
installé de façon quasi systématique comme dépendance transitive de
`torch`/`soundfile`, mais il est recommandé de l'ajouter explicitement à
`requirements.txt` :

```
numpy
```

C'est la **seule** modification apportée à `requirements.txt` — le reste
(versions épinglées de `torch`/`torchaudio`, `demucs`, `mutagen`,
`pyinstaller`, `certifi`, `soundfile`) reste strictement identique.

---

## 4. Exemples d'utilisation

```bash
# Comportement par défaut : 2 stems, dispositif choisi automatiquement
python3 demucs_separator.py chanson.mp3

# 4 stems (ajoute les percussions), en forçant le CPU
python3 demucs_separator.py chanson.mp3 --stems 4 --device cpu

# 6 stems (guitare/piano isolés), en forçant un GPU NVIDIA
python3 demucs_separator.py chanson.mp3 --stems 6 --device cuda
```

---

## 5. Compilation en exécutable autonome

Chaque script de build crée un environnement virtuel, installe les
dépendances, puis utilise [PyInstaller](https://pyinstaller.org/) pour
produire un exécutable unique (`--onefile`) embarquant Python, Demucs et
PyTorch. Les options `--stems` et `--device` fonctionnent de la même
façon une fois l'exécutable compilé — aucune adaptation des scripts de
build n'est nécessaire pour ça.

⚠️ **PyInstaller ne fait pas de compilation croisée.** Il faut compiler
**sur** chaque plateforme cible (compiler sous Windows pour obtenir un
`.exe`, sous macOS pour un binaire macOS, sous Linux pour un binaire Linux).

### 5.1. Linux

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
- Connexion Internet lors de la toute première exécution **de chaque
  modèle utilisé** (voir §2.1 et §3), sauf si le cache `~/.cache/torch`
  est déjà pré-rempli et copié sur la machine cible

### 5.2. macOS

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
pour embarquer le magasin de certificats CA (voir §2.4) — ne pas l'omettre
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
- Connexion Internet lors de la toute première exécution de chaque modèle
  utilisé (voir §2.1 et §3)
- Pour `--device mps`, aucune configuration supplémentaire : PyTorch
  détecte nativement le GPU Apple Silicon si disponible.

### 5.3. Windows

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
- Connexion Internet lors de la toute première exécution de chaque modèle
  utilisé (voir §2.1 et §3)
- Pour `--device cuda`, les pilotes NVIDIA/CUDA compatibles avec la version
  de `torch` épinglée doivent être installés sur la machine cible.

---

## 6. Résumé des prérequis « machine cible » (exécutable compilé)

Quelle que soit la plateforme, sur la machine qui **exécute** l'exécutable
compilé (et non celle qui l'a compilé) :

1. **ffmpeg** doit être disponible séparément (il n'est pas embarqué dans
   l'exécutable PyInstaller) : soit copié dans le même dossier que
   l'exécutable, soit installé et accessible dans le `PATH` (voir §2.3
   pour l'ordre de recherche exact).
2. **Accès Internet** requis lors du tout premier lancement **de chaque
   modèle utilisé** (`htdemucs` pour `--stems 2/4`, `htdemucs_6s` pour
   `--stems 6`), le temps que Demucs télécharge les poids correspondants
   (mise en cache ensuite) — voir §2.4 en cas d'erreur de certificat SSL au
   moment du téléchargement.
3. **Même architecture/OS** que la machine de compilation (voir détails
   par plateforme ci-dessus) — pas de compilation croisée avec PyInstaller.
4. Sur macOS, un exécutable destiné à être distribué doit être signé via
   `macos_notarize.sh` (§5.2) — un exécutable simplement copié depuis
   `dist/` sans signature ne fonctionnera pas correctement sur une autre
   machine une fois le Hardened Runtime appliqué sans les bons entitlements.
5. Espace disque : l'exécutable autonome est volumineux (plusieurs centaines
   de Mo à ~1-2 Go) car il embarque PyTorch ; prévoir de l'espace disque en
   conséquence, ainsi que pour le cache des modèles Demucs (compter
   double si `--stems 6` est utilisé en plus de `--stems 2/4`, les deux
   modèles étant mis en cache séparément).
6. Pour `--device cuda`/`mps` : GPU et pilotes compatibles installés sur la
   machine cible. En leur absence, le programme se replie automatiquement
   sur `cpu` (voir §2 « Options »).

---

## 7. Dépannage

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
  lors du téléchargement d'un modèle : voir §2.4. Vérifiez que `certifi` est
  bien présent dans `requirements.txt` et que le build macOS/Windows/Linux
  a bien été fait avec `--collect-data certifi` dans la commande
  PyInstaller.
- **`Failed to load Python shared library ... different Team IDs`** au
  lancement d'un exécutable macOS signé : signature effectuée sans
  `entitlements.plist` (voir §5.2). Re-signez avec
  `codesign --entitlements entitlements.plist ...` (déjà géré par
  `macos_notarize.sh`) et re-notarisez.
- **Téléchargement d'un modèle très lent / bloqué** (le programme reste
  bloqué sur la ligne `{"running": true, "eta": null, "progress": 0}`) :
  vérifiez la connexion Internet et les éventuels pare-feux/proxy
  d'entreprise ; les modèles Demucs sont téléchargés depuis les serveurs de
  Meta/Demucs lors du tout premier lancement de chaque modèle.
- **`{"running": false, "err": "Output channels > 65536 not supported at the MPS device..."}`** :
  limitation connue du backend MPS de PyTorch sur certaines opérations du
  modèle `htdemucs` (partie "transformer hybride"). Le script positionne
  automatiquement `PYTORCH_ENABLE_MPS_FALLBACK=1` dès son démarrage (avant
  tout import de torch), ce qui autorise PyTorch à replier ces opérations
  précises sur CPU tout en gardant le reste du calcul sur le GPU MPS. Si
  l'erreur persiste malgré tout après mise à jour du script, vérifie que
  tu utilises bien la version corrigée de `demucs_separator.py` (le
  binaire compilé doit être régénéré après cette modification).
- **`usage: demucs_separator [-h] [--version] ... : error: unrecognized
  arguments: -B -S -I -c` qui apparaît en boucle**, en particulier avec un
  exécutable compilé (PyInstaller) : c'est un problème classique lié à
  `multiprocessing` dans un exécutable "onefile". Torch/Demucs utilisent
  `multiprocessing` en interne (notamment le `resource_tracker`), qui
  relance normalement un processus enfant en réinvoquant l'interpréteur
  Python avec des flags internes. Dans un exécutable packagé, il n'y a pas
  de véritable interpréteur à relancer : c'est le programme compilé
  lui-même qui se relance, et ces flags internes atterrissent alors dans
  notre propre `argparse`, qui les rejette — d'où le message d'usage
  répété, une fois par processus enfant relancé. Le script appelle
  désormais `multiprocessing.freeze_support()` tout en haut du bloc
  `if __name__ == "__main__":`, ce qui règle ce problème (comportement
  standard requis par PyInstaller dès qu'un exécutable frozen utilise
  `multiprocessing`, voir la
  [documentation PyInstaller](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#multi-processing)).
  **Recompile l'exécutable** après avoir récupéré cette version du script
  pour que le correctif s'applique.
  vérifiez le message éventuel sur stderr indiquant un repli automatique
  sur `cpu` faute de GPU détecté par PyTorch (pilotes manquants, GPU non
  compatible, etc.).
- **Erreur mémoire / très lent sur CPU** : la séparation Demucs est
  gourmande en calcul, en particulier en séparation complète (`--stems 4`
  ou `6`, plus coûteuse que le mode rapide 2 stems) ; sur une machine sans
  GPU, comptez plusieurs fois la durée du morceau en temps de traitement.
- **Le binaire compilé ne se lance pas sur une autre machine** : vérifiez
  que l'architecture et l'OS correspondent exactement à la machine de
  compilation (voir §5), et sur macOS que l'exécutable a bien été signé
  avec `entitlements.plist` (voir ci-dessus).
- **Fichiers temporaires** : le dossier temporaire créé par Demucs
  (fichiers wav bruts, dossier `htdemucs/...` ou `htdemucs_6s/...`) est
  automatiquement supprimé en fin de traitement, que celui-ci réussisse ou
  échoue. Si le processus est tué brutalement (`kill -9`, coupure de
  courant), il peut rester un dossier résiduel dans le répertoire
  temporaire du système (`/tmp/demucs_*` sous Linux/macOS,
  `%TEMP%\demucs_*` sous Windows) qu'il faudra alors supprimer
  manuellement.
