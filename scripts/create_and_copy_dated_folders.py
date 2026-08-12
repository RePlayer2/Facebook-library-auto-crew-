#!/usr/bin/env python3
"""创建日期编号文件夹，并按广告素材 JSON 顺序复制对应素材文件夹。"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Any

DEFAULT_JSON = Path("/Users/zzh/C/similar_craw/meta素材/鼻贴/HD单卡测试729/广告素材.json")
DEFAULT_TARGET = Path("/Users/zzh/C/similar_craw/meta素材/鼻贴/HD单卡测试729/整理")


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
    return ids


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


def cards_by_library_id(cards: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for card in cards:
        library_id = str(card.get("资料库编号") or "").strip()
        if library_id and library_id not in mapped:
            mapped[library_id] = card
    return mapped


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


def parse_folder_name(name: str) -> tuple[int, int] | None:
    match = re.match(r"^(\d+)\.(\d+)$", name)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


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

    media_roots = [source_root]
    library_output_dir = source_root / library_id
    if library_output_dir.exists() and library_output_dir.is_dir():
        media_roots.extend([library_output_dir, library_output_dir / "广告素材文件"])

    for root in media_roots:
        for media_dir_name in ("视频", "图片"):
            media_dir = root / media_dir_name
            if not media_dir.exists() or not media_dir.is_dir():
                continue
            matches = sorted(child for child in media_dir.iterdir() if child.is_dir() and library_id in child.name)
            if matches:
                return matches[0]

    nested_matches = sorted(
        child
        for child in source_root.glob(f"*/广告素材文件/*/*{library_id}*")
        if child.is_dir() and child.parent.name in {"视频", "图片"}
    )
    if nested_matches:
        return nested_matches[0]
    return None


def create_and_copy_cards_to_dated_folders(
    json_path: Path | None,
    target_dir: Path,
    source_root: Path | None,
    *,
    prefix: str | None = None,
    count: int | None = None,
    ids: list[str] | None = None,
    start_index: int | None = None,
    overwrite: bool = False,
    dry_run: bool = False,
) -> tuple[list[tuple[str, Path, Path]], list[tuple[str, str]]]:
    if ids:
        cards: list[dict[str, Any]] = [{"资料库编号": library_id} for library_id in ids]
        if json_path and json_path.exists():
            cards_index = cards_by_library_id(load_cards(json_path))
            cards = [cards_index.get(library_id, card) for library_id, card in zip(ids, cards)]
    else:
        if json_path is None:
            json_path = DEFAULT_JSON
        cards = load_cards(json_path)

    if ids:
        ordered_cards: list[dict[str, Any]] = []
        for library_id in ids:
            card = next((item for item in cards if str(item.get("资料库编号") or "").strip() == library_id), None)
            if card is None:
                ordered_cards.append({"资料库编号": library_id})
            else:
                ordered_cards.append(card)
        cards = ordered_cards
    elif count is not None:
        if count <= 0:
            raise ValueError("创建数量必须大于 0")
        cards = cards[:count]

    target_dir = target_dir.expanduser().resolve()
    if source_root is None:
        if json_path is not None and json_path.exists():
            source_root = infer_source_root(json_path, cards)
        else:
            source_root = target_dir.parent
    source_root = source_root.expanduser().resolve()
    prefix = prefix or today_prefix()

    if not source_root.exists():
        raise FileNotFoundError(f"源素材根目录不存在: {source_root}")
    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)

    used_indexes = set() if overwrite else existing_indexes(target_dir, prefix)
    start = start_index if start_index is not None else 1

    copied: list[tuple[str, Path, Path]] = []
    skipped: list[tuple[str, str]] = []

    for offset, card in enumerate(cards, start=0):
        library_id = str(card.get("资料库编号") or "").strip()
        target_index = next_available_index(used_indexes, start)
        target_folder = target_dir / f"{prefix}.{target_index}"
        source_folder = find_source_folder(library_id, source_root, card) if library_id else None

        if target_folder.exists():
            if overwrite and not dry_run:
                shutil.rmtree(target_folder)
            elif not overwrite:
                skipped.append((library_id or f"#{offset + 1}", f"目标文件夹已存在: {target_folder}"))
                continue

        print(f"[{target_index}] {library_id or '无编号'}")
        print(f"  目标: {target_folder}")

        if source_folder is None:
            skipped.append((library_id or f"#{offset + 1}", "找不到对应的源素材文件夹"))
            continue

        print(f"  源: {source_folder}")
        if not dry_run:
            target_folder.mkdir(parents=True, exist_ok=True)
        if not dry_run:
            for item in source_folder.iterdir():
                destination = target_folder / item.name
                if item.is_dir():
                    shutil.copytree(item, destination, dirs_exist_ok=overwrite)
                else:
                    shutil.copy2(item, destination)
        copied.append((library_id, source_folder, target_folder))

    return copied, skipped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="创建日期编号文件夹，并按广告素材 JSON 顺序复制对应素材文件夹。")
    parser.add_argument("ids", nargs="*", help="资料库编号，按输入顺序处理；不传则按 JSON 顺序。")
    parser.add_argument("--ids-file", type=Path, help="资料库编号文件，一行一个或用逗号/空格分隔。")
    parser.add_argument("--json", type=Path, default=None, help="广告素材.json 路径；传入资料库编号时可不填。")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET, help="输出整理目录。")
    parser.add_argument("--source-root", type=Path, help="源素材根目录；不传则根据 JSON 自动推断。")
    parser.add_argument("--prefix", help="编号前缀；不传则使用当天日期，如 7月29日 -> 729。")
    parser.add_argument("--count", type=int, help="只处理前 N 条 JSON 记录，同时用于控制创建多少个日期文件夹。")
    parser.add_argument("--start-index", type=int, help="起始序号；不传则从 1 开始。")
    parser.add_argument("--overwrite", action="store_true", help="如果目标编号文件夹已存在，先删除再复制。")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要复制的内容，不实际复制。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        ids = normalize_ids(args.ids, args.ids_file)
        json_path = args.json.expanduser().resolve() if args.json else None
        copied, skipped = create_and_copy_cards_to_dated_folders(
            json_path,
            args.target,
            args.source_root,
            prefix=args.prefix,
            count=args.count,
            ids=ids or None,
            start_index=args.start_index,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
        )
        print()
        print(f"完成：复制 {len(copied)} 个，跳过 {len(skipped)} 个")
        if skipped:
            print("跳过明细:")
            for library_id, reason in skipped:
                print(f"  {library_id}: {reason}")
        return 0
    except Exception as error:
        print(f"错误: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
