#!/usr/bin/env python3
"""将整理目录中的广告图片平铺导出，并按所在文件夹编号重命名。"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import date
from pathlib import Path


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


def today_prefix() -> str:
    today = date.today()
    return f"{today.month}{today.day}"


def parse_numbered_folder(name: str) -> tuple[str, int] | None:
    match = re.fullmatch(r"(\d+)\.(\d+)", name)
    if not match:
        return None
    return match.group(1), int(match.group(2))


def find_ad_images(folder: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in folder.iterdir()
            if path.is_file()
            and path.suffix.lower() in IMAGE_SUFFIXES
            and path.stem.startswith("广告图片")
        ),
        key=lambda path: path.name,
    )


def export_image_materials(
    input_dir: Path,
    output_dir: Path | None = None,
    *,
    prefix: str | None = None,
    overwrite: bool = True,
    dry_run: bool = False,
) -> tuple[list[tuple[Path, Path]], list[tuple[str, str]]]:
    input_dir = input_dir.expanduser().resolve()
    if not input_dir.exists() or not input_dir.is_dir():
        raise FileNotFoundError(f"整理目录不存在: {input_dir}")

    prefix = (prefix or today_prefix()).strip()
    if not re.fullmatch(r"\d+", prefix):
        raise ValueError(f"日期前缀必须是纯数字: {prefix}")

    if output_dir is None:
        output_dir = input_dir.parent / f"{prefix}图片素材"
    output_dir = output_dir.expanduser().resolve()

    numbered_folders: list[tuple[int, Path]] = []
    for folder in input_dir.iterdir():
        if not folder.is_dir():
            continue
        parsed = parse_numbered_folder(folder.name)
        if parsed and parsed[0] == prefix:
            numbered_folders.append((parsed[1], folder))
    numbered_folders.sort(key=lambda item: item[0])

    if not numbered_folders:
        raise ValueError(f"在 {input_dir} 中没有找到 {prefix}.x 格式的整理文件夹")

    copied: list[tuple[Path, Path]] = []
    skipped: list[tuple[str, str]] = []
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    for _, folder in numbered_folders:
        images = find_ad_images(folder)
        if not images:
            skipped.append((folder.name, "没有找到广告图片"))
            continue

        for image_index, source in enumerate(images, start=1):
            suffix = source.suffix.lower()
            numbered_suffix = "" if len(images) == 1 else f"-{image_index}"
            destination = output_dir / f"{folder.name}{numbered_suffix}{suffix}"
            if destination.exists() and not overwrite:
                skipped.append((folder.name, f"目标文件已存在: {destination.name}"))
                continue
            print(f"{source} -> {destination}")
            if not dry_run:
                shutil.copy2(source, destination)
            copied.append((source, destination))

    return copied, skipped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将整理目录中的广告图片导出到日期图片素材文件夹，并按整理文件夹编号重命名。"
    )
    parser.add_argument("--input", type=Path, required=True, help="整理目录，例如 /path/to/整理。")
    parser.add_argument("--output", type=Path, help="输出目录；默认为整理目录同级的 <日期>图片素材。")
    parser.add_argument("--prefix", help="整理文件夹的日期前缀；不传则使用当天日期，如 9 月 20 日为 920。")
    parser.add_argument("--no-overwrite", action="store_true", help="目标图片已存在时跳过，默认覆盖同名图片。")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要导出的图片，不写入文件。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        copied, skipped = export_image_materials(
            args.input,
            args.output,
            prefix=args.prefix,
            overwrite=not args.no_overwrite,
            dry_run=args.dry_run,
        )
        print()
        print(f"完成：导出 {len(copied)} 张，跳过 {len(skipped)} 项")
        if skipped:
            print("跳过明细:")
            for folder_name, reason in skipped:
                print(f"  {folder_name}: {reason}")
        return 0
    except Exception as error:
        print(f"错误: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
