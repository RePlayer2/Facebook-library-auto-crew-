#!/usr/bin/env python3
"""按资料库编号批量运行 Meta 广告素材抓取。

这个脚本不会重新实现抓取逻辑，而是复用 `crawler/meta_ad_card_extractor.py`。
输入一批资料库编号后，脚本会为每个编号生成对应的 Facebook Ads Library URL，
并逐个调用原爬虫脚本执行抓取、下载、保存 JSON 等步骤。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTRACTOR = PROJECT_ROOT / "crawler" / "meta_ad_card_extractor.py"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "meta素材" / "批量资料库编号抓取"
URL_TEMPLATE = (
    "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US"
    "&is_targeted_country=false&media_type=all&q={query}&search_type=keyword_unordered"
    "&sort_data[direction]=desc&sort_data[mode]=total_impressions"
)


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


def build_url(library_id: str) -> str:
    return URL_TEMPLATE.format(query=quote(library_id, safe=""))


def build_command(args: argparse.Namespace, library_id: str, passthrough_args: list[str]) -> list[str]:
    output_root = args.output_root.expanduser().resolve()
    item_root = output_root / library_id
    asset_dir = item_root / "广告素材文件"
    output_json = item_root / "广告素材.json"
    save_html = item_root / "样式_抓取.html"

    command = [
        sys.executable,
        str(EXTRACTOR),
        "--crawl",
        "--url",
        build_url(library_id),
        "--asset-dir",
        str(asset_dir),
        "--output",
        str(output_json),
        "--result-count-root",
        str(item_root),
        "--save-html",
        str(save_html),
        "--scroll-rounds",
        str(args.scroll_rounds),
        "--stop-after-stable-rounds",
        str(args.stop_after_stable_rounds),
        "--wait-ms",
        str(args.wait_ms),
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
    parser.add_argument("--headless", action="store_true", default=True, help="使用无头浏览器，默认开启。")
    parser.add_argument("--show", action="store_true", help="打开可见浏览器；传入后会覆盖无头显示行为。")
    parser.add_argument("--download-images", action="store_true", default=True, help="下载图片/视频素材，默认开启。")
    parser.add_argument("--no-download-images", dest="download_images", action="store_false", help="只抓 JSON，不下载素材。")
    parser.add_argument("--require-hd-video", action="store_true", help="视频素材要求切换并下载 HD。")
    parser.add_argument("--max-cards", type=int, help="每个资料库编号最多保存多少条卡片。")
    parser.add_argument("--scroll-rounds", type=int, default=30, help="每个编号最多滚动次数。")
    parser.add_argument("--stop-after-stable-rounds", type=int, default=6, help="连续多少轮无新增后停止。")
    parser.add_argument("--wait-ms", type=int, default=6000, help="每次滚动后的等待时间，毫秒。")
    parser.add_argument("--no-expand-grouped-ads", action="store_true", help="不展开分组广告。")
    parser.add_argument("--no-result-count-folder", action="store_true", help="不创建本次返回N个结果文件夹。")
    parser.add_argument("--storage-state", type=Path, help="Playwright 登录态 JSON。")
    parser.add_argument("--continue-on-error", action="store_true", default=True, help="单个编号失败后继续跑后续编号，默认开启。")
    parser.add_argument("--stop-on-error", dest="continue_on_error", action="store_false", help="单个编号失败后立即停止。")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要执行的命令，不实际运行。")
    return parser.parse_known_args()


def main() -> int:
    args, passthrough_args = parse_args()
    try:
        library_ids = normalize_ids(args.ids, args.ids_file)
    except Exception as error:
        print(f"错误: {error}", file=sys.stderr)
        return 1

    print(f"资料库编号数量: {len(library_ids)}")
    print(f"输出根目录: {args.output_root.expanduser().resolve()}")

    failed: list[tuple[str, int]] = []
    for index, library_id in enumerate(library_ids, start=1):
        command = build_command(args, library_id, passthrough_args)
        print()
        print(f"========== [{index}/{len(library_ids)}] 开始抓取资料库编号: {library_id} ==========")
        print(f"URL: {build_url(library_id)}")
        print("命令:")
        print(" ".join(repr(part) if " " in part else part for part in command))

        if args.dry_run:
            continue

        result = subprocess.run(command, cwd=PROJECT_ROOT)
        if result.returncode != 0:
            failed.append((library_id, result.returncode))
            print(f"资料库编号 {library_id} 抓取失败，退出码: {result.returncode}", file=sys.stderr)
            if not args.continue_on_error:
                break
        else:
            print(f"========== [{index}/{len(library_ids)}] 完成: {library_id} ==========")

    print()
    print(f"批量完成：成功 {len(library_ids) - len(failed)} 个，失败 {len(failed)} 个")
    if failed:
        print("失败列表:")
        for library_id, returncode in failed:
            print(f"  {library_id}: exit {returncode}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
