#!/usr/bin/env python3
"""Pinterest-style Meta 广告素材客户端。"""

from __future__ import annotations

import json
import os
import re
import runpy
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable
from bundled_runtime import configure_runtime, chromium_options

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

PROJECT_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
APP_RESOURCES = Path(sys.executable).resolve().parent.parent / "Resources" if getattr(sys, "frozen", False) else PROJECT_ROOT
PYTHON = sys.executable

EXTRACTOR = PROJECT_ROOT / "crawler" / "meta_ad_card_extractor.py"
BATCH_BY_IDS = PROJECT_ROOT / "crawler" / "meta_ad_card_batch_by_ids.py"
COPY_FOLDERS = PROJECT_ROOT / "crawler" / "create_and_copy_dated_folders.py"
EXPORT_IMAGE_MATERIALS = PROJECT_ROOT / "crawler" / "export_image_materials.py"
PAGE_UNTIL_ID = PROJECT_ROOT / "crawler" / "meta_ad_page_until_id.py"
CAPCUT_IMPORT = PROJECT_ROOT / "crawler" / "capcut_local_draft_import.py"
SUMMARY_VIDEO = PROJECT_ROOT / "summary_scripts" / "generate_summary.py"
SUMMARY_IMAGE = PROJECT_ROOT / "summary_scripts" / "generate_image_summary.py"

APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "SimilarCrawClient"
CONFIG_PATH = APP_SUPPORT_DIR / "config.json"
CAPCUT_DEFAULT_API = "http://127.0.0.1:30001/openapi/capcut-mate/v1"
CAPCUT_DATA_ROOT = APP_SUPPORT_DIR / "CapcutBackend"

PIN_RED = "#e60023"
PIN_RED_DARK = "#ad081b"
INK = "#211922"
MUTE = "#6e666f"
CANVAS = "#f7f5f2"
CARD = "#ffffff"
LINE = "#e9e4de"
SOFT_RED = "#fff0f2"
WARM = "#f1eee9"


def script_command(script: Path) -> list[str]:
    if getattr(sys, "frozen", False):
        try:
            script_arg = str(script.relative_to(PROJECT_ROOT))
        except ValueError:
            script_arg = str(script)
        return [sys.executable, "--worker-script", script_arg]
    return [PYTHON, str(script)]


def run_worker_script() -> None:
    if len(sys.argv) < 3 or sys.argv[1] != "--worker-script":
        return
    script = Path(sys.argv[2])
    if not script.is_absolute():
        script = PROJECT_ROOT / script
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    sys.path.insert(0, str(script.parent))
    configure_runtime()
    if not script.exists():
        raise SystemExit(f"worker 找不到脚本：{script}")
    sys.argv = [str(script), *sys.argv[3:]]
    runpy.run_path(str(script), run_name="__main__")
    raise SystemExit(0)


def parse_ids(text: str) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for candidate in re.split(r"[\s,，]+", text.strip()):
        if candidate and re.fullmatch(r"\d+", candidate) and candidate not in seen:
            seen.add(candidate)
            ids.append(candidate)
    return ids


def split_globs(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"[\n,，]+", text) if item.strip()]

def failed_ids_from_local_results(ids: list[str], output_root: Path, media_type: str) -> list[str]:
    """Recover old whole-batch retry lists without redownloading completed media."""
    failed = []
    for library_id in ids:
        try:
            records = json.loads((output_root / "素材爬取" / library_id / "广告素材.json").read_text(encoding="utf-8"))
            records = [record for record in records if str(record.get("资料库编号", "")) == library_id]
            if not records:
                raise ValueError("缺少编号记录")
            for record in records:
                kind = "广告视频" if record.get("广告视频") else "广告图片"
                if media_type == "video" and kind != "广告视频":
                    raise ValueError("缺少视频")
                file = Path(record.get(f"{kind}本地文件") or "")
                if not file.is_file() or not file.stat().st_size:
                    raise ValueError("本地素材未保存")
        except (OSError, ValueError, TypeError, AttributeError):
            failed.append(library_id)
    return failed


def quote_cmd(command: list[str]) -> str:
    return " ".join(shlex.quote(str(item)) for item in command)


def bundled_playwright_browsers() -> Path | None:
    candidates = [PROJECT_ROOT / "ms-playwright", APP_RESOURCES / "ms-playwright"]
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        candidates.extend([executable.parent / "ms-playwright", executable.parent.parent / "Frameworks" / "ms-playwright"])
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def with_media_type(url: str, media_type: str) -> str:
    if not url:
        return url
    parsed = urllib.parse.urlsplit(url)
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    query["media_type"] = media_type if media_type in {"photo", "video", "all"} else "all"
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query), parsed.fragment))


@dataclass
class ClientConfig:
    mode: str = "page"
    media_type: str = "video"
    page_url: str = "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&is_targeted_country=false&media_type=all&q=tryfortis&search_type=keyword_unordered&sort_data[mode]=relevancy_monthly_grouped&sort_data[direction]=desc"
    stop_library_id: str = ""
    ids_text: str = ""
    output_root: str = ""
    advertiser_filter: str = "all"
    selected_advertisers: list[str] = field(default_factory=list)
    headless: bool = True
    require_hd_video: bool = True
    download_images: bool = True
    scroll_rounds: int = 40
    stop_after_stable_rounds: int = 6
    wait_ms: int = 2500
    concurrency: int = 2
    max_cards: str = ""
    organize_prefix: str = ""
    capcut_draft_name: str = ""
    capcut_one_per_folder: bool = True
    capcut_width: int = 1080
    capcut_height: int = 1920
    capcut_scale: float = 1.03
    capcut_speed: float = 0.93
    capcut_exclude_globs: str = "*_1080x1920_*,*_match_capcut*"
    last_failed_ids: list[str] = field(default_factory=list)
    retry_context: dict[str, Any] = field(default_factory=dict)


class ConfigStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> ClientConfig:
        if not self.path.exists():
            return ClientConfig()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return ClientConfig()
        config = ClientConfig()
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
        return config

    def save(self, config: ClientConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")


class CommandRunner:
    def __init__(self, log_callback: Callable[[str], None], done_callback: Callable[[str, int, str], None]) -> None:
        self.log_callback = log_callback
        self.done_callback = done_callback
        self._running = False
        self._process: subprocess.Popen[str] | None = None

    @property
    def running(self) -> bool:
        return self._running

    def run(self, name: str, command: list[str], cwd: Path) -> None:
        if self._running:
            raise RuntimeError("当前已有任务在运行")
        self._running = True

        def worker() -> None:
            lines: list[str] = []
            code = 0
            try:
                self.log_callback(f"\n{name} · 开始")
                self.log_callback(f"$ {quote_cmd(command)}")
                env = {**os.environ, "PYTHONUNBUFFERED": "1"}
                backend_tools = APP_RESOURCES / "capcut-backend" / "_internal"
                if backend_tools.is_dir():
                    env["PATH"] = str(backend_tools) + os.pathsep + env.get("PATH", "")
                env["SIMILAR_CRAW_PYTHON"] = PYTHON
                if getattr(sys, "frozen", False):
                    env["SIMILAR_CRAW_WORKER_EXE"] = sys.executable
                    env["SIMILAR_CRAW_PROJECT_ROOT"] = str(PROJECT_ROOT)
                browsers = bundled_playwright_browsers()
                if browsers:
                    env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers)
                proc = subprocess.Popen(
                    command,
                    cwd=str(cwd),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                    env=env,
                )
                self._process = proc
                assert proc.stdout is not None
                for line in proc.stdout:
                    line = line.rstrip("\n")
                    lines.append(line)
                    self.log_callback(line)
                code = proc.wait()
                self.log_callback(f"{name} · 结束，退出码 {code}")
            except Exception as exc:
                code = 1
                lines.append(str(exc))
                self.log_callback(f"{name} · 失败：{exc}")
            finally:
                self._process = None
                self._running = False
                self.done_callback(name, code, "\n".join(lines))

        threading.Thread(target=worker, daemon=True).start()

    def stop(self) -> bool:
        proc = self._process
        if not self._running or proc is None or proc.poll() is not None:
            return False
        self.log_callback("正在停止当前任务...")
        try:
            proc.terminate()
            threading.Timer(5, self._kill_if_running, args=(proc,)).start()
        except Exception as exc:
            self.log_callback(f"停止失败：{exc}")
            return False
        return True

    def _kill_if_running(self, proc: subprocess.Popen[str]) -> None:
        if proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass


