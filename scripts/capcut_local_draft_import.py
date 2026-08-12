#!/usr/bin/env python3
"""Create a local Jianying/CapCut draft with local video files via capcut-mate."""

from __future__ import annotations

import argparse
import contextlib
import fnmatch
import http.server
import json
import os
import re
import shutil
import socket
import socketserver
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_API_BASE = "http://localhost:30000/openapi/capcut-mate/v1"
DEFAULT_CAPCUT_MATE_ROOT = Path("/Users/zzh/C/capcut-mate-main/capcut-mate-main")
DEFAULT_JIANYING_DRAFT_DIR = Path(
    "/Users/zzh/Movies/JianyingPro/User Data/Projects/com.lveditor.draft"
)


class ReusableTcpServer(socketserver.TCPServer):
    allow_reuse_address = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="用 capcut-mate 创建本地剪映草稿，并导入一个或多个本地视频。"
    )
    parser.add_argument("videos", nargs="*", help="要导入剪映草稿的视频文件路径")
    parser.add_argument(
        "--from-dir",
        type=Path,
        help="从指定目录按子目录自然顺序收集视频，例如整理/728.1、整理/728.2",
    )
    parser.add_argument(
        "--video-extensions",
        default=".mp4,.mov,.m4v,.avi,.mkv",
        help="--from-dir 扫描的视频扩展名，逗号分隔",
    )
    parser.add_argument(
        "--one-per-folder",
        action="store_true",
        help="--from-dir 时每个子目录只取自然排序后的第一个视频",
    )
    parser.add_argument(
        "--exclude-glob",
        action="append",
        default=[],
        help="--from-dir 时排除匹配的文件名 glob，可重复传入，例如 '*_1080x1920_*'",
    )
    parser.add_argument("--width", type=int, default=720, help="草稿画布宽度，默认 720")
    parser.add_argument("--height", type=int, default=1280, help="草稿画布高度，默认 1280")
    parser.add_argument("--scale", type=float, default=1.0, help="视频缩放比例，1.03 表示 103%%")
    parser.add_argument("--speed", type=float, default=1.0, help="视频倍速，0.93 表示 0.93x")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="capcut-mate API 前缀")
    parser.add_argument(
        "--capcut-mate-root",
        type=Path,
        default=DEFAULT_CAPCUT_MATE_ROOT,
        help="capcut-mate 项目根目录",
    )
    parser.add_argument(
        "--jianying-draft-dir",
        type=Path,
        default=DEFAULT_JIANYING_DRAFT_DIR,
        help="macOS 剪映本地草稿目录",
    )
    parser.add_argument("--http-root", type=Path, help="本地 HTTP 服务根目录，默认自动取视频公共目录")
    parser.add_argument("--http-port", type=int, default=18080, help="本地 HTTP 服务端口，默认 18080")
    parser.add_argument("--host", default="127.0.0.1", help="本地 HTTP 服务 host，默认 127.0.0.1")
    parser.add_argument("--draft-name", help="复制到剪映草稿目录后的草稿文件夹名")
    parser.add_argument("--overwrite", action="store_true", help="如果目标草稿目录已存在，则覆盖")
    parser.add_argument("--keep-server", action="store_true", help="脚本结束后保持本地 HTTP 服务运行")
    parser.add_argument("--list-only", action="store_true", help="只打印扫描到的视频顺序，不创建草稿")
    return parser.parse_args()


def natural_key(value: str) -> list[Any]:
    """Sort names like 728.1, 728.2, 728.10 in human order."""
    parts = re.split(r"(\d+)", value)
    return [int(part) if part.isdigit() else part.lower() for part in parts]


def parse_extensions(value: str) -> set[str]:
    extensions = set()
    for item in value.split(","):
        item = item.strip().lower()
        if not item:
            continue
        extensions.add(item if item.startswith(".") else f".{item}")
    return extensions


def is_excluded(path: Path, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path.name.lower(), pattern.lower()) for pattern in patterns)


def collect_videos_from_dir(
    root: Path,
    extensions: set[str],
    one_per_folder: bool,
    exclude_globs: list[str],
) -> list[Path]:
    """Collect videos from immediate child folders in natural folder order."""
    if not root.is_dir():
        raise SystemExit(f"--from-dir 不是文件夹：{root}")

    video_paths: list[Path] = []

    root_files = [
        path for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in extensions
        and not is_excluded(path, exclude_globs)
    ]
    for path in sorted(root_files, key=lambda item: natural_key(item.name)):
        video_paths.append(path.resolve())

    child_dirs = [path for path in root.iterdir() if path.is_dir() and not path.name.startswith(".")]
    for child_dir in sorted(child_dirs, key=lambda item: natural_key(item.name)):
        child_videos = [
            path for path in child_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in extensions
            and not is_excluded(path, exclude_globs)
        ]
        sorted_child_videos = sorted(child_videos, key=lambda item: natural_key(str(item.relative_to(root))))
        if one_per_folder:
            sorted_child_videos = sorted_child_videos[:1]
        for path in sorted_child_videos:
            video_paths.append(path.resolve())

    if not video_paths:
        raise SystemExit(f"没有在目录中找到视频：{root}")
    return video_paths


