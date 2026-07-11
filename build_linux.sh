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

# --- Vérifications préalables ---
if ! command -v python3 &> /dev/null; then
    echo "ERREUR: python3 introuvable. Installez Python 3.9+ avant de continuer."
    exit 1
fi

if ! command -v ffmpeg &> /dev/null; then
    echo "AVERTISSEMENT: ffmpeg n'est pas installé sur cette machine."
    echo "Il n'est pas requis pour la compilation, mais SERA requis à l'exécution"
    echo "sur la machine cible (voir README.md)."
fi

# --- Nettoyage éventuel d'un ancien venv ---
# if [ -d "build_venv" ]; then
#     echo "[0/5] Suppression de l'ancien environnement virtuel..."
#     rm -rf build_venv
# fi

echo "[1/5] Création de l'environnement virtuel de build..."
python3 -m venv build_venv
# shellcheck disable=SC1091
source build_venv/bin/activate

echo "[2/5] Mise à jour de pip..."
pip install --upgrade pip

echo "[3/5] Installation de torch/torchaudio en version CPU-only..."
# IMPORTANT : on force l'index CPU de PyTorch pour éviter ~2.5-3 Go
# de dépendances CUDA (nvidia-cublas, nvidia-cudnn, nvidia-cusparse, etc.)
pip install \
    torch==2.5.1 \
    torchaudio==2.5.1 \
    --index-url https://download.pytorch.org/whl/cpu

# Fichier de contraintes : empêche pip de ré-installer une version CUDA
# de torch quand il résoudra les dépendances de demucs juste après.
cat > constraints.txt <<EOF
torch==2.5.1
torchaudio==2.5.1
EOF

echo "[4/5] Installation des autres dépendances (avec contrainte torch CPU)..."
pip install -r requirements.txt -c constraints.txt

# --- Vérification que torch est bien en CPU-only ---
echo ""
echo "--- Vérification torch ---"
python3 -c "
import torch
version = torch.__version__
cuda_ok = torch.cuda.is_available()
print(f'Version torch  : {version}')
print(f'CUDA disponible : {cuda_ok}')
if '+cpu' not in version:
    print()
    print('ERREUR: torch installé ne semble PAS être la version CPU-only (+cpu manquant).')
    print('Le build risque de faire plusieurs Go. Arrêt.')
    raise SystemExit(1)
if cuda_ok:
    print()
    print('ERREUR: CUDA est disponible, ce qui ne devrait pas être le cas.')
    raise SystemExit(1)
"
echo "--- OK : torch est bien en CPU-only ---"
echo ""

rm constraints.txt

echo "[5/5] Compilation avec PyInstaller..."
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
    --exclude-module torch.utils.tensorboard \
    --exclude-module torch.distributed \
    --exclude-module torch.testing \
    --exclude-module torch.utils.bottleneck \
    demucs_separator.py

deactivate

echo ""
echo "=== Terminé. ==="
echo "Exécutable généré : dist/demucs_separator"
echo "Taille :"
du -h dist/demucs_separator 2>/dev/null || true
echo ""
echo "Vous pouvez le copier sur une autre machine Linux compatible (voir README.md)."
