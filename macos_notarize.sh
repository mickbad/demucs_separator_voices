#!/usr/bin/env bash
#
# macos_notarize.sh
#
# Build final macOS :
# - vérifie l'exécutable
# - signe avec Developer ID Application
# - vérifie GateKeeper
# - notarise Apple (sauf --skip-notarize)
#
# Usage:
#   ./macos_notarize.sh
#   ./macos_notarize.sh --skip-notarize
#

set -euo pipefail

################################################################################
# Configuration
################################################################################

APP_NAME="demucs_separator"
DIST_DIR="dist"
APP_PATH="${DIST_DIR}/${APP_NAME}"

ZIP_FILE="${APP_NAME}.zip"

NOTARY_PROFILE="ricochets-notary-profile"

SKIP_NOTARIZE=false

################################################################################
# Arguments
################################################################################

usage() {
    cat <<EOF

Usage:
  $0 [option]

Options:
  --skip-notarize   Signe uniquement sans envoyer à Apple Notary
  --help            Affiche cette aide

EOF
}

for arg in "$@"; do
    case "$arg" in
        --skip-notarize)
            SKIP_NOTARIZE=true
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "Option inconnue : $arg"
            usage
            exit 1
            ;;
    esac
done

################################################################################
# Couleurs
################################################################################

RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
BLUE="\033[0;34m"
NC="\033[0m"

info() {
    echo -e "${BLUE}==>${NC} $*"
}

warn() {
    echo -e "${YELLOW}==>${NC} $*"
}

success() {
    echo -e "${GREEN}==>${NC} $*"
}

die() {
    echo
    echo -e "${RED}ERREUR:${NC} $*"
    exit 1
}

################################################################################
# Vérifications système
################################################################################

[[ "$(uname)" == "Darwin" ]] || die "Ce script fonctionne uniquement sur macOS."

command -v codesign >/dev/null || die "codesign absent."
command -v xcrun >/dev/null || die "xcrun absent."
command -v security >/dev/null || die "security absent."
command -v ditto >/dev/null || die "ditto absent."

[[ -f "$APP_PATH" ]] || die "Fichier absent : $APP_PATH"

################################################################################
# Test exécutable
################################################################################

info "Test de l'exécutable..."

VERSION=$("$APP_PATH" --version 2>/dev/null || true)

[[ -n "$VERSION" ]] || die "$APP_PATH --version échoue."

success "Version : $VERSION"

################################################################################
# Sélection certificat
################################################################################

info "Recherche Developer ID Application..."

CERTS=()

while IFS= read -r cert; do
    CERTS+=("$cert")
done < <(
    security find-identity -v -p codesigning |
    grep "Developer ID Application:" |
    sed -E 's/^.*"(.*)".*$/\1/' |
    sort -u
)

[[ ${#CERTS[@]} -gt 0 ]] || die "Aucun certificat Developer ID trouvé."

if [[ ${#CERTS[@]} == 1 ]]; then

    CERTIFICATE="${CERTS[0]}"

else

    echo
    echo "Certificats disponibles :"

    for i in "${!CERTS[@]}"
    do
        echo "  $((i+1))) ${CERTS[$i]}"
    done

    echo

    read -rp "Choisir le certificat : " CHOICE

    [[ "$CHOICE" =~ ^[0-9]+$ ]] ||
        die "Choix invalide."

    CERTIFICATE="${CERTS[$((CHOICE-1))]}"

fi

success "Certificat utilisé :"
echo "    $CERTIFICATE"

################################################################################
# Signature
################################################################################

info "Signature..."

codesign \
    --force \
    --options runtime \
    --timestamp \
    --entitlements entitlements.plist \
    --sign "$CERTIFICATE" \
    "$APP_PATH"    

success "Signature terminée."

################################################################################
# Validation signature
################################################################################

info "Validation signature..."

codesign \
    --verify \
    --deep \
    --strict \
    --verbose=2 \
    "$APP_PATH"

success "Signature valide."

################################################################################
# Mode local uniquement
################################################################################

if [[ "$SKIP_NOTARIZE" == true ]]; then

    warn "Mode --skip-notarize actif."

    info "Test GateKeeper..."

    spctl \
        --assess \
        --type execute \
        --verbose \
        "$APP_PATH"

    echo
    success "Signature terminée sans notarisation Apple."
    echo

    exit 0
fi

################################################################################
# Profil Notary
################################################################################

info "Vérification profil Notary..."

if xcrun notarytool history \
    --keychain-profile "$NOTARY_PROFILE" \
    >/dev/null 2>&1
then

    success "Profil '$NOTARY_PROFILE' trouvé."

else

    warn "Profil '$NOTARY_PROFILE' absent."

    read -rp "Apple ID : " APPLE_ID
    read -rp "Team ID : " TEAM_ID
    read -srp "App Specific Password : " APP_PASSWORD
    echo

    xcrun notarytool store-credentials \
        "$NOTARY_PROFILE" \
        --apple-id "$APPLE_ID" \
        --team-id "$TEAM_ID" \
        --password "$APP_PASSWORD"

    success "Profil créé."

fi

################################################################################
# ZIP
################################################################################

info "Création ZIP..."

rm -f "$ZIP_FILE"

ditto \
    -c \
    -k \
    --keepParent \
    "$APP_PATH" \
    "$ZIP_FILE"

success "ZIP créé : $ZIP_FILE"

################################################################################
# Notarisation
################################################################################

info "Envoi Apple Notary..."

xcrun notarytool submit \
    "$ZIP_FILE" \
    --keychain-profile "$NOTARY_PROFILE" \
    --wait

success "Apple a accepté la notarisation."

################################################################################
# Staple
################################################################################

info "Application ticket..."

case "$APP_PATH" in
    *.app|*.pkg|*.dmg)
        xcrun stapler staple "$APP_PATH"
        xcrun stapler validate "$APP_PATH"
        success "Ticket appliqué."
        ;;
    *)
        warn "Stapling non applicable aux exécutables Mach-O."
        ;;
esac

################################################################################
# GateKeeper
################################################################################

info "Validation finale GateKeeper..."

case "$APP_PATH" in
    *.app|*.pkg|*.dmg)
        spctl \
            --assess \
            --type execute \
            --verbose \
            "$APP_PATH"
        success "Valide."
        ;;
    *)
        warn "Stapling non applicable aux exécutables Mach-O."
        ;;
esac


echo
echo "================================================"
success "Distribution prête"
echo "================================================"
echo
echo "Fichier signé : $APP_PATH"
echo "Archive       : $ZIP_FILE"
echo

################################################################################
# Test exécutable
################################################################################

info "Test de l'exécutable..."

VERSION=$("$APP_PATH" --version 2>/dev/null || true)

[[ -n "$VERSION" ]] || die "$APP_PATH --version échoue."

success "Version : $VERSION"