def check_api(api_base: str) -> None:
    docs_url = api_base.rsplit("/openapi/capcut-mate/v1", 1)[0] + "/docs"
    try:
        with urllib.request.urlopen(docs_url, timeout=3) as response:
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}")
    except Exception as exc:
        raise SystemExit(
            "capcut-mate API 没有正常启动。请先执行：\n"
            "cd \"/Users/zzh/C/capcut-mate-main/capcut-mate-main\"\n"
            "source .venv/bin/activate\n"
            "python main.py\n\n"
            f"检测地址：{docs_url}\n原始错误：{exc}"
        ) from exc


def ffprobe_video(path: Path) -> dict[str, Any]:
    if not shutil.which("ffprobe"):
        raise SystemExit("找不到 ffprobe，请先安装完整版 ffmpeg。")

    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "format=duration:stream=width,height,duration,r_frame_rate,avg_frame_rate",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, check=True, text=True, capture_output=True)
    data = json.loads(result.stdout)
    stream = data.get("streams", [{}])[0]
    format_info = data.get("format", {})
    duration = float(format_info.get("duration") or stream.get("duration") or 0)
    if duration <= 0:
        raise SystemExit(f"无法读取视频时长：{path}")
    return {
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "duration_us": int(round(duration * 1_000_000)),
        "duration_seconds": duration,
        "r_frame_rate": stream.get("r_frame_rate", ""),
        "avg_frame_rate": stream.get("avg_frame_rate", ""),
    }


