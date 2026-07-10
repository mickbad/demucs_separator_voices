#!/usr/bin/env bash
#
# test_demucs.sh
#
# Script de test pour demucs_separator (macOS / Linux).
#
# Usage:
#   ./test_demucs.sh                  # utilise royalty-free-onlap-the-awakening.mp3 (même dossier que le script)
#   ./test_demucs.sh /chemin/vers.mp3 # utilise le fichier audio indiqué
#
# Variables d'environnement :
#   DEMUCS_BIN   chemin explicite vers l'exécutable demucs_separator
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

################################################################################
# Couleurs
################################################################################

RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
BLUE="\033[0;34m"
NC="\033[0m"

info()    { echo -e "${BLUE}==>${NC} $*"; }
success() { echo -e "${GREEN}==>${NC} $*"; }
warn()    { echo -e "${YELLOW}==>${NC} $*"; }
die()     { echo; echo -e "${RED}ERREUR:${NC} $*"; exit 1; }

################################################################################
# Fichier audio à traiter
################################################################################

if [[ $# -ge 1 ]]; then
    INPUT_FILE="$1"
else
    INPUT_FILE="$SCRIPT_DIR/royalty-free-onlap-the-awakening.mp3"
fi

[[ -f "$INPUT_FILE" ]] || die "Fichier audio introuvable : $INPUT_FILE"

info "Fichier audio : $INPUT_FILE"

################################################################################
# Localisation de l'exécutable demucs_separator
################################################################################

BIN=""

if [[ -n "${DEMUCS_BIN:-}" ]]; then
    BIN="$DEMUCS_BIN"
else
    for candidate in \
        "$SCRIPT_DIR/dist/demucs_separator" \
        "$SCRIPT_DIR/dist/demucs_separator_macos_arm64" \
        "$SCRIPT_DIR/dist/demucs_separator_macos_x86_64" \
        "$SCRIPT_DIR/dist/demucs_separator_linux"
    do
        if [[ -x "$candidate" ]]; then
            BIN="$candidate"
            break
        fi
    done

    if [[ -z "$BIN" ]] && command -v demucs_separator >/dev/null 2>&1; then
        BIN="$(command -v demucs_separator)"
    fi
fi

[[ -n "$BIN" ]] || die "Exécutable demucs_separator introuvable (dossier du script ou PATH). Définissez DEMUCS_BIN si besoin."

info "Exécutable utilisé : $BIN"

################################################################################
# Test de version
################################################################################

info "Vérification de la version..."

VERSION_OUTPUT="$("$BIN" --version 2>&1)" || die "Échec de '$BIN --version' : $VERSION_OUTPUT"

success "Version détectée : $VERSION_OUTPUT"

################################################################################
# Préparation du dossier de sortie
################################################################################

OUTPUT_DIR="$SCRIPT_DIR/output"

mkdir -p "$OUTPUT_DIR"

INPUT_BASENAME="$(basename "$INPUT_FILE")"
WORK_FILE="$OUTPUT_DIR/$INPUT_BASENAME"

info "Copie du fichier audio dans : $OUTPUT_DIR"
cp -f "$INPUT_FILE" "$WORK_FILE"

################################################################################
# Exécution
################################################################################

echo
info "Lancement de demucs_separator..."
echo

set +e
"$BIN" "$WORK_FILE"
STATUS=$?
set -e

echo

if [[ $STATUS -ne 0 ]]; then
    die "demucs_separator a terminé avec le code $STATUS"
fi

################################################################################
# Fin
################################################################################

success "Traitement terminé."
echo
echo "Fichiers produits dans : $OUTPUT_DIR"
ls -lh "$OUTPUT_DIR"
