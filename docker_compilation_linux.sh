#!/usr/bin/env bash
#
# docker_compilation_linux.sh
#
# procédure de compilation avec la bonne version de python (3.12) pour Linux
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Build Linux - Docker ==="

# préparation script
cat > /tmp/build_script.sh <<'EOF'
#!/bin/bash

apt update
apt install -y python3 python3-venv git build-essential ffmpeg

cd /app
./build_linux.sh

echo
echo "=== Build terminé ==="
EOF

docker run --rm -v "$(pwd)":/app -w /app python:3.12 bash /tmp/build_script.sh

rm /tmp/build_script.sh

echo
echo "=== Build terminé ==="

echo
echo "Executable :"
echo "  dist/demucs_separator"
echo
echo "Python utilisé :"
echo "  3.12"
echo
echo "Architecture :"
echo "  x86_64"