class CapcutBackendManager:
    def __init__(self, log_callback: Callable[[str], None], api_base: str = CAPCUT_DEFAULT_API) -> None:
        self.log_callback = log_callback
        self.api_base = api_base.rstrip("/")
        self.process: subprocess.Popen[str] | None = None
        self.lock = threading.Lock()
        self.operation_lock = threading.Lock()
        self.busy = False
        self.last_error = ""

    @property
    def state_file(self) -> Path:
        port = urllib.parse.urlsplit(self.api_base).port or 30001
        return CAPCUT_DATA_ROOT / f"process-{port}.json"

    def process_identity(self, pid: int) -> dict[str, Any] | None:
        result = subprocess.run(
            ["/bin/ps", "-ww", "-p", str(pid), "-o", "lstart=", "-o", "command="],
            capture_output=True, text=True,
        )
        parts = result.stdout.strip().split(None, 5)
        if result.returncode or len(parts) != 6:
            return None
        command = re.fullmatch(
            r"(.+) --data-dir (.+) --port (\d+)(?: --parent-pid \d+)?", parts[5]
        )
        if not command:
            return None
        port = str(urllib.parse.urlsplit(self.api_base).port or 30001)
        executable = Path(command.group(1))
        if not (
            executable.name == "capcut-backend"
            and (
                str(executable).endswith("/Contents/Resources/capcut-backend/capcut-backend")
                or executable.resolve() == self.bundled_executable().resolve()
            )
        ):
            return None
        data_dir = Path(command.group(2)).resolve()
        process_port = command.group(3)
        if data_dir != CAPCUT_DATA_ROOT.resolve() or process_port != port:
            return None
        return {"pid": pid, "started": " ".join(parts[:5]), "command": parts[5]}

    def remember_process(self, identity: dict[str, Any]) -> None:
        CAPCUT_DATA_ROOT.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(identity), encoding="utf-8")

    def managed_process(self) -> dict[str, Any] | None:
        try:
            saved = json.loads(self.state_file.read_text(encoding="utf-8"))
            current = self.process_identity(int(saved["pid"]))
            if current == saved:
                return current
        except (OSError, ValueError, KeyError, TypeError):
            pass
        # Recover older releases that did not persist their backend PID.
        port = urllib.parse.urlsplit(self.api_base).port or 30001
        result = subprocess.run(
            ["/usr/sbin/lsof", "-nP", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True, text=True,
        )
        for value in result.stdout.split():
            if value.isdigit():
                identity = self.process_identity(int(value))
                if identity:
                    self.remember_process(identity)
                    return identity
        return None

    def is_running(self) -> bool:
        openapi_url = self.api_base.rsplit("/openapi/capcut-mate/v1", 1)[0] + "/openapi.json"
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(openapi_url, timeout=2) as response:
                data = json.load(response)
            paths = data.get("paths", {})
            draft_route = paths.get("/openapi/capcut-mate/v1/create_draft", {})
            return data.get("info", {}).get("title") == "CapCut Mate API" and "post" in draft_route
        except Exception:
            return False

    def bundled_executable(self) -> Path:
        for root in (PROJECT_ROOT, APP_RESOURCES):
            executable = root / "capcut-backend" / "capcut-backend"
            if executable.is_file():
                return executable
        if not getattr(sys, "frozen", False):
            return Path(__file__).resolve().parents[1] / "backend-dist/capcut-backend/capcut-backend"
        raise RuntimeError("应用包缺少 capcut-backend，请使用完整新版应用")

    def start(self) -> None:
        if not self.operation_lock.acquire(blocking=False):
            raise RuntimeError("后端正在启动或停止，请稍候")
        self.busy = True
        self.last_error = ""
        try:
            self._start()
        except Exception as error:
            self.last_error = str(error)
            self.log_callback(f"后端启动失败：{error}")
            raise
        finally:
            self.busy = False
            self.operation_lock.release()

    def _start(self) -> None:
        if self.is_running():
            self.log_callback("CapCut Mate 后端已通过 API 检测")
            return
        with self.lock:
            if self.process and self.process.poll() is None:
                raise RuntimeError("CapCut Mate 后端仍在启动，请稍后刷新状态")
        executable = self.bundled_executable()
        if not executable.is_file():
            raise RuntimeError("应用中缺少内置 CapCut Mate 后端，请重新打包应用")
        CAPCUT_DATA_ROOT.mkdir(parents=True, exist_ok=True)
        port = urllib.parse.urlsplit(self.api_base).port or 30001
        command = [
            str(executable), "--data-dir", str(CAPCUT_DATA_ROOT),
            "--port", str(port), "--parent-pid", str(os.getpid()),
        ]
        self.log_callback(f"启动 CapCut Mate：{quote_cmd(command)}")
        env = dict(os.environ)
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        env["PATH"] = str(executable.parent / "_internal") + os.pathsep + env.get("PATH", "")
        with (CAPCUT_DATA_ROOT / "backend.log").open("a", encoding="utf-8") as log_file:
            process = subprocess.Popen(
                command, cwd=str(CAPCUT_DATA_ROOT), env=env,
                stdout=log_file, stderr=subprocess.STDOUT, start_new_session=True,
            )
        with self.lock:
            self.process = process
        identity = self.process_identity(process.pid)
        if identity:
            self.remember_process(identity)
        for _ in range(45):
            if process.poll() is not None:
                raise RuntimeError(
                    f"后端进程退出（{process.returncode}），日志：{CAPCUT_DATA_ROOT / 'backend.log'}"
                )
            if self.is_running():
                self.log_callback("CapCut Mate 后端启动完成，API 检测通过")
                return
            time.sleep(1)
        process.terminate()
        process.wait(timeout=10)
        raise RuntimeError(f"后端启动超时，日志：{CAPCUT_DATA_ROOT / 'backend.log'}")

    def ensure_running(self) -> None:
        if self.is_running():
            self.log_callback("CapCut Mate 后端已通过 API 检测")
            return
        self.start()

    def stop(self) -> bool:
        if not self.operation_lock.acquire(blocking=False):
            raise RuntimeError("后端正在启动或停止，请稍候")
        self.busy = True
        try:
            return self._stop()
        finally:
            self.busy = False
            self.operation_lock.release()

    def _stop(self) -> bool:
        identity = self.managed_process()
        if not identity:
            if self.is_running():
                raise RuntimeError("该端口上的服务不是此应用的内置后端，未执行关闭")
            return False
        pid = identity["pid"]
        if self.process_identity(pid) != identity:
            return False
        os.kill(pid, signal.SIGTERM)
        for _ in range(100):
            if self.process and self.process.pid == pid:
                self.process.poll()
            if self.process_identity(pid) != identity:
                break
            time.sleep(0.1)
        else:
            if self.process_identity(pid) == identity:
                os.kill(pid, signal.SIGKILL)
            for _ in range(30):
                if self.process and self.process.pid == pid:
                    self.process.poll()
                if self.process_identity(pid) != identity:
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("后端进程未能退出，请查看后端日志")
        self.process = None
        try:
            if json.loads(self.state_file.read_text(encoding="utf-8")) == identity:
                self.state_file.unlink()
        except (OSError, ValueError):
            pass
        self.log_callback("内置 CapCut Mate 后端已关闭")
        return True

    def status(self) -> str:
        if self.busy:
            return "后端正在启动或停止…"
        if self.is_running():
            return "运行中 · API 检测通过"
        if self.last_error:
            return f"启动失败：{self.last_error}"
        return "后端未启动" if self.bundled_executable().is_file() else "应用缺少内置后端"

class MotionBar(tk.Canvas):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, height=7, bg=CANVAS, highlightthickness=0)
        self.running = False
        self.offset = 0

    def start(self) -> None:
        self.running = True
        self._tick()

    def stop(self) -> None:
        self.running = False
        self.delete("all")
        self.create_rectangle(0, 2, max(self.winfo_width(), 1), 5, fill=LINE, outline="")

    def _tick(self) -> None:
        if not self.running:
            return
        width = max(self.winfo_width(), 1)
        self.delete("all")
        self.create_rectangle(0, 2, width, 5, fill=LINE, outline="")
        x = (self.offset % (width + 180)) - 180
        self.create_rectangle(x, 0, x + 180, 7, fill=PIN_RED, outline="")
        self.offset += 12
        self.after(35, self._tick)


