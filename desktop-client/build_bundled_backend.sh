#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
BACKEND_SOURCE="${BACKEND_SOURCE:-$(pwd)/vendor/capcut-mate}"
if [ ! -f "$BACKEND_SOURCE/config/sticker.json" ]; then
  gzip -dk "$BACKEND_SOURCE/config/sticker.json.gz"
fi
BACKEND_PYTHON="${BACKEND_PYTHON:-$BACKEND_SOURCE/.venv/bin/python}"
BACKEND_DIST="${BACKEND_DIST:-backend-dist}"
BACKEND_BUILD="${BACKEND_BUILD:-backend-build}"
FFMPEG_BIN="${FFMPEG_BIN:-/opt/homebrew/bin/ffmpeg}"
FFPROBE_BIN="${FFPROBE_BIN:-/opt/homebrew/bin/ffprobe}"
BACKEND_ARCH="${BACKEND_ARCH:-arm64}"
/usr/bin/arch "-$BACKEND_ARCH" "$BACKEND_PYTHON" -m PyInstaller \
  --noconfirm --onedir --name capcut-backend \
  --target-arch "$BACKEND_ARCH" \
  --distpath "$BACKEND_DIST" --workpath "$BACKEND_BUILD" --specpath "$BACKEND_BUILD" \
  --paths "$BACKEND_SOURCE" \
  --collect-all src --collect-all uvicorn --collect-all pymediainfo \
  --collect-all imageio --collect-all oss2 --collect-all qcloud_cos \
  --collect-all email_validator \
  --add-data "$BACKEND_SOURCE/config:config" \
  --add-data "$BACKEND_SOURCE/template:template" \
  --add-data "$BACKEND_SOURCE/assets:assets" \
  --add-data "$BACKEND_SOURCE/src/pyJianYingDraft/assets:src/pyJianYingDraft/assets" \
  --add-data "$BACKEND_SOURCE/LICENSE:licenses" \
  --add-data "$BACKEND_SOURCE/NOTICE:licenses" \
  --add-binary "$FFMPEG_BIN:." \
  --add-binary "$FFPROBE_BIN:." \
  crawler/bundled_capcut_backend.py
