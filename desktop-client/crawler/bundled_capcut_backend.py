"""Standalone CapCut Mate entry point; keep generated data outside the bundle."""

import argparse
import os
import sys
import threading
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--port", type=int, default=30001)
    parser.add_argument("--parent-pid", type=int)
    args = parser.parse_args()
    root = args.data_dir.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    os.chdir(root)
    tools = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    os.environ["PATH"] = str(tools) + os.pathsep + os.environ.get("PATH", "")
    import config

    config.PROJECT_ROOT = str(root)
    for name, relative in (
        ("DRAFT_DIR", "output/draft"),
        ("LOG_DIR", "logs"),
        ("TEMP_DIR", "temp"),
    ):
        folder = root / relative
        folder.mkdir(parents=True, exist_ok=True)
        setattr(config, name, str(folder))
    (root / "db").mkdir(exist_ok=True)
    config.VIDEO_GEN_TASK_DB_PATH = str(root / "db/video_gen_tasks.sqlite3")
    config.DRAFT_URL = f"http://127.0.0.1:{args.port}/openapi/capcut-mate/v1/get_draft"
    config.DOWNLOAD_URL = f"http://127.0.0.1:{args.port}/"
    config.ENABLE_APIKEY = False
    from main import app
    import uvicorn

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, log_config=None))

    if args.parent_pid:
        def watch_parent():
            while True:
                time.sleep(1)
                if os.getppid() != args.parent_pid:
                    server.should_exit = True
                    return

        threading.Thread(target=watch_parent, daemon=True).start()
    server.run()


if __name__ == "__main__":
    main()
