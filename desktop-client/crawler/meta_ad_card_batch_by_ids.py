#!/usr/bin/env python3
"""按资料库编号批量运行 Meta 广告素材抓取。

这个脚本不会重新实现抓取逻辑，而是复用 `crawler/meta_ad_card_extractor.py`。
输入一批资料库编号后，脚本会为每个编号生成对应的 Facebook Ads Library URL，
并逐个调用原爬虫脚本执行抓取、下载、保存 JSON 等步骤。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import signal
import threading
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import sys
from pathlib import Path
from urllib.parse import quote

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTRACTOR = PROJECT_ROOT / "crawler" / "meta_ad_card_extractor.py"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "meta素材" / "批量资料库编号抓取"
URL_TEMPLATE = (
    "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US"
    "&is_targeted_country=false&media_type={media_type}&q={query}&search_type=keyword_unordered"
    "&sort_data[direction]=desc&sort_data[mode]=total_impressions"
)


def python_bin() -> str:
    return os.environ.get("SIMILAR_CRAW_PYTHON") or sys.executable


def script_command(script: Path) -> list[str]:
    worker_exe = os.environ.get("SIMILAR_CRAW_WORKER_EXE")
    project_root = Path(os.environ.get("SIMILAR_CRAW_PROJECT_ROOT") or PROJECT_ROOT)
    if worker_exe:
        try:
            script_arg = str(script.relative_to(project_root))
        except ValueError:
            script_arg = str(script)
        return [worker_exe, "--worker-script", script_arg]
    return [python_bin(), str(script)]


def normalize_ids(values: list[str], ids_file: Path | None) -> list[str]:
    raw_values: list[str] = []
    raw_values.extend(values)
    if ids_file:
        if not ids_file.exists():
            raise FileNotFoundError(f"编号文件不存在: {ids_file}")
        raw_values.append(ids_file.read_text(encoding="utf-8"))

    ids: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        for candidate in re.split(r"[\s,，]+", value.strip()):
            if not candidate:
                continue
            if not re.fullmatch(r"\d+", candidate):
                raise ValueError(f"资料库编号必须是纯数字: {candidate}")
            if candidate not in seen:
                seen.add(candidate)
                ids.append(candidate)
    if not ids:
        raise ValueError("没有输入任何资料库编号")
    return ids


def build_url(library_id: str, media_type: str) -> str:
    return URL_TEMPLATE.format(query=quote(library_id, safe=""), media_type=media_type)

def validate_download(args: argparse.Namespace, library_id: str) -> None:
    path = args.output_root / library_id / "广告素材.json"
    cards = json.loads(path.read_text(encoding="utf-8"))
    matched = [card for card in cards if str(card.get("资料库编号", "")) == library_id]
    if not matched:
        raise ValueError("未获得该编号的广告记录")
    if not args.download_images:
        return
    for card in matched:
        kind = "广告视频" if card.get("广告视频") else "广告图片"
        if args.media_type == "video" and kind != "广告视频":
            raise ValueError("未获得该编号的视频地址")
        filename = card.get(f"{kind}本地文件")
        if not filename or not Path(filename).is_file() or Path(filename).stat().st_size == 0:
            raise ValueError(card.get(f"{kind}下载错误") or f"{kind}未下载成功")


def build_command(args: argparse.Namespace, library_id: str, passthrough_args: list[str]) -> list[str]:
    output_root = args.output_root.expanduser().resolve()
    item_root = output_root / library_id
    asset_dir = item_root / "广告素材文件"
    output_json = item_root / "广告素材.json"
    save_html = item_root / "样式_抓取.html"
    scroll_rounds = args.scroll_rounds
    stop_after_stable_rounds = args.stop_after_stable_rounds
    wait_ms = args.wait_ms

    if args.require_hd_video and not args.fast_hd:
        scroll_rounds = max(scroll_rounds, args.hd_min_scroll_rounds)
        stop_after_stable_rounds = max(stop_after_stable_rounds, args.hd_min_stable_rounds)
        wait_ms = max(wait_ms, args.hd_min_wait_ms)

    command = [
        *script_command(EXTRACTOR),
        "--crawl",
        "--url",
        build_url(library_id, args.media_type),
        "--asset-dir",
        str(asset_dir),
        "--output",
        str(output_json),
        "--result-count-root",
        str(item_root),
        "--save-html",
        str(save_html),
        "--scroll-rounds",
        str(scroll_rounds),
        "--stop-after-stable-rounds",
        str(stop_after_stable_rounds),
        "--wait-ms",
        str(wait_ms),
    ]

    if args.headless:
        command.append("--headless")
    if args.show:
        command.append("--show")
    if args.download_images:
        command.append("--download-images")
    if args.require_hd_video:
        command.append("--require-hd-video")
    if args.max_cards is not None:
        command.extend(["--max-cards", str(args.max_cards)])
    if args.no_expand_grouped_ads:
        command.append("--no-expand-grouped-ads")
    if args.no_result_count_folder:
        command.append("--no-result-count-folder")
    if args.storage_state:
        command.extend(["--storage-state", str(args.storage_state.expanduser().resolve())])

    command.extend(passthrough_args)
    return command


def parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description="按资料库编号批量调用 meta_ad_card_extractor.py 抓取广告素材。",
        epilog="未识别的额外参数会原样传给 meta_ad_card_extractor.py，例如 --timeout 90000。",
    )
    parser.add_argument("ids", nargs="*", help="资料库编号，可传多个，也可用逗号/空格分隔。")
    parser.add_argument("--ids-file", type=Path, help="资料库编号文件，一行一个或用逗号/空格分隔。")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT, help="批量输出根目录。")
    parser.add_argument("--media-type", choices=["all", "photo", "video"], default="all", help="广告素材类型，默认 all。")
    parser.add_argument("--headless", action="store_true", default=True, help="使用无头浏览器，默认开启。")
    parser.add_argument("--show", action="store_true", help="打开可见浏览器；传入后会覆盖无头显示行为。")
    parser.add_argument("--download-images", action="store_true", default=True, help="下载图片/视频素材，默认开启。")
    parser.add_argument("--no-download-images", dest="download_images", action="store_false", help="只抓 JSON，不下载素材。")
    parser.add_argument("--require-hd-video", action="store_true", help="视频素材要求切换并下载 HD。")
    parser.add_argument("--max-cards", type=int, help="每个资料库编号最多保存多少条卡片。")
    parser.add_argument("--scroll-rounds", type=int, default=5, help="每个编号最多滚动次数，默认 5。")
    parser.add_argument("--stop-after-stable-rounds", type=int, default=3, help="连续多少轮无新增后停止，默认 3。")
    parser.add_argument("--wait-ms", type=int, default=2000, help="每次滚动后的等待时间，毫秒，默认 2000。")
    parser.add_argument("--hd-min-scroll-rounds", type=int, default=5, help="开启 --require-hd-video 时的最小滚动轮数，默认 5。")
    parser.add_argument("--hd-min-stable-rounds", type=int, default=3, help="开启 --require-hd-video 时的最小无新增停止轮数，默认 3。")
    parser.add_argument("--hd-min-wait-ms", type=int, default=2000, help="开启 --require-hd-video 时的最小等待时间，默认 2000 毫秒。")
    parser.add_argument("--fast-hd", action="store_true", help="关闭 HD 安全参数提升，完全按传入的滚动/等待参数执行。")
    parser.add_argument("--no-expand-grouped-ads", action="store_true", help="不展开分组广告。")
    parser.add_argument("--no-result-count-folder", action="store_true", help="不创建本次返回N个结果文件夹。")
    parser.add_argument("--storage-state", type=Path, help="Playwright 登录态 JSON。")
    parser.add_argument("--continue-on-error", action="store_true", default=True, help="单个编号失败后继续跑后续编号，默认开启。")
    parser.add_argument("--stop-on-error", dest="continue_on_error", action="store_false", help="单个编号失败后立即停止。")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要执行的命令，不实际运行。")
    parser.add_argument("--report", type=Path, help="逐条保存本次成功、失败和未执行编号。")
    parser.add_argument("--concurrency", type=int, choices=range(1, 6), default=2, help="同时抓取的编号数，1–5，默认 2。")
    return parser.parse_known_args()

def run_job(command: list[str], library_id: str, cancel: threading.Event,
            active: dict, lock: threading.Lock) -> int:
    """Each job owns a process group so stopping the batch also stops its browsers."""
    with lock:
        if cancel.is_set():
            return -signal.SIGTERM
        process = subprocess.Popen(
            command, cwd=PROJECT_ROOT, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1, start_new_session=True,
        )
        active[library_id] = process
    try:
        assert process.stdout is not None
        for line in process.stdout:
            print(f"[编号 {library_id}] {line.rstrip()}", flush=True)
        return process.wait()
    finally:
        with lock:
            active.pop(library_id, None)


def main() -> int:
    args, passthrough_args = parse_args()
    try:
        library_ids = normalize_ids(args.ids, args.ids_file)
    except Exception as error:
        print(f"错误: {error}", file=sys.stderr)
        return 1

    print(f"资料库编号数量: {len(library_ids)}")
    print(f"输出根目录: {args.output_root.expanduser().resolve()}")
    print(f"媒体类型: {args.media_type}")
    print(f"并发数量: {args.concurrency}（全部完成后才进入整理）")
    if args.require_hd_video and not args.fast_hd:
        print(
            "HD安全模式: 已开启；会自动把过低的 --scroll-rounds/--stop-after-stable-rounds/--wait-ms "
            f"提升到至少 {args.hd_min_scroll_rounds}/{args.hd_min_stable_rounds}/{args.hd_min_wait_ms}ms。"
        )

    failed: list[tuple[str, int]] = []
    report = {"ids": library_ids, "succeeded": [], "failed": [], "pending": list(library_ids)}

    def save_report() -> None:
        if args.report and not args.dry_run:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            temporary = args.report.with_suffix(".tmp")
            temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(args.report)

    save_report()
    if args.dry_run:
        for library_id in library_ids:
            print(build_command(args, library_id, passthrough_args))
        return 0
    cancel = threading.Event()
    active: dict[str, subprocess.Popen] = {}
    lock = threading.RLock()

    def interrupt(signum, frame):
        cancel.set()
        # Jobs run in separate groups; do not signal the GUI or the CapCut service.
        with lock:
            processes = list(active.values())
        for process in processes:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    previous = {sig: signal.signal(sig, interrupt) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            queued = iter(library_ids)
            running = {}
            def submit_next():
                if cancel.is_set():
                    return
                library_id = next(queued, None)
                if library_id is not None:
                    command = build_command(args, library_id, passthrough_args)
                    print(f"[开始] {library_id}", flush=True)
                    running[pool.submit(run_job, command, library_id, cancel, active, lock)] = library_id

            for _ in range(args.concurrency):
                submit_next()
            stop_scheduling = False
            while running:
                done, _ = wait(running, timeout=.2, return_when=FIRST_COMPLETED)
                if cancel.is_set():
                    # SIGTERM is usually enough; kill remaining groups if needed.
                    with lock:
                        for process in active.values():
                            try:
                                os.killpg(process.pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                for future in done:
                    library_id = running.pop(future)
                    try:
                        returncode = future.result()
                        if returncode == 0:
                            validate_download(args, library_id)
                    except Exception as error:
                        print(f"[失败] {library_id}: {error}", file=sys.stderr, flush=True)
                        returncode = 1
                    report["pending"].remove(library_id)
                    report["failed" if returncode else "succeeded"].append(library_id)
                    # Persist in input order regardless of completion order.
                    for key in ("succeeded", "failed"):
                        report[key].sort(key=library_ids.index)
                    save_report()
                    if returncode:
                        failed.append((library_id, returncode))
                        stop_scheduling |= not args.continue_on_error
                    print(f"[{'失败' if returncode else '完成'}] {library_id}", flush=True)
                if not stop_scheduling:
                    for _ in done:
                        submit_next()
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)

    print()
    print(f"批量完成：成功 {len(report['succeeded'])} 个，失败 {len(failed)} 个，未执行 {len(report['pending'])} 个")
    if failed or report["pending"]:
        print("失败列表:")
        for library_id, returncode in failed:
            print(f"  {library_id}: exit {returncode}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
