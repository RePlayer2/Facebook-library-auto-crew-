#!/usr/bin/env python3
"""按页面从上到下抓取 Meta 广告卡片，直到遇到指定资料库编号停止。

新增能力：
1. scan 模式先扫描页面上方可见/可滚动卡片的投放者，按投放者去重输出清单。
2. crawl 模式支持只抓取指定投放者，或排除指定投放者。
3. crawl 模式从页面上到下实时保存，遇到 --stop-library-id 后保存该卡片并停止。

本脚本复用 meta_ad_card_extractor.py 里已有的卡片解析、HD 切换、下载和 Markdown 生成逻辑。
"""

from __future__ import annotations

import argparse
import json
import sys
from html import escape
from pathlib import Path
from typing import Any
from bundled_runtime import chromium_options

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from crawler.meta_ad_card_extractor import (  # noqa: E402
    download_card_images,
    extract_card,
    import_playwright,
    parse_html,
    select_visible_hd_video_options,
    video_quality_from_card_html,
    write_result_count_folder,
)

DEFAULT_URL = (
    "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US"
    "&is_targeted_country=false&media_type=all&q=tryfortis&search_type=keyword_unordered"
)


READ_VISIBLE_CARDS_JS = r"""
() => {
    const clean = value => (value || '').replace(/\s+/g, ' ').trim();
    for (const video of document.querySelectorAll('video')) {
        const currentSrc = video.currentSrc || video.src || video.getAttribute('src') || '';
        if (currentSrc && !currentSrc.startsWith('blob:')) {
            video.setAttribute('src', currentSrc);
            video.setAttribute('data-current-src', currentSrc);
        }
        if (video.poster) video.setAttribute('poster', video.poster);
    }
    const libraryIdOf = element => {
        const text = clean(element.innerText || element.textContent || '');
        const match = text.match(/(?:资料库编号|Library ID)[:：\s]*([0-9]+)/i);
        return match ? match[1] : null;
    };
    return [...document.querySelectorAll('div, article, section')]
        .map(element => {
            const text = clean(element.innerText || element.textContent || '');
            const libraryId = libraryIdOf(element);
            return { element, text, libraryId };
        })
        .filter(item => {
            if (!item.libraryId || item.text.length < 80) return false;
            if (!/(赞助内容|Sponsored)/i.test(item.text)) return false;
            const parentText = clean(item.element.parentElement?.innerText || '');
            return !parentText || parentText.length > item.text.length * 1.15;
        })
        .map(item => {
            const rect = item.element.getBoundingClientRect();
            return {
                library_id: item.libraryId,
                html: item.element.outerHTML,
                top: rect.top + window.scrollY,
            };
        })
        .sort((a, b) => a.top - b.top);
}
"""


def split_names(values: list[str] | None) -> set[str]:
    names: set[str] = set()
    for value in values or []:
        for item in value.replace("，", ",").split(","):
            cleaned = item.strip()
            if cleaned:
                names.add(cleaned)
    return names


def normalize_name(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def is_navigation_evaluate_error(error: Exception) -> bool:
    message = str(error).lower()
    return "execution context was destroyed" in message or "most likely because of a navigation" in message


def read_visible_cards(page: Any, timeout: int) -> list[dict[str, Any]]:
    for attempt in range(1, 4):
        try:
            return page.evaluate(READ_VISIBLE_CARDS_JS) or []
        except Exception as error:
            if not is_navigation_evaluate_error(error):
                raise
            print(f"[页面跳转] 读取卡片时页面正在刷新，重试 {attempt}/3。", flush=True)
            try:
                page.wait_for_load_state("domcontentloaded", timeout=timeout)
            except Exception:
                pass
            page.wait_for_timeout(1_000)
    return []


def safe_select_hd(page: Any, timeout: int) -> None:
    try:
        select_visible_hd_video_options(page)
    except Exception as error:
        if not is_navigation_evaluate_error(error):
            raise
        print("[页面跳转] 切换 HD 时页面正在刷新，等待后继续。", flush=True)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=timeout)
        except Exception:
            pass
        page.wait_for_timeout(1_000)


def card_allowed(card: dict[str, str], include: set[str], exclude: set[str]) -> bool:
    advertiser = normalize_name(card.get("投放者", ""))
    include_norm = {normalize_name(item) for item in include}
    exclude_norm = {normalize_name(item) for item in exclude}
    if include_norm and advertiser not in include_norm:
        return False
    if exclude_norm and advertiser in exclude_norm:
        return False
    return True


