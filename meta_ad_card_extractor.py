#!/usr/bin/env python3
"""Crawl or parse Meta Ad Library cards into a compact JSON format.

This script is designed for the HTML snippets saved under ``meta素材``.  It can
also open a live Meta Ad Library URL with Playwright, scroll the page, save the
HTML, and then parse the same fields from the captured cards.

Examples:
    python crawler/meta_ad_card_extractor.py
    python crawler/meta_ad_card_extractor.py --input-html meta素材/样式.md --output crawler/data/tryfortis_cards.json
    python crawler/meta_ad_card_extractor.py --crawl --show --max-cards 100
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from dataclasses import dataclass, field
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen

DEFAULT_URL = (
    "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US"
    "&is_targeted_country=false&media_type=all&q=tryfortis&search_type=keyword_unordered"
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_HTML = PROJECT_ROOT / "meta素材" / "样式.md"
DEFAULT_CAPTURE_HTML = PROJECT_ROOT / "meta素材" / "样式_抓取.html"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "meta素材" / "广告素材.json"
DEFAULT_ASSET_DIR = PROJECT_ROOT / "meta素材" / "广告素材文件"
DEFAULT_RESULT_COUNT_ROOT = PROJECT_ROOT / "meta素材"

COMMON_UI_TEXTS = {
    "投放中",
    "Active",
    "平台",
    "Platform",
    "打开下拉菜单",
    "查看广告详情",
    "查看摘要详情",
    "See ad details",
    "See summary details",
    "展示次数：",
    "Impressions",
    "赞助内容",
    "Sponsored",
    "使用这个创意和文字",
}
CTA_TEXTS = {
    "learn more",
    "shop now",
    "get fortis",
    "sign up",
    "order now",
    "buy now",
    "download",
    "subscribe",
    "apply now",
    "详细了解",
    "去逛逛",
    "了解更多",
    "立即购买",
    "注册",
}
DOMAIN_RE = re.compile(r"^(?:https?://)?[A-Z0-9][A-Z0-9.-]*\.[A-Z]{2,}(?:\b|/)", re.I)
LIBRARY_ID_RE = re.compile(r"(?:资料库编号|Library ID)[:：\s]*([0-9]+)", re.I)
START_DATE_VALUE_RE = re.compile(
    r"((?:\d{4}年\d{1,2}月\d{1,2}日|[A-Z][a-z]+\s+\d{1,2},\s+\d{4}).{0,20}?(?:开始投放|Started running))",
    re.I,
)
START_DATE_RE = re.compile(r"(?:开始投放|Started running)", re.I)
AD_COUNT_RE = re.compile(r"^\d+\s*(?:条广告|ads?)$", re.I)
GROUPED_AD_COUNT_RE = re.compile(r"(\d+)\s*(?:条广告|ads?)\s*(?:使用这个创意和文字|using this creative and text)?", re.I)
RESULT_COUNT_RE = re.compile(r"约?\s*([0-9,]+)\s*(?:条结果|results)", re.I)
HD_VIDEO_RE = re.compile(r"(?:\bhd\b|720|high|sve_hd|progressive_hd)", re.I)
SD_VIDEO_RE = re.compile(r"(?:\bsd\b|360|480|sve_sd|progressive_sd)", re.I)


@dataclass
class Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["Node"] = field(default_factory=list)
    data: list[str] = field(default_factory=list)
    parent: "Node | None" = None

    def append_child(self, child: "Node") -> None:
        child.parent = self
        self.children.append(child)

    def add_data(self, value: str) -> None:
        if value:
            self.data.append(value)

    def iter_nodes(self) -> Any:
        yield self
        for child in self.children:
            yield from child.iter_nodes()

    def texts(self) -> list[str]:
        values: list[str] = []
        for value in self.data:
            cleaned = clean_text(value)
            if cleaned:
                values.append(cleaned)
        for child in self.children:
            values.extend(child.texts())
        return values

    def text_content(self) -> str:
        return " ".join(self.texts())

    def images(self) -> list[dict[str, str | None]]:
        values: list[dict[str, str | None]] = []
        if self.tag == "img":
            src = self.attrs.get("src") or self.attrs.get("data-src") or self.attrs.get("currentSrc")
            if src and not src.startswith("data:"):
                values.append(
                    {
                        "src": unescape(src),
                        "alt": self.attrs.get("alt"),
                        "width": self.attrs.get("width"),
                        "height": self.attrs.get("height"),
                    }
                )
        for child in self.children:
            values.extend(child.images())
        return values

    def videos(self) -> list[dict[str, str | None]]:
        values: list[dict[str, str | None]] = []
        if self.tag in {"video", "source"}:
            src = self.attrs.get("src") or self.attrs.get("data-src") or self.attrs.get("currentSrc")
            poster = self.attrs.get("poster") if self.tag == "video" else None
            if src and not src.startswith("blob:"):
                values.append({"src": unescape(src), "poster": unescape(poster or "") or None})
        for child in self.children:
            values.extend(child.videos())
        return values


class SnippetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("document")
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag.lower(), {key: value or "" for key, value in attrs})
        self.stack[-1].append_child(node)
        if tag.lower() not in {"br", "img", "input", "meta", "link", "hr", "source"}:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].add_data(data)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value or "").replace("\u200b", "")).strip()


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique_values.append(value)
    return unique_values


def parse_html(html: str) -> Node:
    parser = SnippetParser()
    parser.feed(html)
    return parser.root


def is_card_candidate(node: Node) -> bool:
    text = node.text_content()
    if not LIBRARY_ID_RE.search(text):
        return False
    if not re.search(r"赞助内容|Sponsored", text, re.I):
        return False
    if len(text) < 80:
        return False
    return True


def select_card_nodes(root: Node) -> list[Node]:
    by_library_id: dict[str, Node] = {}
    for node in root.iter_nodes():
        if node.tag not in {"div", "article", "section"} or not is_card_candidate(node):
            continue
        library_id = extract_library_id(node.text_content())
        if not library_id:
            continue
        previous = by_library_id.get(library_id)
        if previous is None:
            by_library_id[library_id] = node
            continue
        current_score = card_node_score(node)
        previous_score = card_node_score(previous)
        if current_score < previous_score:
            by_library_id[library_id] = node
    return list(by_library_id.values())


def card_node_score(node: Node) -> tuple[int, int]:
    text_length = len(node.text_content())
    image_count_penalty = 0 if len(node.images()) >= 2 else 100_000
    return image_count_penalty + text_length, len(node.children)


def extract_library_id(text: str) -> str | None:
    match = LIBRARY_ID_RE.search(text)
    return match.group(1) if match else None


def is_domain_text(value: str) -> bool:
    return bool(DOMAIN_RE.search(value.strip()))


def is_cta_text(value: str) -> bool:
    return value.strip().lower() in CTA_TEXTS


def is_noise_text(value: str) -> bool:
    if value in COMMON_UI_TEXTS:
        return True
    if LIBRARY_ID_RE.search(value) or START_DATE_RE.search(value) or AD_COUNT_RE.search(value):
        return True
    if value == "< 100" or value.endswith("展示次数"):
        return True
    return False


def extract_advertiser(texts: list[str]) -> str:
    sponsored_indexes = [index for index, value in enumerate(texts) if value in {"赞助内容", "Sponsored"}]
    if not sponsored_indexes:
        return ""
    before_sponsored = texts[: sponsored_indexes[0]]
    for value in reversed(before_sponsored):
        if not is_noise_text(value):
            return value
    return ""


def is_video_control_text(value: str) -> bool:
    stripped = value.strip()
    if stripped in {"/", "画质", "hd", "sd", "HD", "SD"}:
        return True
    if re.match(r"^\d{1,2}:\d{2}$", stripped):
        return True
    if "画质" in stripped and re.search(r"\b(?:hd|sd)\b", stripped, re.I):
        return True
    if re.search(r"\d{1,2}:\d{2}\s*/\s*\d{1,2}:\d{2}", stripped):
        return True
    return False


def extract_copy_title_and_description(texts: list[str]) -> tuple[str, str, str]:
    sponsored_index = next((index for index, value in enumerate(texts) if value in {"赞助内容", "Sponsored"}), -1)
    if sponsored_index < 0:
        return "", "", ""

    after_sponsored = [
        value
        for value in texts[sponsored_index + 1 :]
        if value and not is_noise_text(value) and not is_video_control_text(value)
    ]
    domain_index = next((index for index, value in enumerate(after_sponsored) if is_domain_text(value)), len(after_sponsored))

    copy_parts = [value for value in after_sponsored[:domain_index] if not is_cta_text(value)]
    ad_copy = "\n".join(copy_parts).strip()

    preview_parts = [value for value in after_sponsored[domain_index + 1 :] if not is_domain_text(value) and not is_cta_text(value)]
    ad_title = preview_parts[0].strip() if preview_parts else ""
    ad_description = preview_parts[1].strip() if len(preview_parts) > 1 else ""
    return ad_copy, ad_title, ad_description


def extract_copy_and_title(texts: list[str]) -> tuple[str, str]:
    ad_copy, ad_title, _ = extract_copy_title_and_description(texts)
    return ad_copy, ad_title


def extract_preview_description(texts: list[str]) -> str:
    _, _, ad_description = extract_copy_title_and_description(texts)
    return ad_description


def extract_images(node: Node) -> tuple[str, str]:
    image_urls = unique_preserve_order([image["src"] or "" for image in node.images()])
    avatar = ""
    ad_image = ""
    for url in image_urls:
        if re.search(r"[?&]stp=[^&]*(?:s60x60|s64x64|cp0_dst-jpg)", url) or "s60x60" in url:
            avatar = url
            break
    if not avatar and image_urls:
        avatar = image_urls[0]

    for url in image_urls:
        if url != avatar:
            ad_image = url
            if re.search(r"s\d{3,4}x\d{3,4}|_n\.(?:jpg|png|webp)", url, re.I):
                break
    return avatar, ad_image


def decode_facebook_video_efg(url: str) -> str:
    decoded_url = unescape(url)
    parsed = urlparse(decoded_url)
    efg = parse_qs(parsed.query).get("efg", [""])[0]
    if not efg:
        return ""
    try:
        value = unquote(efg)
        value += "=" * ((4 - len(value) % 4) % 4)
        return base64.urlsafe_b64decode(value).decode("utf-8", errors="ignore")
    except Exception:
        return ""


def video_quality_from_url(url: str) -> str:
    decoded_url = unescape(url)
    efg = decode_facebook_video_efg(decoded_url)
    searchable = f"{decoded_url} {efg}"
    if HD_VIDEO_RE.search(searchable):
        return "hd"
    if SD_VIDEO_RE.search(searchable):
        return "sd"
    return ""


def is_hd_video_url(url: str) -> bool:
    return video_quality_from_url(url) == "hd"


def extract_video(node: Node) -> tuple[str, str, str]:
    videos = node.videos()
    video_urls = unique_preserve_order([video["src"] or "" for video in videos])
    if not video_urls:
        return "", "", ""

    selected_url = next((url for url in video_urls if video_quality_from_url(url) == "hd"), video_urls[0])
    quality = video_quality_from_url(selected_url)
    poster = ""
    for video in videos:
        if video.get("src") == selected_url and video.get("poster"):
            poster = video["poster"] or ""
            break
    if not poster:
        poster = next((video.get("poster") or "" for video in videos if video.get("poster")), "")
    return selected_url, poster, quality


def video_quality_from_card_html(html: str) -> str:
    video_url, _, quality = extract_video(parse_html(html))
    if quality:
        return quality
    return video_quality_from_url(video_url) if video_url else ""


def extract_grouped_ad_count(texts: list[str]) -> int:
    for value in texts:
        match = GROUPED_AD_COUNT_RE.search(value)
        if match:
            return max(1, int(match.group(1)))
    return 1


def extract_start_date(texts: list[str]) -> str:
    for value in texts:
        match = START_DATE_VALUE_RE.search(value)
        if match:
            return match.group(1).strip()
    for value in texts:
        if START_DATE_RE.search(value):
            return value.strip()
    return ""


def extract_card(node: Node) -> dict[str, str]:
    texts = node.texts()
    ad_copy, ad_title, ad_description = extract_copy_title_and_description(texts)
    avatar, ad_image = extract_images(node)
    ad_video, video_poster, video_quality = extract_video(node)
    card = {
        "投放者": extract_advertiser(texts),
        "资料库编号": extract_library_id(node.text_content()) or "",
        "广告投放时间": extract_start_date(texts),
        "投放者头像": avatar,
        "广告标题": ad_title,
        "广告描述": ad_description,
        "广告文案": ad_copy,
    }
    if ad_video:
        card["广告视频"] = ad_video
        card["广告视频封面"] = video_poster
        card["视频清晰度"] = video_quality
    else:
        card["广告图片"] = ad_image
    return card


def extract_cards_from_html(
    html: str,
    *,
    max_cards: int | None = None,
    expand_grouped_ads: bool = True,
) -> list[dict[str, str]]:
    root = parse_html(html)
    card_nodes = select_card_nodes(root)
    cards: list[dict[str, str]] = []
    for node in card_nodes:
        card = extract_card(node)
        repeat_count = extract_grouped_ad_count(node.texts()) if expand_grouped_ads else 1
        cards.extend(card.copy() for _ in range(repeat_count))
    cards = [card for card in cards if any(card.values())]
    return cards[:max_cards] if max_cards else cards


def extract_result_count(html: str) -> int | None:
    text = parse_html(html).text_content()
    match = RESULT_COUNT_RE.search(text)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def safe_filename(value: str, *, fallback: str = "未命名") -> str:
    cleaned = clean_text(value)
    cleaned = re.sub(r"[\\/:*?\"<>|]+", "_", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ._")
    return cleaned[:120] or fallback


def image_extension_from_url(url: str, default: str = ".jpg") -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov", ".m4v", ".webm"}:
        return suffix
    return default


def download_image(url: str, output_path: Path, *, timeout: int = 30, force: bool = False) -> bool:
    if not url:
        return False
    if not force and output_path.exists() and output_path.stat().st_size > 0:
        return True
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            ),
            "Referer": "https://www.facebook.com/ads/library/",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        output_path.write_bytes(response.read())
    return True


def folder_name_for_card(card: dict[str, str]) -> str:
    parts = [
        safe_filename(card.get("投放者", ""), fallback="未知投放者"),
        safe_filename(card.get("广告投放时间", ""), fallback="未知投放时间"),
        safe_filename(card.get("资料库编号", ""), fallback="未知资料库编号"),
    ]
    return "+".join(parts)


def media_type_for_card(card: dict[str, str]) -> str:
    return "视频" if card.get("广告视频") else "图片"


def media_folder_for_card(card: dict[str, str], asset_dir: Path) -> Path:
    return asset_dir / media_type_for_card(card) / folder_name_for_card(card)


def markdown_media_path(card: dict[str, str], folder: Path) -> str:
    if card.get("广告视频"):
        local_video = card.get("广告视频本地文件", "")
        if local_video:
            local_path = Path(local_video)
            try:
                return local_path.relative_to(folder).as_posix()
            except ValueError:
                return local_path.as_posix()
        if card.get("广告视频下载错误"):
            return ""
        return card.get("广告视频", "")

    local_image = card.get("广告图片本地文件", "")
    if local_image:
        local_path = Path(local_image)
        try:
            return local_path.relative_to(folder).as_posix()
        except ValueError:
            return local_path.as_posix()
    return card.get("广告图片", "")


def write_card_markdown(card: dict[str, str], folder: Path) -> Path:
    library_id = card.get("资料库编号", "")
    title = card.get("广告标题", "")
    description = card.get("广告描述", "")
    copy = (card.get("广告文案", "") or "").replace("\\n", "\n")
    media_path = markdown_media_path(card, folder)
    is_video = bool(card.get("广告视频"))
    media_label = "广告视频" if is_video else "广告图片"
    media_line = f"[{media_label}]({media_path})" if is_video and media_path else ""
    if not is_video and media_path:
        media_line = f"![广告图片]({media_path})"
    markdown = f"""资料库编号：
{library_id}

