#!/usr/bin/env python3
"""在指定目录下按当天日期创建一批编号文件夹。"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

DEFAULT_TARGET = Path("/Users/zzh/C/similar_craw/meta素材/防滑垫")


def today_prefix() -> str:
    today = date.today()
    return f"{today.month}{today.day}"


def create_folders(target_dir: Path, count: int) -> tuple[list[Path], list[Path]]:
    if count <= 0:
        raise ValueError("创建数量必须大于 0")
    if not target_dir.exists():
        raise FileNotFoundError(f"目标目录不存在: {target_dir}")
    if not target_dir.is_dir():
        raise NotADirectoryError(f"不是目录: {target_dir}")

    prefix = today_prefix()
    created: list[Path] = []
    skipped: list[Path] = []

    for index in range(1, count + 1):
        folder = target_dir / f"{prefix}.{index}"
        if folder.exists():
            skipped.append(folder)
            continue
        folder.mkdir(parents=True, exist_ok=False)
        created.append(folder)

    return created, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="按当天日期批量创建编号文件夹。")
    parser.add_argument("count", nargs="?", type=int, help="要创建的文件夹数量。")
    parser.add_argument("folder", nargs="?", help="目标目录；不填则使用默认目录。")
    parser.add_argument(
        "--target",
        default=str(DEFAULT_TARGET),
        help="目标目录；也可以用第二个位置参数传入。",
    )
    args = parser.parse_args()

    count = args.count
    if count is None:
        raw = input("请输入要创建的文件夹数量: ").strip()
        if not raw:
            raise SystemExit("未输入数量，已退出。")
        count = int(raw)

    target_dir = Path(args.folder or args.target).expanduser().resolve()
    created, skipped = create_folders(target_dir, count)

    print(f"目标目录: {target_dir}")
    print(f"日期前缀: {today_prefix()}")
    print(f"成功创建 {len(created)} 个文件夹:")
    for folder in created:
        print(folder.name)
    if skipped:
        print(f"跳过 {len(skipped)} 个已存在文件夹:")
        for folder in skipped:
            print(folder.name)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