def crawl_page(
    *,
    url: str,
    mode: str,
    output: Path,
    asset_dir: Path,
    result_count_root: Path | None,
    stop_library_id: str | None,
    include_advertisers: set[str],
    exclude_advertisers: set[str],
    headless: bool,
    timeout: int,
    wait_ms: int,
    scroll_rounds: int,
    stop_after_stable_rounds: int,
    storage_state: Path | None,
    download_images: bool,
    require_hd_video: bool,
    max_cards: int | None,
) -> int:
    sync_playwright, PlaywrightTimeoutError = import_playwright()
    cards_by_id: dict[str, dict[str, str]] = {}
    advertisers: dict[str, dict[str, str]] = {}
    card_html_by_id: dict[str, str] = {}

    output.parent.mkdir(parents=True, exist_ok=True)
    if download_images:
        asset_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**chromium_options(headless))
        context_options: dict[str, Any] = {"viewport": {"width": 1440, "height": 1200}}
        if storage_state:
            context_options["storage_state"] = str(storage_state)
        context = browser.new_context(**context_options)
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            page.wait_for_timeout(wait_ms)
            if require_hd_video:
                safe_select_hd(page, timeout)
                page.wait_for_timeout(500)

            stable_rounds = 0
            should_stop = False

            for round_index in range(0, scroll_rounds + 1):
                if round_index > 0:
                    page.mouse.wheel(0, 2500)
                    page.wait_for_timeout(wait_ms)
                    if require_hd_video:
                        safe_select_hd(page, timeout)
                        page.wait_for_timeout(500)

                visible_cards = read_visible_cards(page, timeout)
                if require_hd_video:
                    sd_cards = [card for card in visible_cards if video_quality_from_card_html(str(card.get("html") or "")) == "sd"]
                    if sd_cards:
                        print(f"[HD重试] 当前可见 {len(sd_cards)} 条视频仍是 SD，先尝试切换到 HD。", flush=True)
                        safe_select_hd(page, timeout)
                        page.wait_for_timeout(1_000)
                        visible_cards = read_visible_cards(page, timeout)

                new_count = 0
                for visible in visible_cards:
                    library_id = str(visible.get("library_id") or "").strip()
                    html = str(visible.get("html") or "")
                    if not library_id or not html:
                        continue
                    if library_id not in card_html_by_id:
                        new_count += 1
                    previous = card_html_by_id.get(library_id)
                    previous_quality = video_quality_from_card_html(previous) if previous else ""
                    current_quality = video_quality_from_card_html(html)
                    should_replace = previous is None or previous_quality != "hd" and current_quality == "hd"
                    if not should_replace:
                        continue

                    card_html_by_id[library_id] = html
                    card = extract_card(parse_html(html))
                    card["资料库编号"] = card.get("资料库编号") or library_id
                    advertiser = card.get("投放者", "") or "未知投放者"
                    if advertiser not in advertisers:
                        advertisers[advertiser] = {
                            "投放者": advertiser,
                            "投放者头像": card.get("投放者头像", ""),
                            "首次资料库编号": library_id,
                        }
                        print(f"[投放者] 当前已发现 {len(advertisers)} 个 | {advertiser}", flush=True)

                    if mode == "scan":
                        continue
                    if not card_allowed(card, include_advertisers, exclude_advertisers):
                        print(f"[跳过] 资料库编号: {library_id} | 投放者: {advertiser}", flush=True)
                    elif library_id not in cards_by_id:
                        cards_by_id[library_id] = card
                        if download_images:
                            download_card_images([card], asset_dir, require_hd_video=require_hd_video)
                        output.write_text(json.dumps(list(cards_by_id.values()), ensure_ascii=False, indent=2), encoding="utf-8")
                        print(
                            f"[保存] {len(cards_by_id)} 条 | 资料库编号: {library_id} | 投放者: {advertiser} | "
                            f"目标停止编号: {stop_library_id or '未设置'}",
                            flush=True,
                        )
                        if max_cards and len(cards_by_id) >= max_cards:
                            should_stop = True

                    if stop_library_id and library_id == stop_library_id:
                        print(f"[停止] 已遇到目标资料库编号：{stop_library_id}", flush=True)
                        should_stop = True
                        break

                scan_output = output if mode == "scan" else output.with_name(output.stem + "_投放者扫描.json")
                scan_output.write_text(json.dumps(list(advertisers.values()), ensure_ascii=False, indent=2), encoding="utf-8")

                print(
                    f"[滚动进度] {round_index}/{scroll_rounds} | 本轮新增DOM卡片: {new_count} | "
                    f"唯一DOM卡片: {len(card_html_by_id)} | 已保存: {len(cards_by_id)} | 投放者: {len(advertisers)} | 连续无新增: {stable_rounds}",
                    flush=True,
                )

                if should_stop:
                    break
                if new_count == 0:
                    stable_rounds += 1
                    if stable_rounds >= stop_after_stable_rounds:
                        break
                else:
                    stable_rounds = 0

            if mode == "scan":
                print(f"扫描完成：共发现 {len(advertisers)} 个投放者", flush=True)
                return 0

            if not output.exists():
                output.write_text("[]", encoding="utf-8")
            if result_count_root:
                write_result_count_folder(list(cards_by_id.values()), result_count_root)
            print(f"抓取完成：保存 {len(cards_by_id)} 条，投放者 {len(advertisers)} 个", flush=True)
            return 0
        except PlaywrightTimeoutError as error:
            raise RuntimeError(f"页面加载超时: {error}") from error
        finally:
            browser.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="页面从上到下抓取，直到遇到指定资料库编号停止，并支持投放者扫描/过滤。")
    parser.add_argument("--mode", choices=["scan", "crawl"], default="crawl", help="scan 只扫描投放者；crawl 保存素材。")
    parser.add_argument("--url", default=DEFAULT_URL, help="Meta Ads Library 页面 URL。")
    parser.add_argument("--stop-library-id", help="抓到该资料库编号后停止；该卡片会先按条件保存。")
    parser.add_argument("--include-advertiser", action="append", help="只抓这些投放者，可重复传入或用逗号分隔。")
    parser.add_argument("--exclude-advertiser", action="append", help="排除这些投放者，可重复传入或用逗号分隔。")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "meta素材" / "页面直到编号抓取" / "广告素材.json", help="输出 JSON。")
    parser.add_argument("--asset-dir", type=Path, default=PROJECT_ROOT / "meta素材" / "页面直到编号抓取" / "广告素材文件", help="素材下载目录。")
    parser.add_argument("--result-count-root", type=Path, help="创建“本次返回N个结果”文件夹的根目录。")
    parser.add_argument("--download-images", action="store_true", help="下载图片/视频素材并生成单卡 Markdown。")
    parser.add_argument("--require-hd-video", action="store_true", help="尝试切换并只下载 HD/720p 视频。")
    parser.add_argument("--max-cards", type=int, help="最多保存多少条符合条件的素材。")
    parser.add_argument("--headless", action="store_true", help="无头浏览器。")
    parser.add_argument("--show", action="store_true", help="显示浏览器窗口。")
    parser.add_argument("--timeout", type=int, default=60_000, help="页面加载超时，毫秒。")
    parser.add_argument("--wait-ms", type=int, default=2_500, help="每次滚动等待时间，毫秒。")
    parser.add_argument("--scroll-rounds", type=int, default=120, help="最多滚动次数。")
    parser.add_argument("--stop-after-stable-rounds", type=int, default=8, help="连续多少轮无新增后停止。")
    parser.add_argument("--storage-state", type=Path, help="Playwright 登录态 JSON。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    include = split_names(args.include_advertiser)
    exclude = split_names(args.exclude_advertiser)
    if include and exclude:
        overlap = {normalize_name(item) for item in include} & {normalize_name(item) for item in exclude}
        if overlap:
            raise SystemExit(f"同一个投放者不能同时 include 和 exclude：{', '.join(sorted(overlap))}")
    return crawl_page(
        url=args.url,
        mode=args.mode,
        output=args.output.expanduser().resolve(),
        asset_dir=args.asset_dir.expanduser().resolve(),
        result_count_root=args.result_count_root.expanduser().resolve() if args.result_count_root else None,
        stop_library_id=args.stop_library_id,
        include_advertisers=include,
        exclude_advertisers=exclude,
        headless=args.headless and not args.show,
        timeout=args.timeout,
        wait_ms=args.wait_ms,
        scroll_rounds=args.scroll_rounds,
        stop_after_stable_rounds=args.stop_after_stable_rounds,
        storage_state=args.storage_state.expanduser().resolve() if args.storage_state else None,
        download_images=args.download_images,
        require_hd_video=args.require_hd_video,
        max_cards=args.max_cards,
    )


if __name__ == "__main__":
    raise SystemExit(main())
