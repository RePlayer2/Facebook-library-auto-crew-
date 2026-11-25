#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="Meta广告素材客户端"
ENTRY="$ROOT/crawler/meta_material_client.py"
DIST_DIR="$ROOT/dist"
BUILD_DIR="$ROOT/build"
SPEC_DIR="$ROOT/crawler"

cd "$ROOT"

if ! command -v pyinstaller >/dev/null 2>&1; then
  echo "pyinstaller 未安装。请先在当前环境安装：pip install pyinstaller"
  exit 1
fi

pyinstaller \
  --noconfirm \
  --windowed \
  --name "$APP_NAME" \
  --icon "$ROOT/assets/AppIcon.icns" \
  --distpath "$DIST_DIR" \
  --workpath "$BUILD_DIR" \
  --specpath "$SPEC_DIR" \
  --add-data "$ROOT/crawler/meta_material_pipeline.py:crawler" \
  --add-data "$ROOT/crawler/meta_ad_card_extractor.py:crawler" \
  --add-data "$ROOT/crawler/meta_ad_card_batch_by_ids.py:crawler" \
  --add-data "$ROOT/crawler/meta_ad_page_until_id.py:crawler" \
  --add-data "$ROOT/crawler/meta_ad_page_until_id_使用指南.md:crawler" \
  --add-data "$ROOT/crawler/create_and_copy_dated_folders.py:crawler" \
  --add-data "$ROOT/crawler/capcut_local_draft_import.py:crawler" \
  --add-data "$ROOT/summary_scripts/generate_summary.py:summary_scripts" \
  --add-data "$ROOT/summary_scripts/generate_image_summary.py:summary_scripts" \
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
  "$ENTRY"

BROWSER_CACHE="$HOME/Library/Caches/ms-playwright"
APP_RESOURCES="$DIST_DIR/$APP_NAME.app/Contents/Resources"
if [ -d "$BROWSER_CACHE" ]; then
  echo "正在复制 Playwright 浏览器缓存到应用内..."
  rm -rf "$APP_RESOURCES/ms-playwright"
  ditto "$BROWSER_CACHE" "$APP_RESOURCES/ms-playwright"
else
  echo "警告：未找到 Playwright 浏览器缓存：$BROWSER_CACHE"
  echo "请先运行：python3 -m playwright install chromium"
fi

echo ""
echo "已生成应用：$DIST_DIR/$APP_NAME.app"
