#!/usr/bin/env python3
"""按广告素材 JSON 顺序，把素材文件夹复制成当天编号整理文件夹。

示例:
    python3 crawler/copy_ads_to_dated_folders.py \
      --json 'meta素材/鼻贴/HD前三条测试/广告素材.json' \
      --target 'meta素材/鼻贴/HD单卡测试729/整理'

脚本会按 JSON 中广告记录从上到下的顺序读取 `资料库编号`，在源素材目录的
`图片/视频` 子目录中查找文件夹名包含该资料库编号的素材文件夹，然后复制到
目标整理目录下的当天编号文件夹，例如 `729.1`, `729.2`, `729.3`。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Any

DEFAULT_JSON = Path("/Users/zzh/C/similar_craw/meta素材/鼻贴/HD前三条测试/广告素材.json")
DEFAULT_TARGET = Path("/Users/zzh/C/similar_craw/meta素材/鼻贴/HD单卡测试729/整理")


def today_prefix() -> str:
    today = date.today()
    return f"{today.month}{today.day}"


def load_cards(json_path: Path) -> list[dict[str, Any]]:
    if not json_path.exists():
        raise FileNotFoundError(f"JSON 文件不存在: {json_path}")
    data = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"JSON 顶层必须是列表: {json_path}")
    cards = [item for item in data if isinstance(item, dict)]
    if not cards:
        raise ValueError(f"JSON 中没有广告记录: {json_path}")
    return cards


def infer_source_root(json_path: Path, cards: list[dict[str, Any]]) -> Path:
    for card in cards:
        folder = card.get("素材文件夹")
        if folder:
            folder_path = Path(str(folder)).expanduser()
            if not folder_path.is_absolute():
                folder_path = (Path.cwd() / folder_path).resolve()
            parent = folder_path.parent
            if parent.name in {"图片", "视频"}:
                return parent.parent
    return json_path.parent


def existing_indexes(target_dir: Path, prefix: str) -> set[int]:
    indexes: set[int] = set()
    if not target_dir.exists():
        return indexes
    pattern = re.compile(rf"^{re.escape(prefix)}\.(\d+)$")
    for child in target_dir.iterdir():
        if not child.is_dir():
            continue
        match = pattern.match(child.name)
        if match:
            indexes.add(int(match.group(1)))
    return indexes


def next_available_index(used: set[int], start: int = 1) -> int:
    index = max(1, start)
    while index in used:
        index += 1
    used.add(index)
    return index


def find_source_folder(library_id: str, source_root: Path, card: dict[str, Any]) -> Path | None:
    material_folder = card.get("素材文件夹")
    if material_folder:
        folder_path = Path(str(material_folder)).expanduser()
        if not folder_path.is_absolute():
            folder_path = (Path.cwd() / folder_path).resolve()
        if folder_path.exists() and folder_path.is_dir() and library_id in folder_path.name:
            return folder_path

    for media_dir_name in ("视频", "图片"):
        media_dir = source_root / media_dir_name
        if not media_dir.exists() or not media_dir.is_dir():
            continue
        matches = sorted(child for child in media_dir.iterdir() if child.is_dir() and library_id in child.name)
        if matches:
            return matches[0]
    return None


def copy_cards_to_dated_folders(
    json_path: Path,
    target_dir: Path,
    source_root: Path | None,
    *,
    prefix: str | None = None,
    start_index: int | None = None,
    limit: int | None = None,
    overwrite: bool = False,
    dry_run: bool = False,
) -> tuple[list[tuple[str, Path, Path]], list[tuple[str, str]]]:
    cards = load_cards(json_path)
    if limit is not None:
        cards = cards[:limit]

    source_root = source_root or infer_source_root(json_path, cards)
    source_root = source_root.expanduser().resolve()
    target_dir = target_dir.expanduser().resolve()
    prefix = prefix or today_prefix()

    if not source_root.exists():
        raise FileNotFoundError(f"源素材根目录不存在: {source_root}")
    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)

    used_indexes = set() if overwrite else existing_indexes(target_dir, prefix)
    start = start_index if start_index is not None else 1
    copied: list[tuple[str, Path, Path]] = []
    skipped: list[tuple[str, str]] = []

    for card in cards:
        library_id = str(card.get("资料库编号") or "").strip()
        if not library_id:
            skipped.append(("", "缺少资料库编号"))
            continue

        source_folder = find_source_folder(library_id, source_root, card)
        if source_folder is None:
            skipped.append((library_id, f"找不到包含资料库编号的源文件夹: {library_id}"))
            continue

        target_index = next_available_index(used_indexes, start)
        target_folder = target_dir / f"{prefix}.{target_index}"

        if target_folder.exists():
            if not overwrite:
                skipped.append((library_id, f"目标文件夹已存在: {target_folder}"))
                continue
            if not dry_run:
                shutil.rmtree(target_folder)

        print(f"[{len(copied) + 1}] {library_id}")
        print(f"  源: {source_folder}")
        print(f"  目标: {target_folder}")

        if not dry_run:
            shutil.copytree(source_folder, target_folder)
        copied.append((library_id, source_folder, target_folder))

    return copied, skipped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按广告素材 JSON 顺序复制素材到当天编号整理文件夹。")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON, help="广告素材.json 路径。")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET, help="输出整理目录，例如 meta素材/鼻贴/HD单卡测试729/整理。")
    parser.add_argument("--source-root", type=Path, help="源素材根目录；不传则根据 JSON 的 素材文件夹 自动推断。")
    parser.add_argument("--prefix", help="编号前缀；不传则使用当天日期，如 7月29日 -> 729。")
    parser.add_argument("--start-index", type=int, help="起始序号；不传则从 1 开始并自动跳过已存在编号。")
    parser.add_argument("--limit", type=int, help="只处理前 N 条 JSON 记录。")
    parser.add_argument("--overwrite", action="store_true", help="如果目标编号文件夹已存在，先删除再复制。")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要复制的内容，不实际复制。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        copied, skipped = copy_cards_to_dated_folders(
            args.json.expanduser().resolve(),
            args.target,
            args.source_root,
            prefix=args.prefix,
            start_index=args.start_index,
            limit=args.limit,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
        )
        print()
        print(f"完成：复制 {len(copied)} 个，跳过 {len(skipped)} 个")
        if skipped:
            print("跳过明细:")
            for library_id, reason in skipped:
                print(f"  {library_id or '无编号'}: {reason}")
        return 0
    except Exception as error:
        print(f"错误: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