class StatusDot(tk.Canvas):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, width=18, height=18, bg=CANVAS, highlightthickness=0)
        self.running = False
        self.step = 0
        self.draw("#bdb4b6")

    def draw(self, color: str) -> None:
        self.delete("all")
        self.create_oval(4, 4, 14, 14, fill=color, outline="")

    def start(self) -> None:
        self.running = True
        self._tick()

    def stop(self) -> None:
        self.running = False
        self.draw("#bdb4b6")

    def _tick(self) -> None:
        if not self.running:
            return
        colors = [PIN_RED, "#ff6b80", PIN_RED_DARK, "#ff6b80"]
        self.draw(colors[self.step % len(colors)])
        self.step += 1
        self.after(220, self._tick)


class RoundedButton(tk.Canvas):
    def __init__(self, master: tk.Misc, text: str, command: Callable[[], None], *, primary: bool = False, width: int = 160, bg: str | None = None) -> None:
        parent_bg = bg or str(master.cget("bg") if hasattr(master, "cget") else CANVAS)
        super().__init__(master, width=width, height=42, bg=parent_bg, highlightthickness=0, cursor="pointinghand")
        self.text = text
        self.command = command
        self.primary = primary
        self.width_value = width
        self.hover = False
        self.bind("<Button-1>", lambda _event: self.command())
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.draw()

    def _enter(self, _event: tk.Event) -> None:
        self.hover = True
        self.draw()

    def _leave(self, _event: tk.Event) -> None:
        self.hover = False
        self.draw()

    def draw(self) -> None:
        self.delete("all")
        fill = PIN_RED if self.primary else WARM
        if self.hover:
            fill = PIN_RED_DARK if self.primary else "#e8e2db"
        fg = "white" if self.primary else INK
        self.create_round_rect(1, 1, self.width_value - 1, 41, radius=16, fill=fill, outline="")
        self.create_text(self.width_value / 2, 21, text=self.text, fill=fg, font=("PingFang SC", 12, "bold"))

    def create_round_rect(self, x1: int, y1: int, x2: int, y2: int, radius: int, **kwargs: Any) -> int:
        points = [
            x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
            x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
            x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
        ]
        return self.create_polygon(points, smooth=True, **kwargs)