广告标题：
{title}

广告描述：
{description}

文案：
{copy}

{media_label}：
{media_line}
"""
    output_path = folder / "素材信息.md"
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


def write_markdown_for_existing_asset_folders(asset_dir: Path) -> int:
    if not asset_dir.exists():
        raise FileNotFoundError(f"图片下载目录不存在: {asset_dir}")
    if not asset_dir.is_dir():
        raise NotADirectoryError(f"不是目录: {asset_dir}")

    count = 0
    for metadata_path in sorted(asset_dir.rglob("素材信息.json")):
        folder = metadata_path.parent
        metadata_path = folder / "素材信息.json"
        try:
            card = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            print(f"跳过，素材信息.json 格式错误: {metadata_path} ({error})", file=sys.stderr)
            continue

        local_video = next((candidate for candidate in sorted(folder.glob("广告视频.*")) if candidate.is_file()), None)
        if local_video:
            card["广告视频本地文件"] = str(local_video)
        local_image = next((candidate for candidate in sorted(folder.glob("广告图片.*")) if candidate.is_file()), None)
        if local_image:
            card["广告图片本地文件"] = str(local_image)

        markdown_path = write_card_markdown(card, folder)
        card["素材Markdown文件"] = str(markdown_path)
        metadata_path.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
        count += 1
        print(f"已生成 Markdown: {markdown_path}", file=sys.stderr)
    return count


def download_card_images(cards: list[dict[str, str]], asset_dir: Path, *, require_hd_video: bool = False) -> None:
    asset_dir.mkdir(parents=True, exist_ok=True)
    for index, card in enumerate(cards, start=1):
        folder = media_folder_for_card(card, asset_dir)
        folder.mkdir(parents=True, exist_ok=True)
        card["素材文件夹"] = str(folder)

        media_fields = [("投放者头像", "投放者头像", ".jpg")]
        if card.get("广告视频"):
            if require_hd_video and video_quality_from_url(card.get("广告视频", "")) != "hd":
                card["广告视频下载错误"] = "未获取到 HD/720p 视频地址，已跳过下载，避免保存低清视频。"
            else:
                media_fields.append(("广告视频", "广告视频", ".mp4"))
            if card.get("广告视频封面"):
                media_fields.append(("广告视频封面", "广告视频封面", ".jpg"))
        else:
            media_fields.append(("广告图片", "广告图片", ".jpg"))

        for field_name, file_stem, default_ext in media_fields:
            url = card.get(field_name, "")
            if not url:
                continue
            output_path = folder / f"{file_stem}{image_extension_from_url(url, default=default_ext)}"
            local_field = f"{field_name}本地文件"
            try:
                download_image(url, output_path, force=require_hd_video and field_name == "广告视频")
                card[local_field] = str(output_path)
            except (OSError, URLError, TimeoutError) as error:
                card[local_field] = ""
                card[f"{field_name}下载错误"] = str(error)

        markdown_path = write_card_markdown(card, folder)
        card["素材Markdown文件"] = str(markdown_path)
        metadata_path = folder / "素材信息.json"
        metadata_path.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[{index}/{len(cards)}] 已处理素材文件夹: {folder}", file=sys.stderr)


def write_result_count_folder(cards: list[dict[str, str]], root_dir: Path) -> Path:
    folder = root_dir / f"本次返回{len(cards)}个结果"
    folder.mkdir(parents=True, exist_ok=True)
    output_path = folder / "广告素材.json"
    output_path.write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8")
    return folder


def import_playwright() -> Any:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise RuntimeError("缺少依赖 playwright，请先运行: pip install playwright && python -m playwright install chromium") from error
    return sync_playwright, PlaywrightTimeoutError


def select_visible_hd_video_options(page: Any) -> int:
    clicked = 0

    def sync_current_video_sources() -> None:
        page.evaluate(
            r"""
            () => {
                for (const video of document.querySelectorAll('video')) {
                    const currentSrc = video.currentSrc || video.src || video.getAttribute('src') || '';
                    if (currentSrc && !currentSrc.startsWith('blob:')) {
                        video.setAttribute('src', currentSrc);
                        video.setAttribute('data-current-src', currentSrc);
                    }
                    if (video.poster) video.setAttribute('poster', video.poster);
                }
            }
            """
        )

    def visible_video_indexes() -> list[int]:
        indexes = page.evaluate(
            r"""
            () => [...document.querySelectorAll('video')]
                .map((video, index) => {
                    const rect = video.getBoundingClientRect();
                    const style = getComputedStyle(video);
                    const visible = rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden'
                        && rect.bottom > 0 && rect.top < window.innerHeight;
                    return { index, top: rect.top, visible };
                })
                .filter(item => item.visible)
                .sort((a, b) => a.top - b.top)
                .map(item => item.index)
                .slice(0, 12)
            """
        )
        return [int(index) for index in (indexes or [])]

    def video_src(index: int) -> str:
        return str(
            page.evaluate(
                "index => { const video = document.querySelectorAll('video')[index]; return video ? (video.currentSrc || video.src || video.getAttribute('src') || '') : ''; }",
                index,
            )
            or ""
        )

    def prepare_video(index: int) -> None:
        page.evaluate(
            r"""
            index => {
                const video = document.querySelectorAll('video')[index];
                if (!video) return;
                video.scrollIntoView({ block: 'center', inline: 'center' });
                video.muted = true;
                video.playsInline = true;
                const rect = video.getBoundingClientRect();
                const eventInit = { bubbles: true, cancelable: true, clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2, view: window };
                for (const type of ['pointerover', 'mouseover', 'pointermove', 'mousemove', 'mouseenter']) {
                    video.dispatchEvent(new MouseEvent(type, eventInit));
                }
                const container = video.closest('[data-testid="ad-content-body-video-container"], [role="group"], div') || video.parentElement;
                if (container) {
                    for (const type of ['pointerover', 'mouseover', 'pointermove', 'mousemove', 'mouseenter']) {
                        container.dispatchEvent(new MouseEvent(type, eventInit));
                    }
                    const playButton = [...container.querySelectorAll('[role="button"], button')].find(element => {
                        const label = (element.getAttribute('aria-label') || element.innerText || element.textContent || '').toLowerCase();
                        return /播放|play/.test(label);
                    });
                    if (playButton) playButton.click();
                }
                video.play?.().catch(() => {});
            }
            """,
            index,
        )

    def click_video_control(index: int, kind: str) -> int:
        return int(
            page.evaluate(
                r"""
                ([index, kind]) => {
                    const clean = value => (value || '').replace(/\s+/g, ' ').trim().toLowerCase();
                    const isVisible = element => {
                        const rect = element.getBoundingClientRect();
                        const style = getComputedStyle(element);
                        return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden'
                            && rect.bottom > 0 && rect.top < window.innerHeight;
                    };
                    const fireClick = element => {
                        const rect = element.getBoundingClientRect();
                        const clientX = rect.left + rect.width / 2;
                        const clientY = rect.top + rect.height / 2;
                        for (const type of ['pointerover', 'mouseover', 'pointermove', 'mousemove', 'pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
                            element.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, clientX, clientY, view: window }));
                        }
                    };
                    const video = document.querySelectorAll('video')[index];
                    if (!video) return 0;
                    const videoRect = video.getBoundingClientRect();
                    const videoCenterX = videoRect.left + videoRect.width / 2;
                    const videoCenterY = videoRect.top + videoRect.height / 2;
                    const distanceToVideo = rect => Math.hypot(rect.left + rect.width / 2 - videoCenterX, rect.top + rect.height / 2 - videoCenterY);
                    let candidates = [...document.querySelectorAll('[role="button"], button, [role="menuitem"], [role="option"], div, span')]
                        .map(element => {
                            const rect = element.getBoundingClientRect();
                            return {
                                element,
                                text: clean(element.innerText || element.textContent || ''),
                                aria: clean(element.getAttribute('aria-label') || ''),
                                role: element.getAttribute('role') || '',
                                width: rect.width,
                                height: rect.height,
                                area: rect.width * rect.height,
                                distance: distanceToVideo(rect),
                            };
                        })
                        .filter(item => isVisible(item.element));
                    if (kind === 'settings') {
                        candidates = candidates
                            .filter(item => item.aria.includes('设置') || item.aria.includes('settings') || item.aria.includes('quality') || item.aria.includes('清晰'))
                            .sort((a, b) => a.distance - b.distance || b.area - a.area);
                    } else if (kind === 'quality') {
                        candidates = candidates
                            .filter(item => /(画质|清晰度|quality)/i.test(`${item.text} ${item.aria}`)
                                && item.width >= 40 && item.width <= 360 && item.height >= 10 && item.height <= 100)
                            .sort((a, b) => (b.role === 'button') - (a.role === 'button') || a.distance - b.distance || b.area - a.area);
                    } else if (kind === 'hd') {
                        candidates = candidates
                            .filter(item => item.text === 'hd' || item.aria === 'hd')
                            .sort((a, b) => (b.role === 'button') - (a.role === 'button') || a.distance - b.distance || b.area - a.area);
                    }
                    if (!candidates.length) return 0;
                    fireClick(candidates[0].element);
                    return 1;
                }
                """,
                [index, kind],
            )
            or 0
        )

    def wait_for_video_hd(index: int) -> None:
        try:
            page.wait_for_function(
                r"""
                index => {
                    const video = document.querySelectorAll('video')[index];
                    if (!video) return false;
                    const currentSrc = video.currentSrc || video.src || video.getAttribute('src') || '';
                    const decodeEfg = src => {
                        try {
                            const url = new URL(src, window.location.href);
                            let efg = url.searchParams.get('efg') || '';
                            if (!efg) return '';
                            efg = decodeURIComponent(efg).replace(/-/g, '+').replace(/_/g, '/');
                            efg += '='.repeat((4 - efg.length % 4) % 4);
                            return atob(efg).toLowerCase();
                        } catch (_) {
                            return '';
                        }
                    };
                    const searchable = `${currentSrc} ${decodeEfg(currentSrc)}`.toLowerCase();
                    return /(720|dash_h264|sve_hd|progressive_hd|\bhd\b)/.test(searchable);
                }
                """,
                index,
                timeout=6_000,
            )
        except Exception:
            pass

    indexes = visible_video_indexes()
    if not indexes:
        indexes = list(range(min(page.locator('video').count(), 6)))

    for index in indexes:
        try:
            before_src = video_src(index)
            if before_src and video_quality_from_url(before_src) == 'hd':
                sync_current_video_sources()
                continue
            prepare_video(index)
            page.wait_for_timeout(800)
            if not click_video_control(index, 'settings'):
                continue
            page.wait_for_timeout(900)
            if not click_video_control(index, 'quality'):
                continue
            page.wait_for_timeout(900)
            if click_video_control(index, 'hd'):
                clicked += 1
            wait_for_video_hd(index)
            sync_current_video_sources()
            page.wait_for_timeout(300)
        except Exception:
            continue

    sync_current_video_sources()
    return clicked


def crawl_html(
    url: str,
    *,
    headless: bool,
    timeout: int,
    wait_ms: int,
    scroll_rounds: int,
    stop_after_stable_rounds: int,
    storage_state: Path | None,
    select_hd_video: bool = False,
    on_card_html: Callable[[str, str, int, bool], None] | None = None,
) -> str:
    sync_playwright, PlaywrightTimeoutError = import_playwright()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context_options: dict[str, Any] = {"viewport": {"width": 1440, "height": 1200}}
        if storage_state:
            context_options["storage_state"] = str(storage_state)
        context = browser.new_context(**context_options)
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            page.wait_for_timeout(wait_ms)
            if select_hd_video:
                select_visible_hd_video_options(page)
                page.wait_for_timeout(500)
            stable_rounds = 0
            seen_library_ids: set[str] = set()
            card_html_by_id: dict[str, str] = {}

            def collect_visible_cards() -> int:
                def read_visible_cards() -> list[dict[str, str]]:
                    return page.evaluate(
                        r"""
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
                            .map(item => ({ library_id: item.libraryId, html: item.element.outerHTML }));
                    }
                    """
                    ) or []

                visible_cards = read_visible_cards()
                if select_hd_video:
                    sd_cards = [card for card in visible_cards if video_quality_from_card_html(str(card.get("html") or "")) == "sd"]
                    if sd_cards:
                        print(
                            f"[HD重试] 当前可见 {len(sd_cards)} 条视频仍是 SD，先尝试切换到 HD 再保存。",
                            flush=True,
                        )
                        select_visible_hd_video_options(page)
                        page.wait_for_timeout(1_000)
                        visible_cards = read_visible_cards()
                new_count = 0
                for card in visible_cards or []:
                    library_id = str(card.get("library_id") or "")
                    html = str(card.get("html") or "")
                    if not library_id or not html:
                        continue
                    if library_id not in seen_library_ids:
                        new_count += 1
                    seen_library_ids.add(library_id)
                    previous = card_html_by_id.get(library_id)
                    previous_quality = video_quality_from_card_html(previous) if previous else ""
                    current_quality = video_quality_from_card_html(html)
                    should_replace = previous is None
                    if previous is not None:
                        should_replace = (
                            (previous_quality != "hd" and current_quality == "hd")
                            or (previous_quality == current_quality and html.count("<img") > previous.count("<img"))
                            or (previous_quality == current_quality and len(html) < len(previous))
                        )
                    if should_replace:
                        card_html_by_id[library_id] = html
                        if on_card_html:
                            on_card_html(library_id, html, len(seen_library_ids), previous is not None)
                return new_count

            collect_visible_cards()
            for round_index in range(1, scroll_rounds + 1):
                page.mouse.wheel(0, 2500)
                page.wait_for_timeout(wait_ms)
                if select_hd_video:
                    select_visible_hd_video_options(page)
                    page.wait_for_timeout(500)
                new_cards = collect_visible_cards()
                print(
                    f"[滚动进度] {round_index}/{scroll_rounds} | 本轮新增: {new_cards} | "
                    f"累计唯一卡片: {len(seen_library_ids)} | 连续无新增: {stable_rounds}",
                    flush=True,
                )
                if new_cards == 0:
                    stable_rounds += 1
                    if stable_rounds >= stop_after_stable_rounds:
                        break
                else:
                    stable_rounds = 0
            if card_html_by_id:
                page_text = page.evaluate("document.body.innerText || document.body.textContent || ''")
                return f"<pre data-meta-page-text='1'>{escape(page_text)}</pre>\n" + "\n".join(
                    card_html_by_id.values()
                )
            return page.content()
        except PlaywrightTimeoutError as error:
            raise RuntimeError(f"页面加载超时: {error}") from error
        finally:
            browser.close()


def build_default_output_path() -> Path:
    return DEFAULT_OUTPUT_PATH


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="抓取/解析 Meta 广告资料库卡片元素，并保存为指定 JSON 字段。")
    parser.add_argument("--url", default=DEFAULT_URL, help="Meta Ad Library URL，默认是 tryfortis / US / active。")
    parser.add_argument(
        "--monthly-grouped",
        action="store_true",
        help="使用 Facebook 的 relevancy_monthly_grouped 分组排序；不传时默认不分组，通常能拿到更多独立广告卡片。",
    )
    parser.add_argument(
        "--require-full-results",
        action="store_true",
        help="如果 DOM 可采集数量小于页面显示的约 N 条结果，则返回错误并提示需要分页接口/登录态。",
    )
    parser.add_argument("--crawl", action="store_true", help="打开 URL 重新抓取；不传时直接解析 --input-html。")
    parser.add_argument("--input-html", type=Path, default=DEFAULT_INPUT_HTML, help="本地 HTML/MD 文件，默认 meta素材/样式.md。")
    parser.add_argument("--save-html", type=Path, default=DEFAULT_CAPTURE_HTML, help="--crawl 时保存抓取 HTML 的路径。")
    parser.add_argument("--output", type=Path, default=build_default_output_path(), help="输出 JSON 路径，默认 meta素材/广告素材.json。")
    parser.add_argument("--asset-dir", type=Path, default=DEFAULT_ASSET_DIR, help="素材下载目录，默认 meta素材/广告素材文件；内部会分成 图片/视频。")
    parser.add_argument("--generate-markdown-only", action="store_true", help="只为 --asset-dir 下已有素材文件夹批量生成素材信息.md，不重新解析/爬取。")
    parser.add_argument("--result-count-root", type=Path, default=DEFAULT_RESULT_COUNT_ROOT, help="按本次返回数量创建汇总文件夹的根目录，默认 meta素材。")
    parser.add_argument("--no-result-count-folder", action="store_true", help="不创建“本次返回N个结果”的汇总文件夹。")
    parser.add_argument("--download-images", action="store_true", help="下载投放者头像和广告图片，并为每条素材建立文件夹。")
    parser.add_argument("--require-hd-video", action="store_true", help="下载视频时只保存 HD/720p 地址；未切到高清的视频会跳过下载并在 JSON 中标记错误。")
    parser.add_argument("--max-cards", type=int, help="最多保存多少张卡片，默认不限。")
    parser.add_argument(
        "--no-expand-grouped-ads",
        action="store_true",
        help="不要展开“2条广告/3条广告使用这个创意和文字”的分组；默认会按广告条数展开。",
    )
    parser.add_argument("--headless", action="store_true", help="--crawl 时使用无头浏览器；默认打开可见浏览器。")
    parser.add_argument("--show", action="store_true", help="兼容参数：--crawl 时打开可见浏览器。")
    parser.add_argument("--timeout", type=int, default=60_000, help="页面加载超时时间，毫秒。")
    parser.add_argument("--wait-ms", type=int, default=2_500, help="每次滚动后的等待时间，毫秒。")
    parser.add_argument("--scroll-rounds", type=int, default=120, help="最多滚动次数。")
    parser.add_argument("--stop-after-stable-rounds", type=int, default=8, help="连续多少轮没有新卡片后停止。")
    parser.add_argument("--storage-state", type=Path, help="Playwright 登录态 JSON，用于复用 Facebook 登录状态。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.generate_markdown_only:
            count = write_markdown_for_existing_asset_folders(args.asset_dir)
            print(f"素材目录: {args.asset_dir}")
            print(f"生成 Markdown 文件夹数量: {count}")
            return 0

        realtime_cards_by_id: dict[str, dict[str, str]] = {}
        realtime_seen_count = 0

        def handle_realtime_card(library_id: str, card_html: str, seen_count: int, replaced: bool) -> None:
            nonlocal realtime_seen_count
            if args.max_cards and library_id not in realtime_cards_by_id and len(realtime_cards_by_id) >= args.max_cards:
                return
            card = extract_card(parse_html(card_html))
            if not any(card.values()):
                return
            realtime_seen_count = max(realtime_seen_count, seen_count)
            status = "更新" if replaced else "新增"
            quality = card.get("视频清晰度", "") or "图片"
            print(
                f"[实时{status}] 已发现 {realtime_seen_count} 条 | 资料库编号: {library_id} | "
                f"投放者: {card.get('投放者', '')} | 类型/清晰度: {quality}",
                flush=True,
            )
            waiting_for_hd = bool(args.require_hd_video and card.get("广告视频") and card.get("视频清晰度") != "hd")
            if waiting_for_hd:
                print(
                    f"[等待HD] {library_id} 当前还是 {card.get('视频清晰度') or '未知清晰度'}，暂不下载；后续检测到 HD 会自动保存。",
                    flush=True,
                )
            if args.download_images:
                if not waiting_for_hd:
                    download_card_images([card], args.asset_dir, require_hd_video=args.require_hd_video)
                    folder = card.get("素材文件夹", "")
                    video_file = card.get("广告视频本地文件", "")
                    if video_file and Path(video_file).exists():
                        size_mb = Path(video_file).stat().st_size / 1024 / 1024
                        print(f"[实时保存] {library_id} | 视频大小: {size_mb:.2f}MB | 文件夹: {folder}", flush=True)
                    else:
                        print(f"[实时保存] {library_id} | 文件夹: {folder}", flush=True)
            realtime_cards_by_id[library_id] = card
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(list(realtime_cards_by_id.values()), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"[实时JSON] 当前已写入 {len(realtime_cards_by_id)} 条: {args.output}", flush=True)

        if args.crawl:
            if args.monthly_grouped and "sort_data[mode]" not in args.url:
                separator = "&" if "?" in args.url else "?"
                args.url = f"{args.url}{separator}sort_data[mode]=relevancy_monthly_grouped&sort_data[direction]=desc"
            print("开始实时抓取：发现一条就会立即创建文件夹/保存素材。", flush=True)
            html = crawl_html(
                args.url,
                headless=args.headless and not args.show,
                timeout=args.timeout,
                wait_ms=args.wait_ms,
                scroll_rounds=args.scroll_rounds,
                stop_after_stable_rounds=args.stop_after_stable_rounds,
                storage_state=args.storage_state,
                select_hd_video=args.require_hd_video,
                on_card_html=handle_realtime_card,
            )
            args.save_html.parent.mkdir(parents=True, exist_ok=True)
            args.save_html.write_text(html, encoding="utf-8")
            source = str(args.url)
        else:
            if not args.input_html.exists():
                raise RuntimeError(f"输入文件不存在: {args.input_html}")
            html = args.input_html.read_text(encoding="utf-8")
            source = str(args.input_html)

        cards = extract_cards_from_html(
            html,
            max_cards=args.max_cards,
            expand_grouped_ads=not args.no_expand_grouped_ads,
        )
        if realtime_cards_by_id:
            cards = list(realtime_cards_by_id.values())
            if args.max_cards:
                cards = cards[: args.max_cards]
            if args.require_hd_video:
                cards = [
                    card
                    for card in cards
                    if not card.get("广告视频") or card.get("视频清晰度") == "hd" or card.get("广告视频本地文件")
                ]
        result_count = extract_result_count(html)
        if args.require_full_results and result_count and len(cards) < result_count:
            raise RuntimeError(
                f"页面显示约 {result_count} 条结果，但 DOM 只渲染/可采集到 {len(cards)} 条。"
                "Facebook 当前页面没有把全部结果放进 HTML；需要登录态 + GraphQL 分页或官方 Ad Library API 才能全量获取。"
            )
        if args.download_images and not realtime_cards_by_id:
            download_card_images(cards, args.asset_dir, require_hd_video=args.require_hd_video)
        result_count_folder = None
        if not args.no_result_count_folder:
            result_count_folder = write_result_count_folder(cards, args.result_count_root)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"来源: {source}")
        print(f"卡片数量: {len(cards)}")
        if result_count:
            print(f"页面显示结果数: 约 {result_count}")
        print(f"输出: {args.output}")
        if result_count_folder:
            print(f"本次结果文件夹: {result_count_folder}")
        if args.download_images:
            print(f"素材目录: {args.asset_dir}")
        return 0
    except Exception as error:
        print(f"错误: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
