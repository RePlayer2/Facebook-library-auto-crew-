#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
INTEL_PYTHON="$(pwd)/.venv-intel/bin/python"
TOOLS="$(pwd)/intel-tools"
export PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=mac15
export BROWSER_CACHE="$(pwd)/browsers-x86_64"
PLAYWRIGHT_BROWSERS_PATH="$BROWSER_CACHE" /usr/bin/arch -x86_64 "$INTEL_PYTHON" -m playwright install chromium
export BACKEND_PYTHON="$(pwd)/.venv-backend-intel/bin/python" BACKEND_ARCH=x86_64
export BACKEND_DIST=backend-dist-intel BACKEND_BUILD=backend-build-intel
export FFMPEG_BIN="$TOOLS/ffmpeg" FFPROBE_BIN="$TOOLS/ffprobe"
bash build_bundled_backend.sh
export PACKAGING_PYTHON="$INTEL_PYTHON" TARGET_ARCH=x86_64
export DIST_PATH=dist-intel WORK_PATH=build-intel
bash 打包mac应用.command
