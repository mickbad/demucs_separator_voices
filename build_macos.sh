#!/usr/bin/env bash
#
# build_macos.sh
#
# Compile demucs_separator.py en exécutable macOS avec Python 3.12 forcé.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Build macOS - demucs_separator ==="
echo

################################################################################
# Vérification architecture
################################################################################

ARCH="$(uname -m)"

echo "Architecture détectée : $ARCH"

if [[ "$ARCH" != "arm64" && "$ARCH" != "x86_64" ]]; then
    echo "ERREUR: architecture inconnue : $ARCH"
    exit 1
fi


################################################################################
# Recherche Python 3.12
################################################################################

PYTHON_BIN=""

for candidate in \
    python3.12 \
    /opt/homebrew/bin/python3.12 \
    /usr/local/bin/python3.12
do
    if command -v "$candidate" >/dev/null 2>&1; then
        PYTHON_BIN="$(command -v "$candidate")"
        break
    fi
done


if [[ -z "$PYTHON_BIN" ]]; then
    echo
    echo "ERREUR: Python 3.12 introuvable."
    echo
    echo "Installez-le avec par exemple :"
    echo "  brew install python@3.12"
    exit 1
fi


################################################################################
# Vérification version Python
################################################################################

PY_VERSION="$("$PYTHON_BIN" --version 2>&1)"

echo "Python sélectionné : $PYTHON_BIN"
echo "Version           : $PY_VERSION"

if ! echo "$PY_VERSION" | grep -q "Python 3\.12\."; then
    echo
    echo "ERREUR: Python 3.12 requis."
    echo "Version détectée : $PY_VERSION"
    exit 1
fi


################################################################################
# Vérification dépendances système
################################################################################

if ! command -v ffmpeg >/dev/null 2>&1; then
    echo
    echo "AVERTISSEMENT: ffmpeg absent."
    echo "Installation recommandée : brew install ffmpeg"
    echo
fi


################################################################################
# Création environnement virtuel
################################################################################

VENV_DIR="build_venv"

echo
echo "[1/5] Création environnement virtuel Python 3.12..."

rm -rf "$VENV_DIR"

"$PYTHON_BIN" -m venv "$VENV_DIR"


# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"


################################################################################
# Vérifications venv
################################################################################

echo
echo "Python du venv : $(which python)"
echo "Version        : $(python --version)"

if ! python --version | grep -q "Python 3\.12\."; then
    echo "ERREUR: le venv n'utilise pas Python 3.12."
    exit 1
fi


################################################################################
# Installation dépendances
################################################################################

echo
echo "[2/5] Installation dépendances..."

python -m pip install --upgrade pip

python -m pip install \
    -r requirements.txt


################################################################################
# Vérification PyInstaller
################################################################################

echo
echo "[3/5] Vérification PyInstaller..."

pyinstaller --version

echo
echo "PyInstaller utilisé :"
which pyinstaller


################################################################################
# Compilation
################################################################################

echo
echo "[4/5] Compilation PyInstaller..."

rm -rf build dist

pyinstaller \
  --onefile \
  --clean \
  --noconfirm \
  --name demucs_separator \
  --collect-all numpy \
  --collect-all demucs \
  --collect-all torch \
  --collect-all torchaudio \
  --collect-all julius \
  --collect-all openunmix \
  --collect-data certifi \
  demucs_separator.py


################################################################################
# Test local
################################################################################

echo
echo "[5/5] Test exécutable..."

./dist/demucs_separator --version


################################################################################
# Fin
################################################################################

deactivate


echo
echo "=============================================="
echo "Build terminé"
echo "=============================================="
echo
echo "Executable :"
echo "  dist/demucs_separator"
echo
echo "Python utilisé :"
echo "  $PY_VERSION"
echo
echo "Architecture :"
echo "  $ARCH"
echo