def find_free_port(preferred_port: int, host: str) -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        if sock.connect_ex((host, preferred_port)) != 0:
            return preferred_port

    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def start_http_server(root: Path, host: str, port: int) -> tuple[ReusableTcpServer, int]:
    actual_port = find_free_port(port, host)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(root), **kwargs)

        def log_message(self, format: str, *args: Any) -> None:
            print(f"[http] {format % args}")

    server = ReusableTcpServer((host, actual_port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, actual_port


def path_to_url(path: Path, root: Path, host: str, port: int) -> str:
    relative_path = path.relative_to(root)
    quoted = "/".join(urllib.parse.quote(part) for part in relative_path.parts)
    return f"http://{host}:{port}/{quoted}"


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"接口请求失败：{url}\nHTTP {exc.code}: {exc.read().decode('utf-8', errors='ignore')}") from exc
    except Exception as exc:
        raise SystemExit(f"接口请求失败：{url}\n{exc}") from exc

    if data.get("code") != 0:
        raise SystemExit(f"接口返回错误：{url}\n{json.dumps(data, ensure_ascii=False, indent=2)}")
    return data


def create_draft(api_base: str, width: int, height: int) -> str:
    response = post_json(f"{api_base}/create_draft", {"width": width, "height": height})
    return str(response["draft_url"])


def add_videos(api_base: str, draft_url: str, videos: list[dict[str, Any]], scale: float, speed: float) -> None:
    video_infos = []
    scene_timelines = []
    current_start = 0
    for video in videos:
        duration_us = int(video["duration_us"])
        current_end = current_start + duration_us
        video_infos.append(
            {
                "video_url": video["url"],
                "width": video["width"],
                "height": video["height"],
                "start": current_start,
                "end": current_end,
                "duration": duration_us,
            }
        )
        if speed != 1.0:
            scene_duration = int(round(duration_us / speed))
            scene_timelines.append({"start": current_start, "end": current_start + scene_duration})
            current_start += scene_duration
        else:
            current_start = current_end

    payload: dict[str, Any] = {
        "draft_url": draft_url,
        "video_infos": json.dumps(video_infos, ensure_ascii=False),
    }
    if scale != 1.0:
        payload["scale_x"] = scale
        payload["scale_y"] = scale
    if speed != 1.0:
        payload["scene_timelines"] = scene_timelines

    post_json(f"{api_base}/add_videos", payload)


def save_draft(api_base: str, draft_url: str) -> None:
    post_json(f"{api_base}/save_draft", {"draft_url": draft_url})


def extract_draft_id(draft_url: str) -> str:
    parsed = urllib.parse.urlparse(draft_url)
    query = urllib.parse.parse_qs(parsed.query)
    draft_id = query.get("draft_id", [""])[0]
    if not draft_id:
        raise SystemExit(f"无法从 draft_url 提取 draft_id：{draft_url}")
    return draft_id


def copy_to_jianying(
    source_dir: Path,
    target_base: Path,
    draft_name: str,
    old_root: Path,
    overwrite: bool,
) -> Path:
    target_dir = target_base / draft_name
    if target_dir.exists():
        if not overwrite:
            suffix = time.strftime("%Y%m%d_%H%M%S")
            target_dir = target_base / f"{draft_name}_{suffix}"
        else:
            shutil.rmtree(target_dir)

    shutil.copytree(source_dir, target_dir)
    replace_material_paths(target_dir, old_root, target_dir)
    clear_macos_attrs(target_dir)
    return target_dir


def replace_material_paths(target_dir: Path, old_root: Path, new_root: Path) -> None:
    for name in ["draft_content.json", "draft_info.json"]:
        path = target_dir / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        updated = text.replace(str(old_root), str(new_root))
        path.write_text(updated, encoding="utf-8")


def clear_macos_attrs(path: Path) -> None:
    subprocess.run(["xattr", "-cr", str(path)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for root, dirs, files in os.walk(path):
        for dirname in dirs:
            with contextlib.suppress(OSError):
                os.chmod(Path(root) / dirname, 0o755)
        for filename in files:
            with contextlib.suppress(OSError):
                os.chmod(Path(root) / filename, 0o644)


def main() -> int:
    args = parse_args()
    video_paths = [Path(video).expanduser().resolve() for video in args.videos]
    if args.from_dir:
        scan_root = args.from_dir.expanduser().resolve()
        scanned_videos = collect_videos_from_dir(
            scan_root,
            parse_extensions(args.video_extensions),
            args.one_per_folder,
            args.exclude_glob,
        )
        video_paths.extend(scanned_videos)

    if not video_paths:
        raise SystemExit("请传入视频文件路径，或使用 --from-dir 指定要扫描的视频目录。")

    for path in video_paths:
        if not path.is_file():
            raise SystemExit(f"视频文件不存在：{path}")

    if args.list_only:
        print("导入顺序：")
        for index, path in enumerate(video_paths, start=1):
            print(f"{index:03d}. {path}")
        return 0

    http_root = (
        args.http_root.expanduser().resolve()
        if args.http_root
        else Path(os.path.commonpath([str(path.parent) for path in video_paths])).resolve()
    )
    if not http_root.is_dir():
        raise SystemExit(f"HTTP 根目录不是文件夹：{http_root}")
    for path in video_paths:
        try:
            path.relative_to(http_root)
        except ValueError as exc:
            raise SystemExit(f"视频不在 HTTP 根目录下：{path}\nHTTP 根目录：{http_root}") from exc

    check_api(args.api_base)
    server, actual_port = start_http_server(http_root, args.host, args.http_port)

    try:
        videos = []
        print(f"HTTP 根目录：{http_root}")
        print(f"HTTP 服务：http://{args.host}:{actual_port}/")
        print("导入顺序：")
        for index, path in enumerate(video_paths, start=1):
            info = ffprobe_video(path)
            info["path"] = str(path)
            info["url"] = path_to_url(path, http_root, args.host, actual_port)
            videos.append(info)
            print(
                f"{index:03d}. {path} | {info['width']}x{info['height']} | "
                f"{info['duration_seconds']:.3f}s | {info['url']}"
            )

        draft_url = create_draft(args.api_base, args.width, args.height)
        draft_id = extract_draft_id(draft_url)
        print(f"草稿 URL：{draft_url}")
        print(f"草稿 ID：{draft_id}")

        add_videos(args.api_base, draft_url, videos, args.scale, args.speed)
        save_draft(args.api_base, draft_url)

        source_dir = args.capcut_mate_root / "output" / "draft" / draft_id
        if not source_dir.is_dir():
            raise SystemExit(f"capcut-mate 草稿目录不存在：{source_dir}")

        draft_name = args.draft_name or f"auto_import_{draft_id}"
        target_dir = copy_to_jianying(
            source_dir=source_dir,
            target_base=args.jianying_draft_dir,
            draft_name=draft_name,
            old_root=source_dir,
            overwrite=args.overwrite,
        )

        print("\n完成。")
        print(f"剪映草稿目录：{target_dir}")
        print("请完全退出并重新打开剪映，在本地草稿列表中查看。")
        if args.scale != 1.0 or args.speed != 1.0:
            print(f"处理参数：scale={args.scale}, speed={args.speed}")

        if args.keep_server:
            print("\n已启用 --keep-server，按 Ctrl+C 停止本地 HTTP 服务。")
            while True:
                time.sleep(3600)
    finally:
        if not args.keep_server:
            server.shutdown()
            server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