class AdvertiserCard(tk.Frame):
    def __init__(self, master: tk.Misc, advertiser: dict[str, str], selected: bool, toggle: Callable[[str], None]) -> None:
        super().__init__(master, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        self.advertiser = advertiser
        self.name = advertiser.get("投放者", "未知投放者")
        self.toggle = toggle
        self.selected_var = tk.BooleanVar(value=selected)
        self.configure(cursor="pointinghand")
        self.bind("<Button-1>", self._clicked)
        self.bind("<Enter>", lambda _e: self.configure(highlightbackground=PIN_RED))
        self.bind("<Leave>", lambda _e: self.configure(highlightbackground=PIN_RED if self.selected_var.get() else LINE))
        self._build()

    def reveal(self, delay: int = 0) -> None:
        def flash(step: int = 0) -> None:
            colors = ["#fff0f2", "#fff6f7", CARD]
            self.configure(bg=colors[min(step, len(colors) - 1)], highlightbackground=PIN_RED if step == 0 else LINE)
            for child in self.winfo_children():
                try:
                    child.configure(bg=colors[min(step, len(colors) - 1)])
                except Exception:
                    pass
            if step < len(colors) - 1:
                self.after(80, lambda: flash(step + 1))
            else:
                self.configure(highlightbackground=PIN_RED if self.selected_var.get() else LINE)

        self.after(delay, flash)

    def _build(self) -> None:
        badge = tk.Canvas(self, width=58, height=58, bg=CARD, highlightthickness=0)
        badge.pack(anchor="w", padx=14, pady=(14, 8))
        color = PIN_RED if self.selected_var.get() else SOFT_RED
        badge.create_oval(3, 3, 55, 55, fill=color, outline="")
        initials = "".join(part[:1] for part in self.name.split()[:2]).upper()[:2] or "AD"
        badge.create_text(29, 29, text=initials, fill="white" if self.selected_var.get() else PIN_RED, font=("PingFang SC", 15, "bold"))
        tk.Label(self, text=self.name, bg=CARD, fg=INK, font=("PingFang SC", 13, "bold"), wraplength=210, justify="left").pack(anchor="w", padx=14)
        tk.Label(self, text=f"首次编号：{self.advertiser.get('首次资料库编号', '')}", bg=CARD, fg=MUTE, font=("PingFang SC", 10), wraplength=210, justify="left").pack(anchor="w", padx=14, pady=(6, 10))
        check = tk.Checkbutton(self, text="选中", variable=self.selected_var, command=lambda: self.toggle(self.name), bg=CARD, fg=INK, activebackground=CARD, selectcolor=CARD)
        check.pack(anchor="w", padx=10, pady=(0, 12))

    def _clicked(self, _event: tk.Event) -> None:
        self.toggle(self.name)

    def refresh_selected(self, selected: bool) -> None:
        self.selected_var.set(selected)
        self.configure(highlightbackground=PIN_RED if selected else LINE)
        for child in self.winfo_children():
            child.destroy()
        self._build()



class MetaMaterialClient(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Meta Pinboard")
        self.geometry("1280x820")
        self.minsize(1040, 700)
        self.configure(bg=CANVAS)
        self.store = ConfigStore(CONFIG_PATH)
        self.config_data = self.store.load()
        self.runner = CommandRunner(self.log, self.on_task_done)
        self.backend = CapcutBackendManager(self.log)
        self.closing = False
        self.advertisers: list[dict[str, str]] = []
        self.selected_advertisers = set(self.config_data.selected_advertisers)
        self.workflow_steps: list[str] = []
        self.workflow_index = 0
        self.workflow_ids: list[str] = []
        self.current_page = "home"
        self.page_transition_job: str | None = None
        self.nav_pulse_job: str | None = None
        self.status_var = tk.StringVar(value="Ready · 选择左侧菜单开始")
        self._build_vars()
        self._build_style()
        self._build_ui()
        self.show_page("home")
        self.render_advertisers()
        self.after(300, self.bring_to_front)
        self.protocol("WM_DELETE_WINDOW", self.close_client)
        self.createcommand("tk::mac::Quit", self.close_client)
        signal.signal(signal.SIGTERM, lambda *_: self.after(0, self.close_client))

    def close_client(self) -> None:
        if self.closing:
            return
        self.closing = True
        self.status_var.set("正在关闭内置后端…")
        self.workflow_steps = []
        self.runner.stop()

        def worker() -> None:
            try:
                # Wait for an in-progress start before shutting the backend down.
                with self.backend.operation_lock:
                    if self.backend.managed_process():
                        self.backend._stop()
            except Exception as error:
                self.after(0, lambda message=str(error): self.close_failed(message))
                return
            self.after(0, self.destroy)

        threading.Thread(target=worker, daemon=True).start()

    def close_failed(self, error: str) -> None:
        self.closing = False
        self.status_var.set(f"关闭后端失败：{error}")
        messagebox.showerror("无法退出", f"内置后端尚未关闭：{error}")

    def bring_to_front(self) -> None:
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
            self.attributes("-topmost", True)
            self.after(900, lambda: self.attributes("-topmost", False))
        except Exception:
            pass

    def _build_vars(self) -> None:
        c = self.config_data
        self.var_mode = tk.StringVar(value=c.mode)
        self.var_media_type = tk.StringVar(value=c.media_type)
        self.var_page_url = tk.StringVar(value=c.page_url)
        self.var_stop_library_id = tk.StringVar(value=c.stop_library_id)
        self.var_output_root = tk.StringVar(value=c.output_root)
        self.var_filter = tk.StringVar(value=c.advertiser_filter)
        self.var_headless = tk.BooleanVar(value=c.headless)
        self.var_require_hd = tk.BooleanVar(value=c.require_hd_video)
        self.var_download = tk.BooleanVar(value=c.download_images)
        self.var_scroll_rounds = tk.StringVar(value=str(c.scroll_rounds))
        self.var_stable_rounds = tk.StringVar(value=str(c.stop_after_stable_rounds))
        self.var_wait_ms = tk.StringVar(value=str(c.wait_ms))
        self.var_concurrency = tk.StringVar(value=str(c.concurrency))
        self.var_max_cards = tk.StringVar(value=c.max_cards)
        self.var_organize_prefix = tk.StringVar(value=c.organize_prefix)
        self.var_capcut_draft_name = tk.StringVar(value=c.capcut_draft_name)
        self.var_capcut_width = tk.StringVar(value=str(c.capcut_width))
        self.var_capcut_height = tk.StringVar(value=str(c.capcut_height))
        self.var_capcut_scale = tk.StringVar(value=str(c.capcut_scale))
        self.var_capcut_speed = tk.StringVar(value=str(c.capcut_speed))

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TEntry", padding=7)
        style.configure("TScrollbar", gripcount=0, background=WARM, troughcolor=CANVAS, bordercolor=CANVAS, arrowcolor=MUTE)

    def _build_ui(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.sidebar = tk.Frame(self, width=238, bg=INK)
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.sidebar.grid_propagate(False)
        self.main = tk.Frame(self, bg=CANVAS)
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.columnconfigure(0, weight=1)
        self.main.rowconfigure(1, weight=1)
        self._build_sidebar()
        self._build_header()
        self.page_host = tk.Frame(self.main, bg=CANVAS)
        self.page_host.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 12))
        self.page_host.columnconfigure(0, weight=1)
        self.page_host.rowconfigure(0, weight=1)
        self.pages: dict[str, tk.Frame] = {}
        self._build_home_page()
        self._build_page_crawl_page()
        self._build_ids_page()
        self._build_advertiser_page()
        self._build_backend_page()
        self._build_log_page()
        self.motion = MotionBar(self.main)
        self.motion.grid(row=2, column=0, sticky="ew")
        self.motion.stop()

    def _build_header(self) -> None:
        header = tk.Frame(self.main, bg=CANVAS)
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 12))
        header.columnconfigure(0, weight=1)
        tk.Label(header, text="Meta Pinboard", bg=CANVAS, fg=INK, font=("PingFang SC", 24, "bold")).grid(row=0, column=0, sticky="w")
        status_line = tk.Frame(header, bg=CANVAS)
        status_line.grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.status_dot = StatusDot(status_line)
        self.status_dot.pack(side="left", padx=(0, 6))
        tk.Label(status_line, textvariable=self.status_var, bg=CANVAS, fg=MUTE, font=("PingFang SC", 12)).pack(side="left")
        self.stop_button = RoundedButton(header, "停止当前任务", self.stop_current_task, primary=True, width=140)
        self.stop_button.grid(row=0, column=1, rowspan=2, sticky="e")

    def _build_sidebar(self) -> None:
        tk.Label(self.sidebar, text="Meta\nPinboard", bg=INK, fg="white", font=("PingFang SC", 25, "bold"), justify="left").pack(anchor="w", padx=22, pady=(26, 6))
        tk.Frame(self.sidebar, bg=INK, height=18).pack(fill="x")
        self.nav_buttons: dict[str, tk.Label] = {}
        for key, title, icon in [
            ("home", "总控台", "●"),
            ("page", "页面抓取", "◐"),
            ("ids", "编号全流程", "◆"),
            ("advertisers", "投放者看板", "◈"),
            ("backend", "CapCut Mate 后端", "⚙"),
            ("logs", "实时日志", "▣"),
        ]:
            item = tk.Label(self.sidebar, text=f"{icon}  {title}", bg=INK, fg="white", font=("PingFang SC", 13, "bold"), anchor="w", padx=18, pady=11, cursor="pointinghand")
            item.pack(fill="x", padx=12, pady=3)
            item.bind("<Button-1>", lambda _e, page=key: self.show_page(page))
            item.bind("<Enter>", lambda _e, page=key: self.nav_hover(page, True))
            item.bind("<Leave>", lambda _e, page=key: self.nav_hover(page, False))
            self.nav_buttons[key] = item
        tk.Frame(self.sidebar, bg="#3a3034", height=1).pack(fill="x", padx=18, pady=18)
        tk.Label(self.sidebar, text="快速操作", bg=INK, fg="#cfc7c8", font=("PingFang SC", 10, "bold")).pack(anchor="w", padx=22)
        for text, command, primary in [
            ("扫描投放者", self.start_scan, False),
            ("页面抓取", self.start_page_crawl, True),
            ("资料库全流程", self.start_ids_workflow, True),
            ("打开输出目录", self.open_output, False),
        ]:
            btn = RoundedButton(self.sidebar, text, command, primary=primary, width=190)
            btn.pack(padx=22, pady=6)

    def create_page(self, key: str) -> tk.Frame:
        page = tk.Frame(self.page_host, bg=CANVAS)
        page.grid(row=0, column=0, sticky="nsew")
        page.columnconfigure(0, weight=1)
        page.rowconfigure(0, weight=1)
        self.pages[key] = page
        return page

    def show_page(self, key: str) -> None:
        if key not in self.pages:
            return
        self.current_page = key
        self.pages[key].tkraise()
        self.animate_page_in(self.pages[key])
        for name, button in getattr(self, "nav_buttons", {}).items():
            active = name == key
            button.configure(bg=PIN_RED if active else INK, fg="white")
        titles = {"home": "总控台", "page": "页面抓取", "ids": "编号全流程", "advertisers": "投放者看板", "backend": "CapCut Mate 后端", "logs": "实时日志"}
        self.status_var.set(f"{titles.get(key, '')} · 页面已切换")
        self.pulse_active_nav()

    def animate_page_in(self, page: tk.Frame, step: int = 0) -> None:
        if self.page_transition_job:
            try:
                self.after_cancel(self.page_transition_job)
            except Exception:
                pass
        colors = ["#fff7f7", "#fffafa", "#fbf8f5", CANVAS]
        page.configure(bg=colors[min(step, len(colors) - 1)])
        for child in page.winfo_children():
            try:
                child.configure(bg=CARD if step >= len(colors) - 1 else "#fffafa")
            except Exception:
                pass
        if step < len(colors) - 1:
            self.page_transition_job = self.after(45, lambda: self.animate_page_in(page, step + 1))
        else:
            self.page_transition_job = None

    def nav_hover(self, key: str, entering: bool) -> None:
        if key == self.current_page:
            return
        button = self.nav_buttons.get(key)
        if not button:
            return
        button.configure(bg="#3a3034" if entering else INK, fg="white" if entering else "#f8f1f2")

    def pulse_active_nav(self, step: int = 0) -> None:
        if self.nav_pulse_job:
            try:
                self.after_cancel(self.nav_pulse_job)
            except Exception:
                pass
        button = self.nav_buttons.get(self.current_page)
        if not button:
            return
        colors = [PIN_RED_DARK, PIN_RED, "#ff3856", PIN_RED]
        button.configure(bg=colors[min(step, len(colors) - 1)])
        if step < len(colors) - 1:
            self.nav_pulse_job = self.after(70, lambda: self.pulse_active_nav(step + 1))
        else:
            self.nav_pulse_job = None

    def panel(self, parent: tk.Misc, title: str | None = None) -> tk.Frame:
        frame = tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        if title:
            head = tk.Frame(frame, bg=CARD)
            head.pack(fill="x", padx=16, pady=(14, 6))
            tk.Label(head, text=title, bg=CARD, fg=INK, font=("PingFang SC", 15, "bold")).pack(side="left")
        return frame

    def input_row(self, parent: tk.Misc, label: str, variable: tk.StringVar, *, width: int = 22) -> ttk.Entry:
        tk.Label(parent, text=label, bg=CARD, fg=MUTE, font=("PingFang SC", 10, "bold")).pack(anchor="w", padx=16, pady=(8, 2))
        entry = ttk.Entry(parent, textvariable=variable, width=width)
        entry.pack(fill="x", padx=16)
        return entry

    def small_entry(self, parent: tk.Misc, label: str, variable: tk.StringVar) -> None:
        box = tk.Frame(parent, bg=CARD)
        box.pack(side="left", fill="x", expand=True, padx=(0, 8))
        tk.Label(box, text=label, bg=CARD, fg=MUTE, font=("PingFang SC", 9)).pack(anchor="w")
        ttk.Entry(box, textvariable=variable, width=8).pack(fill="x")

    def _build_home_page(self) -> None:
        page = self.create_page("home")
        page.columnconfigure(0, weight=1)
        page.columnconfigure(1, weight=1)
        left = self.panel(page, "全局设置")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.input_row(left, "输出根目录（只选一次）", self.var_output_root)
        row = tk.Frame(left, bg=CARD)
        row.pack(fill="x", padx=16, pady=12)
        RoundedButton(row, "选择目录", self.choose_output, width=120).pack(side="left")
        RoundedButton(row, "打开目录", self.open_output, width=120).pack(side="left", padx=8)
        RoundedButton(row, "保存配置", self.save_config, width=120).pack(side="left")
        media = tk.Frame(left, bg=CARD)
        media.pack(fill="x", padx=16, pady=(4, 12))
        for text, value in [("抓视频 · HD", "video"), ("抓图片", "photo"), ("图片+视频", "all")]:
            tk.Radiobutton(media, text=text, value=value, variable=self.var_media_type, bg=CARD, fg=INK, activebackground=CARD, selectcolor=SOFT_RED, font=("PingFang SC", 12, "bold")).pack(anchor="w", pady=3)
        tk.Checkbutton(left, text="下载素材", variable=self.var_download, bg=CARD, fg=INK, activebackground=CARD, selectcolor=CARD).pack(anchor="w", padx=14)
        tk.Checkbutton(left, text="视频强制 HD", variable=self.var_require_hd, bg=CARD, fg=INK, activebackground=CARD, selectcolor=CARD).pack(anchor="w", padx=14)
        tk.Checkbutton(left, text="后台无头浏览器", variable=self.var_headless, bg=CARD, fg=INK, activebackground=CARD, selectcolor=CARD).pack(anchor="w", padx=14, pady=(0, 14))

        right = self.panel(page, "常用参数")
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        row2 = tk.Frame(right, bg=CARD)
        row2.pack(fill="x", padx=16, pady=12)
        self.small_entry(row2, "滚动轮数", self.var_scroll_rounds)
        self.small_entry(row2, "稳定轮数", self.var_stable_rounds)
        row3 = tk.Frame(right, bg=CARD)
        row3.pack(fill="x", padx=16, pady=8)
        self.small_entry(row3, "滚动等待(ms)", self.var_wait_ms)
        self.small_entry(row3, "最多卡片", self.var_max_cards)
        concurrency_row = tk.Frame(right, bg=CARD)
        concurrency_row.pack(fill="x", padx=16, pady=8)
        tk.Label(concurrency_row, text="编号并发数", bg=CARD, fg=MUTE, font=("PingFang SC", 10)).pack(side="left")
        ttk.Spinbox(
            concurrency_row, from_=1, to=5, width=5, state="readonly",
            textvariable=self.var_concurrency,
        ).pack(side="left", padx=12)
        self.input_row(right, "整理前缀，例如 827", self.var_organize_prefix)
        self.input_row(right, "剪映草稿名", self.var_capcut_draft_name)
        tk.Label(right, text="建议：先到「页面抓取」扫描投放者，再到「投放者看板」选择过滤方式。", bg=CARD, fg=MUTE, font=("PingFang SC", 11), wraplength=420, justify="left").pack(anchor="w", padx=16, pady=16)

    def _build_page_crawl_page(self) -> None:
        page = self.create_page("page")
        page.rowconfigure(1, weight=1)
        self.page_panel = self.panel(page, "页面抓取")
        self.page_panel.grid(row=0, column=0, sticky="ew")
        self.input_row(self.page_panel, "Meta 广告资料库 URL", self.var_page_url)
        self.input_row(self.page_panel, "抓到该资料库编号后停止", self.var_stop_library_id)
        row = tk.Frame(self.page_panel, bg=CARD)
        row.pack(fill="x", padx=16, pady=14)
        RoundedButton(row, "扫描投放者", self.start_scan, width=140).pack(side="left")
        RoundedButton(row, "开始页面抓取", self.start_page_crawl, primary=True, width=150).pack(side="left", padx=8)
        RoundedButton(row, "查看日志", lambda: self.show_page("logs"), width=110).pack(side="left")
        self._build_advertiser_board(page)

    def _build_ids_page(self) -> None:
        page = self.create_page("ids")
        page.columnconfigure(0, weight=1)
        page.rowconfigure(0, weight=1)
        self.ids_panel = self.panel(page, "资料库编号抓取 · 全流程")
        self.ids_panel.grid(row=0, column=0, sticky="nsew")
        tk.Label(self.ids_panel, text="一行一个资料库编号，或空格/逗号分隔。执行后自动：抓取 → 整理 → Markdown → 剪映。", bg=CARD, fg=MUTE, font=("PingFang SC", 11)).pack(anchor="w", padx=16, pady=(0, 8))
        self.ids_text = tk.Text(self.ids_panel, height=15, bg="#fbfaf8", fg=INK, insertbackground=INK, relief="flat", font=("Menlo", 13), wrap="word")
        self.ids_text.insert("1.0", self.config_data.ids_text)
        self.ids_text.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        row = tk.Frame(self.ids_panel, bg=CARD)
        row.pack(fill="x", padx=16, pady=(0, 12))
        self.small_entry(row, "宽", self.var_capcut_width)
        self.small_entry(row, "高", self.var_capcut_height)
        self.small_entry(row, "缩放", self.var_capcut_scale)
        self.small_entry(row, "倍速", self.var_capcut_speed)
        actions = tk.Frame(self.ids_panel, bg=CARD)
        actions.pack(fill="x", padx=16, pady=(0, 16))
        RoundedButton(actions, "开始全流程", self.start_ids_workflow, primary=True, width=150).pack(side="left")
        RoundedButton(actions, "重试失败编号", self.retry_failed, width=140).pack(side="left", padx=8)
        RoundedButton(actions, "停止", self.stop_current_task, width=100).pack(side="left")

    def _build_advertiser_page(self) -> None:
        page = self.create_page("advertisers")
        self._build_advertiser_board(page)

    def _build_backend_page(self) -> None:
        page = self.create_page("backend")
        panel = self.panel(page, "CapCut Mate 后端")
        panel.grid(row=0, column=0, sticky="new")
        tk.Label(panel, text="服务状态", bg=CARD, fg=MUTE, font=("PingFang SC", 10, "bold")).pack(
            anchor="w", padx=16, pady=(12, 3)
        )
        self.backend_status_var = tk.StringVar(value="检测中…")
        tk.Label(panel, textvariable=self.backend_status_var, bg=CARD, fg=INK, font=("PingFang SC", 16, "bold")).pack(
            anchor="w", padx=16, pady=(0, 12)
        )
        tk.Label(
            panel,
            text=f"API：{CAPCUT_DEFAULT_API}\n内置后端 · 数据目录：{CAPCUT_DATA_ROOT}",
            bg=CARD,
            fg=MUTE,
            font=("PingFang SC", 10),
            justify="left",
            wraplength=820,
        ).pack(anchor="w", padx=16, pady=(0, 12))
        actions = tk.Frame(panel, bg=CARD)
        actions.pack(anchor="w", padx=16, pady=(0, 16))
        RoundedButton(actions, "启动后端", self.start_backend_manually, primary=True, width=130).pack(side="left")
        RoundedButton(actions, "刷新检测", self.refresh_backend_status, width=120).pack(side="left", padx=8)
        RoundedButton(actions, "关闭后端", self.stop_backend_manually, width=130).pack(side="left")
        RoundedButton(actions, "查看后端日志", self.open_backend_log, width=140).pack(side="left", padx=8)
        self.after(100, self._poll_backend_status)

    def _poll_backend_status(self) -> None:
        if self.closing or not hasattr(self, "backend_status_var"):
            return

        def worker() -> None:
            try:
                status = self.backend.status()
            except Exception as error:
                status = str(error)
            self.after(0, lambda: self.backend_status_var.set(status))

        threading.Thread(target=worker, daemon=True).start()
        self.after(5000, self._poll_backend_status)

    def refresh_backend_status(self) -> None:
        self.backend_status_var.set("检测中…")

        def worker() -> None:
            try:
                status = self.backend.status()
            except Exception as error:
                status = str(error)
            self.after(0, lambda: self.backend_status_var.set(status))

        threading.Thread(target=worker, daemon=True).start()

    def open_backend_log(self) -> None:
        CAPCUT_DATA_ROOT.mkdir(parents=True, exist_ok=True)
        log_file = CAPCUT_DATA_ROOT / "backend.log"
        log_file.touch(exist_ok=True)
        subprocess.Popen(["open", "-t", str(log_file)])

    def start_backend_manually(self) -> None:
        self.backend_status_var.set("正在启动…")

        def worker() -> None:
            try:
                self.backend.start()
                status = "运行中 · API 检测通过"
            except Exception as error:
                status = f"启动失败 · {error}"
            self.after(0, lambda: self.backend_status_var.set(status))

        threading.Thread(target=worker, daemon=True).start()

    def stop_backend_manually(self) -> None:
        self.backend_status_var.set("正在停止…")

        def worker() -> None:
            try:
                stopped = self.backend.stop()
                status = "后端已关闭" if stopped else "后端未启动"
            except Exception as error:
                status = f"停止失败 · {error}"
            self.after(0, lambda: self.backend_status_var.set(status))

        threading.Thread(target=worker, daemon=True).start()

    def _build_advertiser_board(self, parent: tk.Misc) -> None:
        board_panel = self.panel(parent)
        board_panel.grid(row=1 if parent == self.pages.get("page") else 0, column=0, sticky="nsew", pady=(12, 0))
        board_panel.rowconfigure(1, weight=1)
        board_panel.columnconfigure(0, weight=1)
        filters = tk.Frame(board_panel, bg=CARD)
        filters.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 8))
        tk.Label(filters, text="投放者看板", bg=CARD, fg=INK, font=("PingFang SC", 15, "bold")).pack(side="left", padx=(0, 18))
        for text, value in [("全部抓取", "all"), ("只抓选中", "include"), ("排除选中", "exclude")]:
            tk.Radiobutton(filters, text=text, value=value, variable=self.var_filter, bg=CARD, fg=INK, activebackground=CARD, selectcolor=SOFT_RED, font=("PingFang SC", 11, "bold")).pack(side="left", padx=(0, 16))
        RoundedButton(filters, "清空", self.clear_advertisers, width=78).pack(side="right")
        RoundedButton(filters, "全选", self.select_all_advertisers, width=78).pack(side="right", padx=(0, 8))
        canvas = tk.Canvas(board_panel, bg=CARD, highlightthickness=0)
        scrollbar = ttk.Scrollbar(board_panel, orient="vertical", command=canvas.yview)
        frame = tk.Frame(canvas, bg=CARD)
        window = canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=1, column=0, sticky="nsew", padx=(16, 0), pady=(0, 14))
        scrollbar.grid(row=1, column=1, sticky="ns", pady=(0, 14))
        frame.bind("<Configure>", lambda _e, c=canvas: c.configure(scrollregion=c.bbox("all")))
        canvas.bind("<Configure>", lambda e, c=canvas, w=window: c.itemconfigure(w, width=e.width))
        self.ad_canvas = canvas
        self.ad_frame = frame

    def _build_log_page(self) -> None:
        page = self.create_page("logs")
        page.columnconfigure(0, weight=1)
        page.rowconfigure(0, weight=1)
        log_panel = self.panel(page)
        log_panel.grid(row=0, column=0, sticky="nsew")
        log_panel.rowconfigure(1, weight=1)
        log_panel.columnconfigure(0, weight=1)
        actions = tk.Frame(log_panel, bg=CARD)
        actions.grid(row=0, column=0, sticky="ew", padx=16, pady=(0, 8))
        tk.Label(actions, text="实时日志", bg=CARD, fg=INK, font=("PingFang SC", 15, "bold")).pack(side="left", padx=(0, 18))
        RoundedButton(actions, "停止任务", self.stop_current_task, primary=True, width=120).pack(side="left")
        RoundedButton(actions, "清空日志", self.clear_log, width=110).pack(side="left", padx=8)
        self.log_text = scrolledtext.ScrolledText(log_panel, bg="#211922", fg="#fff8f8", insertbackground="white", relief="flat", font=("Menlo", 11), wrap="word")
        self.log_text.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        self.log_text.configure(state="disabled")

    def choose_output(self) -> None:
        selected = filedialog.askdirectory(title="选择输出根目录")
        if selected:
            self.var_output_root.set(selected)
            self.save_config()

    def open_output(self) -> None:
        try:
            root = self.output_root()
            subprocess.Popen(["open", str(root)])
        except Exception as exc:
            messagebox.showerror("打开失败", str(exc))

    def output_root(self) -> Path:
        value = self.var_output_root.get().strip()
        if not value:
            raise ValueError("请先选择输出目录")
        path = Path(value).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def crawl_root(self) -> Path:
        return self.output_root() / "素材爬取"

    def organize_root(self) -> Path:
        return self.output_root() / "整理"

    def page_output(self) -> Path:
        return self.output_root() / "广告素材.json"

    def scan_output(self) -> Path:
        return self.output_root() / "投放者扫描.json"

    def save_config(self) -> None:
        c = self.config_data
        c.mode = self.var_mode.get()
        c.media_type = self.var_media_type.get()
        c.page_url = self.var_page_url.get().strip()
        c.stop_library_id = self.var_stop_library_id.get().strip()
        c.ids_text = self.ids_text.get("1.0", "end").strip() if hasattr(self, "ids_text") else c.ids_text
        c.output_root = self.var_output_root.get().strip()
        c.advertiser_filter = self.var_filter.get()
        c.selected_advertisers = sorted(self.selected_advertisers)
        c.headless = self.var_headless.get()
        c.require_hd_video = self.var_require_hd.get()
        c.download_images = self.var_download.get()
        c.scroll_rounds = int(self.var_scroll_rounds.get() or 0)
        c.stop_after_stable_rounds = int(self.var_stable_rounds.get() or 0)
        c.wait_ms = int(self.var_wait_ms.get() or 0)
        c.concurrency = int(self.var_concurrency.get())
        if not 1 <= c.concurrency <= 5:
            raise ValueError("并发数量必须为 1–5")
        if c.wait_ms < 0:
            raise ValueError("滚动等待时间不能为负数")
        c.max_cards = self.var_max_cards.get().strip()
        c.organize_prefix = self.var_organize_prefix.get().strip()
        c.capcut_draft_name = self.var_capcut_draft_name.get().strip()
        c.capcut_width = int(float(self.var_capcut_width.get() or 1080))
        c.capcut_height = int(float(self.var_capcut_height.get() or 1920))
        c.capcut_scale = float(self.var_capcut_scale.get() or 1.03)
        c.capcut_speed = float(self.var_capcut_speed.get() or 0.93)
        self.store.save(c)
        self.status_var.set("配置已保存")

    def common_crawl_args(self) -> list[str]:
        args = ["--scroll-rounds", self.var_scroll_rounds.get().strip() or "40"]
        args += ["--stop-after-stable-rounds", self.var_stable_rounds.get().strip() or "6"]
        args += ["--wait-ms", self.var_wait_ms.get().strip() or "2500"]
        args.append("--headless" if self.var_headless.get() else "--show")
        if self.var_download.get():
            args.append("--download-images")
        if self.var_require_hd.get():
            args.append("--require-hd-video")
        if self.var_max_cards.get().strip():
            args += ["--max-cards", self.var_max_cards.get().strip()]
        return args

    def start_scan(self) -> None:
        if self.runner.running:
            messagebox.showinfo("任务运行中", "请先停止或等待当前任务结束")
            return
        try:
            self.save_config()
            command = [*script_command(PAGE_UNTIL_ID), "--mode", "scan", "--url", with_media_type(self.var_page_url.get().strip(), self.var_media_type.get()), "--output", str(self.scan_output())]
            command += self.common_crawl_args()
            self.motion.start()
            self.status_dot.start()
            self.show_page("logs")
            self.runner.run("扫描投放者", command, PROJECT_ROOT)
        except Exception as exc:
            messagebox.showerror("无法扫描", str(exc))

    def start_page_crawl(self) -> None:
        if self.runner.running:
            messagebox.showinfo("任务运行中", "请先停止或等待当前任务结束")
            return
        try:
            self.save_config()
            command = [*script_command(PAGE_UNTIL_ID), "--mode", "crawl", "--url", with_media_type(self.var_page_url.get().strip(), self.var_media_type.get())]
            command += ["--asset-dir", str(self.crawl_root()), "--output", str(self.page_output()), "--result-count-root", str(self.output_root())]
            if self.var_stop_library_id.get().strip():
                command += ["--stop-library-id", self.var_stop_library_id.get().strip()]
            selected = sorted(self.selected_advertisers)
            if self.var_filter.get() == "include":
                for name in selected:
                    command += ["--include-advertiser", name]
            elif self.var_filter.get() == "exclude":
                for name in selected:
                    command += ["--exclude-advertiser", name]
            command += self.common_crawl_args()
            self.motion.start()
            self.status_dot.start()
            self.show_page("logs")
            self.runner.run("页面抓取", command, PROJECT_ROOT)
        except Exception as exc:
            messagebox.showerror("无法抓取", str(exc))

    def ids(self) -> list[str]:
        ids = parse_ids(self.ids_text.get("1.0", "end"))
        if not ids:
            raise ValueError("请输入至少一个资料库编号")
        return ids

    def start_ids_workflow(self, retry: bool = False) -> None:
        if self.runner.running:
            messagebox.showinfo("任务运行中", "请先停止或等待当前任务结束")
            return
        try:
            self.save_config()
            self.workflow_ids = self.ids()
            if not retry:
                prefix = self.var_organize_prefix.get().strip() or f"{time.localtime().tm_mon}{time.localtime().tm_mday}"
                self.config_data.retry_context = {
                    "ids": list(self.workflow_ids), "prefix": prefix,
                    "output_root": str(self.output_root()),
                    "settings": {
                        key: getattr(self.config_data, key) for key in (
                            "media_type", "require_hd_video", "download_images",
                            "headless", "scroll_rounds", "stop_after_stable_rounds",
                            "wait_ms", "max_cards", "concurrency",
                        )
                    },
                }
                self.config_data.last_failed_ids = []
                self.store.save(self.config_data)
            self.workflow_report = self.output_root() / f".抓取结果-{time.time_ns()}.json"
            self.workflow_steps = ["crawl", "organize", "summary"]
            if self.var_media_type.get() == "photo":
                self.workflow_steps.append("export_images")
            else:
                self.workflow_steps.append("capcut")
            self.workflow_index = 0
            self.motion.start()
            self.status_dot.start()
            self.show_page("logs")
            self.run_next_workflow_step()
        except Exception as exc:
            messagebox.showerror("无法开始", str(exc))

    def run_next_workflow_step(self) -> None:
        if self.workflow_index >= len(self.workflow_steps):
            self.workflow_steps = []
            self.motion.stop()
            self.status_dot.stop()
            failed_count = len(self.config_data.last_failed_ids)
            self.status_var.set(f"成功素材已整理 · {failed_count} 个编号待重试" if failed_count else "全流程完成")
            return
        step = self.workflow_steps[self.workflow_index]
        self.workflow_index += 1
        if step == "crawl":
            command = [*script_command(BATCH_BY_IDS), *self.workflow_ids, "--output-root", str(self.crawl_root()), "--media-type", self.var_media_type.get()]
            command += ["--report", str(self.workflow_report)]
            command += ["--concurrency", self.var_concurrency.get()]
            command += self.common_crawl_args()
            self.runner.run("资料库编号抓取", command, PROJECT_ROOT)
        elif step == "organize":
            command = [*script_command(COPY_FOLDERS), *self.workflow_ids, "--target", str(self.organize_root()), "--source-root", str(self.crawl_root())]
            context = self.config_data.retry_context
            command += [
                "--reuse-existing", "--prefix", context["prefix"],
                "--order-ids", ",".join(context["ids"]),
            ]
            self.runner.run("整理素材", command, PROJECT_ROOT)
        elif step == "summary":
            script = SUMMARY_IMAGE if self.var_media_type.get() == "photo" else SUMMARY_VIDEO
            command = [*script_command(script), "-i", str(self.organize_root()), "-o", str(self.organize_root() / "整理.md")]
            self.runner.run("生成整理文档", command, PROJECT_ROOT)
        elif step == "export_images":
            command = [*script_command(EXPORT_IMAGE_MATERIALS), "--input", str(self.organize_root())]
            command += ["--prefix", self.config_data.retry_context["prefix"]]
            self.runner.run("导出图片素材", command, PROJECT_ROOT)
        elif step == "capcut":
            try:
                self.backend.ensure_running()
            except Exception as exc:
                self.motion.stop()
                messagebox.showerror("剪映后端不可用", str(exc))
                return
            command = [*script_command(CAPCUT_IMPORT), "--from-dir", str(self.organize_root()), "--one-per-folder"]
            command += ["--api-base", CAPCUT_DEFAULT_API, "--capcut-mate-root", str(CAPCUT_DATA_ROOT)]
            command += ["--width", self.var_capcut_width.get() or "1080", "--height", self.var_capcut_height.get() or "1920"]
            command += ["--scale", self.var_capcut_scale.get() or "1.03", "--speed", self.var_capcut_speed.get() or "0.93"]
            if self.var_capcut_draft_name.get().strip():
                command += ["--draft-name", self.var_capcut_draft_name.get().strip()]
            for pattern in split_globs(self.config_data.capcut_exclude_globs):
                command += ["--exclude-glob", pattern]
            self.runner.run("剪映导入", command, PROJECT_ROOT)

    def retry_failed(self) -> None:
        if self.runner.running:
            messagebox.showinfo("任务运行中", "请先等待当前任务结束")
            return
        failed = self.config_data.last_failed_ids
        if not failed:
            messagebox.showinfo("没有失败编号", "当前没有记录失败编号")
            return
        context = self.config_data.retry_context
        if not context:
            root = Path(self.config_data.output_root).expanduser()
            if not self.config_data.output_root or not (root / "素材爬取").is_dir():
                messagebox.showerror("旧版重试记录", "请先在总控台选择原批次的输出目录，才能核对实际失败编号。")
                return
            original_ids = list(failed)
            failed = failed_ids_from_local_results(original_ids, root, self.config_data.media_type)
            self.config_data.last_failed_ids = failed
            context = {
                "ids": original_ids, "output_root": str(root.resolve()),
                "prefix": self.config_data.organize_prefix or f"{time.localtime().tm_mon}{time.localtime().tm_mday}",
                "settings": {
                    key: getattr(self.config_data, key) for key in (
                        "media_type", "require_hd_video", "download_images", "headless",
                        "scroll_rounds", "stop_after_stable_rounds", "wait_ms", "max_cards", "concurrency",
                    )
                },
            }
            self.config_data.retry_context = context
            self.store.save(self.config_data)
            self.log(f"已核对旧版整批记录：只重试缺少本地素材的 {len(failed)} 条")
            if not failed:
                messagebox.showinfo("无需重抓", "原批次的素材均已存在，没有需要重新抓取的编号。")
                return
        self.var_output_root.set(context["output_root"])
        self.var_organize_prefix.set(context["prefix"])
        settings = context["settings"]
        for key, variable in (
            ("media_type", self.var_media_type), ("require_hd_video", self.var_require_hd),
            ("download_images", self.var_download), ("headless", self.var_headless),
            ("scroll_rounds", self.var_scroll_rounds),
            ("stop_after_stable_rounds", self.var_stable_rounds),
            ("wait_ms", self.var_wait_ms), ("max_cards", self.var_max_cards),
            ("concurrency", self.var_concurrency),
        ):
            variable.set(settings.get(key, 2) if key == "concurrency" else settings[key])
        self.show_page("ids")
        self.ids_text.delete("1.0", "end")
        self.ids_text.insert("1.0", "\n".join(failed))
        self.start_ids_workflow(retry=True)

    def stop_current_task(self) -> None:
        stopped = self.runner.stop()
        self.workflow_steps = []
        self.motion.stop()
        self.status_dot.stop()
        self.status_var.set("已请求停止当前任务" if stopped else "当前没有运行中的任务")

    def clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def on_task_done(self, name: str, code: int, output: str) -> None:
        def handle() -> None:
            if name == "资料库编号抓取":
                try:
                    report = json.loads(self.workflow_report.read_text(encoding="utf-8"))
                    expected = list(self.workflow_ids)
                    if report["ids"] != expected:
                        raise ValueError("结果报告与当前批次编号不一致")
                    succeeded = report["succeeded"]
                    failed = report["failed"] + report["pending"]
                    if (
                        set(succeeded) & set(failed)
                        or set(succeeded + failed) != set(expected)
                        or len(succeeded + failed) != len(expected)
                    ):
                        raise ValueError("结果报告缺失或重复编号")
                    self.config_data.last_failed_ids = [item for item in expected if item in failed]
                    self.store.save(self.config_data)
                    if code >= 0 and succeeded and self.workflow_steps:
                        self.workflow_ids = [item for item in expected if item in succeeded]
                        if failed:
                            self.log(f"仅整理成功的 {len(succeeded)} 条；待重试 {len(failed)} 条")
                        self.run_next_workflow_step()
                        return
                except Exception as error:
                    self.log(f"无法读取本次逐条抓取结果：{error}")
                    self.workflow_steps = []
                    self.motion.stop()
                    self.status_dot.stop()
                    messagebox.showerror("抓取结果不完整", "未取得可靠的逐条结果，已停止后续流程；不会把整批误标为失败。请查看日志。")
                    return
            if code != 0:
                self.motion.stop()
                self.status_dot.stop()
                if code < 0:
                    self.status_var.set("任务已停止")
                else:
                    messagebox.showerror(name, f"任务失败，退出码 {code}。请查看实时日志。")
                return
            if name == "扫描投放者":
                self.load_scan_result()
                self.show_page("advertisers")
                self.motion.stop()
                self.status_dot.stop()
                return
            if self.workflow_steps and name in {"资料库编号抓取", "整理素材", "生成整理文档", "导出图片素材", "剪映导入"}:
                self.run_next_workflow_step()
                return
            self.motion.stop()
            self.status_dot.stop()
            self.status_var.set(f"{name} 完成")
        self.after(0, handle)

    def load_scan_result(self) -> None:
        path = self.scan_output()
        if not path.exists():
            messagebox.showwarning("没有扫描结果", f"未找到：{path}")
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        self.advertisers = [item for item in data if isinstance(item, dict)]
        self.status_var.set(f"扫描完成 · {len(self.advertisers)} 个投放者")
        self.render_advertisers()

    def toggle_advertiser(self, name: str) -> None:
        if name in self.selected_advertisers:
            self.selected_advertisers.remove(name)
        else:
            self.selected_advertisers.add(name)
        self.render_advertisers()
        self.save_config()

    def select_all_advertisers(self) -> None:
        self.selected_advertisers = {item.get("投放者", "") for item in self.advertisers if item.get("投放者")}
        self.render_advertisers()
        self.save_config()

    def clear_advertisers(self) -> None:
        self.selected_advertisers.clear()
        self.render_advertisers()
        self.save_config()

    def render_advertisers(self) -> None:
        if not hasattr(self, "ad_frame"):
            return
        for child in self.ad_frame.winfo_children():
            child.destroy()
        if not self.advertisers:
            empty = tk.Frame(self.ad_frame, bg=CARD)
            empty.pack(fill="both", expand=True, pady=50)
            tk.Label(empty, text="先点击「扫描投放者」", bg=CARD, fg=INK, font=("PingFang SC", 22, "bold")).pack()
            tk.Label(empty, text="扫描后这里会出现卡片，可勾选后只抓或排除。", bg=CARD, fg=MUTE, font=("PingFang SC", 13)).pack(pady=8)
            return
        for index, advertiser in enumerate(self.advertisers):
            card = AdvertiserCard(self.ad_frame, advertiser, advertiser.get("投放者", "") in self.selected_advertisers, self.toggle_advertiser)
            card.grid(row=index // 3, column=index % 3, sticky="nsew", padx=8, pady=8)
            card.reveal(min(index, 18) * 35)
        for col in range(3):
            self.ad_frame.columnconfigure(col, weight=1)

    def log(self, message: str) -> None:
        def append() -> None:
            if not hasattr(self, "log_text"):
                return
            self.log_text.configure(state="normal")
            self.log_text.insert("end", message + "\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.after(0, append)


def main() -> int:
    configure_runtime()
    run_worker_script()
    if len(sys.argv) == 3 and sys.argv[1] == "--backend-self-test":
        port = int(sys.argv[2])
        backend = CapcutBackendManager(print, f"http://127.0.0.1:{port}/openapi/capcut-mate/v1")
        if backend.is_running():
            raise SystemExit("测试端口已占用，请选择其他端口")
        try:
            backend.start()
            assert backend.is_running(), "内置后端检测失败"
            print("BUNDLED_BACKEND_START_OK", flush=True)
            recovered = CapcutBackendManager(print, backend.api_base)
            assert recovered.managed_process(), "无法恢复后端进程记录"
            # Legacy versions had no state file; recovery must also work by identity.
            backend.state_file.unlink(missing_ok=True)
            assert recovered.managed_process(), "无法接管旧版内置后端"
            assert recovered.stop(), "重开后的管理器无法关闭后端"
            print("BUNDLED_BACKEND_RECOVERY_STOP_OK", flush=True)
            backend.process.wait(timeout=10)
            backend.start()
            assert backend.is_running()
            print("BUNDLED_BACKEND_RESTART_OK", flush=True)
        finally:
            backend.stop()
        assert not backend.is_running(), "内置后端关闭失败"
        print("BUNDLED_BACKEND_STOP_OK", flush=True)
        return 0
    if len(sys.argv) == 3 and sys.argv[1] == "--backend-close-test":
        port = int(sys.argv[2])
        app = MetaMaterialClient()
        app.backend.api_base = f"http://127.0.0.1:{port}/openapi/capcut-mate/v1"
        if app.backend.is_running():
            app.destroy()
            raise SystemExit("测试端口已占用")
        def launch():
            try:
                app.backend.start()
                app.after(0, app.close_client)
            except Exception:
                app.after(0, app.destroy)
                raise
        app.after(50, lambda: threading.Thread(target=launch, daemon=True).start())
        app.mainloop()
        assert app.backend.process is None
        assert not app.backend.is_running()
        print("CLIENT_EXIT_BACKEND_STOP_OK", flush=True)
        return 0
    try:
        app = MetaMaterialClient()
        app.mainloop()
        return 0
    except Exception as error:
        APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
        crash_log = APP_SUPPORT_DIR / "crash.log"
        import traceback

        crash_log.write_text(traceback.format_exc(), encoding="utf-8")
        try:
            messagebox.showerror("Meta Pinboard 启动失败", f"错误已写入：{crash_log}\n\n{error}")
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
