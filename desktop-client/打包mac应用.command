#!/bin/bash
set -e
cd "$(dirname "$0")"

if [ -z "${PACKAGING_PYTHON:-}" ] && ! command -v pyinstaller >/dev/null 2>&1; then
  echo "没有检测到 pyinstaller，正在尝试安装..."
  python3 -m pip install pyinstaller
fi

DIST_PATH="${DIST_PATH:-dist}"
WORK_PATH="${WORK_PATH:-build}"
BACKEND_DIST="${BACKEND_DIST:-backend-dist}"
TARGET_ARCH="${TARGET_ARCH:-arm64}"
PACKAGING_PYTHON="${PACKAGING_PYTHON:-$(command -v python3)}"
BROWSER_CACHE="${BROWSER_CACHE:-$(pwd)/browsers-$TARGET_ARCH}"
if [ "$TARGET_ARCH" = x86_64 ]; then
  BROWSER_PLATFORM=mac15
else
  BROWSER_PLATFORM=mac15-arm64
fi
PLAYWRIGHT_HOST_PLATFORM_OVERRIDE="$BROWSER_PLATFORM" PLAYWRIGHT_BROWSERS_PATH="$BROWSER_CACHE" \
  /usr/bin/arch "-$TARGET_ARCH" "$PACKAGING_PYTHON" -m playwright install chromium

if [ ! -x "$BACKEND_DIST/capcut-backend/capcut-backend" ]; then
  bash build_bundled_backend.sh
fi

/usr/bin/arch "-$TARGET_ARCH" "$PACKAGING_PYTHON" -m PyInstaller \
  --noconfirm \
  --target-arch "$TARGET_ARCH" \
  --windowed \
  --name "Meta广告素材客户端" \
  --icon "$(pwd)/assets/AppIcon.icns" \
  --distpath "$DIST_PATH" \
  --workpath "$WORK_PATH" \
  --specpath "$WORK_PATH" \
  --add-data "$(pwd)/crawler/bundled_runtime.py:crawler" \
  --add-data "$(pwd)/crawler/certs:crawler/certs" \
  --add-data "$(pwd)/crawler/meta_material_pipeline.py:crawler" \
  --add-data "$(pwd)/crawler/meta_ad_card_extractor.py:crawler" \
  --add-data "$(pwd)/crawler/meta_ad_card_batch_by_ids.py:crawler" \
  --add-data "$(pwd)/crawler/meta_ad_page_until_id.py:crawler" \
  --add-data "$(pwd)/crawler/meta_ad_page_until_id_使用指南.md:crawler" \
  --add-data "$(pwd)/crawler/create_and_copy_dated_folders.py:crawler" \
  --add-data "$(pwd)/crawler/export_image_materials.py:crawler" \
  --add-data "$(pwd)/crawler/capcut_local_draft_import.py:crawler" \
  --add-data "$(pwd)/summary_scripts/generate_summary.py:summary_scripts" \
  --add-data "$(pwd)/summary_scripts/generate_image_summary.py:summary_scripts" \
  --hidden-import html \
  --hidden-import html.parser \
  --hidden-import json \
  --hidden-import urllib.request \
  --hidden-import urllib.parse \
  --hidden-import urllib.error \
  --hidden-import argparse \
  --hidden-import pathlib \
  --hidden-import re \
  --hidden-import shutil \
  --hidden-import socket \
  --hidden-import http.server \
  --hidden-import socketserver \
  --hidden-import contextlib \
  --hidden-import fnmatch \
  --hidden-import threading \
  --hidden-import time \
  --hidden-import base64 \
  --hidden-import dataclasses \
  --hidden-import typing \
  --collect-all playwright \
  "$(pwd)/crawler/meta_material_client.py"

APP_RESOURCES="$DIST_PATH/Meta广告素材客户端.app/Contents/Resources"
echo "正在复制完整内置后端..."
ditto "$BACKEND_DIST/capcut-backend" "$APP_RESOURCES/capcut-backend"
for required in capcut-backend _internal/ffprobe _internal/ffmpeg _internal/base_library.zip _internal/template/default2/draft_info.json; do
  if [ ! -f "$APP_RESOURCES/capcut-backend/$required" ]; then
    echo "打包失败：内置后端缺少 $required" >&2
    exit 1
  fi
done
test -x "$APP_RESOURCES/capcut-backend/capcut-backend"
if [ -d "$BROWSER_CACHE" ]; then
  echo "正在复制 Playwright 浏览器缓存到应用内..."
  rm -rf "$APP_RESOURCES/ms-playwright"
  ditto "$BROWSER_CACHE" "$APP_RESOURCES/ms-playwright"
else
  echo "打包失败：缺少浏览器目录 $BROWSER_CACHE" >&2
  exit 1
fi

/usr/bin/arch "-$TARGET_ARCH" "$PACKAGING_PYTHON" verify_bundle.py "$DIST_PATH/Meta广告素材客户端.app" "$TARGET_ARCH"
codesign --force --deep --sign - "$DIST_PATH/Meta广告素材客户端.app"
echo ""
echo "打包完成：$(pwd)/$DIST_PATH/Meta广告素材客户端.app"
read -n 1 -s -r -p "按任意键退出..." || true
