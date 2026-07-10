#!/usr/bin/env bash
#
# build_linux.sh
# Compile demucs_separator.py en exécutable autonome pour Linux (x86_64).
#
# A exécuter sur une machine Linux. L'exécutable produit ne fonctionnera
# que sur des machines de même architecture (généralement x86_64) et
# de version glibc compatible (voir README.md).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Build Linux - demucs_separator ==="

if ! command -v python3 &> /dev/null; then
    echo "ERREUR: python3 introuvable. Installez Python 3.9+ avant de continuer."
    exit 1
fi

if ! command -v ffmpeg &> /dev/null; then
    echo "AVERTISSEMENT: ffmpeg n'est pas installé sur cette machine."
    echo "Il n'est pas requis pour la compilation, mais SERA requis à l'exécution"
    echo "sur la machine cible (voir README.md)."
fi

echo "[1/4] Création de l'environnement virtuel de build..."
python3 -m venv build_venv
# shellcheck disable=SC1091
source build_venv/bin/activate

echo "[2/4] Installation des dépendances..."
pip install --upgrade pip
pip install -r requirements.txt

echo "[3/4] Compilation avec PyInstaller..."
pyinstaller \
  --onefile \
  --clean \
  --noconfirm \
  --name demucs_separator \
  --collect-all numpy \
  --collect-all demucs \
  --collect-all torch \
  --collect-all torchaudio \
  --collect-all torchcodec \
  --collect-all julius \
  --collect-all openunmix \
  --collect-data certifi \
  demucs_separator.py

deactivate

echo "[4/4] Terminé."
echo ""
echo "Exécutable généré : dist/demucs_separator"
echo "Vous pouvez le copier sur une autre machine Linux compatible (voir README.md)."
