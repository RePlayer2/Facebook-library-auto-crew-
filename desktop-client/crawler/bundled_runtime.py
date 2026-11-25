"""Resolve application-owned browser assets in every worker process."""

import json
import os
import platform
import ssl
import sys
from functools import lru_cache
from pathlib import Path


def bundled_ca_file() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent.parent / "Resources/crawler/certs/cacert.pem"
    return Path(__file__).resolve().parent / "certs/cacert.pem"


@lru_cache(maxsize=1)
def media_ssl_context() -> ssl.SSLContext:
    ca_file = bundled_ca_file()
    if not ca_file.is_file():
        raise OSError(f"应用内可信证书文件缺失：{ca_file}；请重新复制完整应用包。")
    # An explicit CA file avoids Python's build-machine default certificate path.
    return ssl.create_default_context(cafile=str(ca_file))


def configure_runtime() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    contents = Path(sys.executable).resolve().parent.parent
    candidates = [
        contents / "Resources/ms-playwright",
        Path(sys._MEIPASS) / "ms-playwright",
    ]
    root = next((path for path in candidates if path.is_dir()), None)
    if root is None:
        raise RuntimeError("应用包缺少内置 Chromium，请使用完整应用包。")
    ca_file = bundled_ca_file()
    if not ca_file.is_file():
        raise RuntimeError(f"应用内可信证书文件缺失：{ca_file}")
    os.environ["SSL_CERT_FILE"] = str(ca_file)
    os.environ["REQUESTS_CA_BUNDLE"] = str(ca_file)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(root)
    # Node's hardware detection can disagree with an Intel app under Rosetta.
    os.environ["PLAYWRIGHT_HOST_PLATFORM_OVERRIDE"] = (
        "mac15" if platform.machine() == "x86_64" else "mac15-arm64"
    )
    os.environ["SIMILAR_CRAW_WORKER_EXE"] = sys.executable
    os.environ["SIMILAR_CRAW_PROJECT_ROOT"] = str(contents / "Resources")
    tools = contents / "Resources/capcut-backend/_internal"
    if tools.is_dir():
        os.environ["PATH"] = str(tools) + os.pathsep + os.environ.get("PATH", "")
    return root


def chromium_options(headless: bool) -> dict:
    root = configure_runtime()
    if root is None:
        return {"headless": headless}
    import playwright

    manifest = Path(playwright.__file__).parent / "driver/package/browsers.json"
    browsers = json.loads(manifest.read_text(encoding="utf-8"))["browsers"]
    name = "chromium-headless-shell" if headless else "chromium"
    revision = next(item["revision"] for item in browsers if item["name"] == name)
    arch = "x64" if platform.machine() == "x86_64" else "arm64"
    folder = root / f"{name.replace('-', '_')}-{revision}"
    if headless:
        executable = folder / f"chrome-headless-shell-mac-{arch}/chrome-headless-shell"
    else:
        executable = folder / f"chrome-mac-{arch}/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
        if not executable.is_file():
            # Older bundled Chromium releases used chrome-mac without an arch suffix.
            executable = folder / "chrome-mac/Chromium.app/Contents/MacOS/Chromium"
    if not executable.is_file():
        raise RuntimeError(f"应用内浏览器缺失：{executable}；请使用完整应用包。")
    return {"headless": headless, "executable_path": str(executable)}
