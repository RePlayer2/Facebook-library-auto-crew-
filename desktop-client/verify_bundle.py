"""Reject incomplete or mixed-architecture release bundles."""

import json
import subprocess
import ssl
import sys
from pathlib import Path

contents = Path(sys.argv[1]) / "Contents"
arch = sys.argv[2]
resources = contents / "Resources"
ca_file = resources / "crawler/certs/cacert.pem"
context = ssl.create_default_context(cafile=str(ca_file))
assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
assert context.cert_store_stats()["x509_ca"] > 0
manifest = resources / "playwright/driver/package/browsers.json"
browsers = json.loads(manifest.read_text(encoding="utf-8"))["browsers"]
suffix = "x64" if arch == "x86_64" else "arm64"
required = [
    contents / "MacOS/Meta广告素材客户端",
    resources / "capcut-backend/capcut-backend",
    resources / "capcut-backend/_internal/ffprobe",
    resources / "capcut-backend/_internal/ffmpeg",
    resources / "playwright/driver/node",
]
for name in ("chromium", "chromium-headless-shell"):
    revision = next(item["revision"] for item in browsers if item["name"] == name)
    folder = resources / f"ms-playwright/{name.replace('-', '_')}-{revision}"
    if name == "chromium":
        executable = folder / f"chrome-mac-{suffix}/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
    else:
        executable = folder / f"chrome-headless-shell-mac-{suffix}/chrome-headless-shell"
    required.append(executable)
for executable in required:
    if not executable.is_file():
        raise SystemExit(f"Missing bundled executable: {executable}")
    architectures = subprocess.check_output(["/usr/bin/lipo", "-archs", str(executable)], text=True)
    if arch not in architectures.split():
        raise SystemExit(f"Wrong architecture: {executable}: {architectures}")
print(f"Bundle verification passed: {arch}, matching Chromium revisions and backend")
