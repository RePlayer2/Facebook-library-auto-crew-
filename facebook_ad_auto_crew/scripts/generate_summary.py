#!/usr/bin/env python3
"""
广告素材信息整理工具

扫描指定目录下的编号子文件夹（如 728.1, 728.2, ...），
读取每个文件夹内的素材信息.md，提取标题和文案，
按顺序合并输出为一个 Markdown 总结文件。

使用方式:
    python generate_summary.py                    # 默认扫描当前目录
    python generate_summary.py -i /path/to/整理   # 指定输入目录
    python generate_summary.py -i ./整理 -o 整理.md  # 指定输入和输出
    python generate_summary.py --prefix 729        # 只处理 729.x 的文件夹
    python generate_summary.py --range 728.1-728.10  # 只处理指定范围
"""

import argparse
import os
import re
import sys
from pathlib import Path


LOW_IMPRESSIONS_RE = re.compile(r"(?:<\s*100|100\s*<|&lt;\s*100)", re.I)


def normalize_impressions(value: str) -> str:
    """展示次数只保留 100< 标记。"""
    return "100<" if LOW_IMPRESSIONS_RE.search(value or "") else ""


def sort_key(name: str) -> tuple:
    """提取文件夹名中的数字作为排序键，如 '728.1' -> (728, 1)"""
    match = re.match(r"(\d+)\.(\d+)", name)
    if match:
        return (int(match.group(1)), int(match.group(2)))
    return (999999, 999999)


def parse_folder_name(name: str) -> tuple | None:
    """解析文件夹名，返回 (prefix, number) 或 None"""
    match = re.match(r"(\d+)\.(\d+)", name)
    if match:
        return (int(match.group(1)), int(match.group(2)))
    return None


def extract_field(lines: list[str], field_name: str) -> str:
    """从素材信息.md中提取单个字段"""
    marker = f"{field_name}："
    stop_markers = {"资料库编号：", "广告标题：", "展示次数：", "广告描述：", "文案：", "广告图片：", "广告视频："}
    for index, line in enumerate(lines):
        if marker in line:
            value = line.split(marker, 1)[1].strip()
            if value:
                return value.replace("\uFFFD", "").strip() or "无"
            collected = []
            for next_line in lines[index + 1:]:
                stripped = next_line.strip()
                if stripped in stop_markers or any(stripped.startswith(stop) for stop in stop_markers):
                    break
                if stripped:
                    collected.append(stripped)
                    break
            value = "".join(collected).replace("\uFFFD", "").strip()
            return value if value else "无"
    return "无"


def extract_title(lines: list[str]) -> str:
    """从素材信息.md的行列表中提取标题"""
    for i, line in enumerate(lines):
        if "广告标题：" in line:
            title_part = line.split("广告标题：", 1)[1].strip()
            if title_part:
                title = title_part
            else:
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line and "文案：" not in next_line:
                        title = next_line
                    else:
                        title = "无"
                else:
                    title = "无"
            title = title.replace("\uFFfd", "").strip()
            return title if title else "无"
    return "无"


def extract_copy(lines: list[str]) -> str:
    """从素材信息.md的行列表中提取文案"""
    copy_lines = []
    in_copy = False

    for line in lines:
        if "文案：" in line and not in_copy:
            in_copy = True
            copy_part = line.split("文案：", 1)[1].strip()
            if copy_part:
                copy_lines.append(copy_part)
            continue

        if in_copy:
            stripped = line.strip()
            if stripped.startswith("0:") or "广告视频" in stripped:
                break
            if re.match(r"^\d+:\d+$", stripped):
                continue
            if stripped == "/":
                continue
            copy_lines.append(line)

    return "".join(copy_lines).strip()


def get_folders_to_process(base_dir: Path, prefix: int | None, range_str: str | None) -> list[Path]:
    """获取需要处理的文件夹列表"""
    if not base_dir.exists():
        print(f"错误：目录不存在 - {base_dir}", file=sys.stderr)
        sys.exit(1)

    # 筛选子文件夹
    dirs = []
    for d in base_dir.iterdir():
        if d.is_dir():
            parsed = parse_folder_name(d.name)
            if parsed:
                dirs.append((d, parsed))

    # 按 prefix 筛选
    if prefix is not None:
        dirs = [(d, p) for d, p in dirs if p[0] == prefix]

    # 按 range 筛选
    if range_str:
        range_match = re.match(r"(\d+)\.(\d+)-(\d+)\.(\d+)", range_str)
        if range_match:
            p1, n1, p2, n2 = int(range_match.group(1)), int(range_match.group(2)), int(range_match.group(3)), int(range_match.group(4))
            start = (p1, n1)
            end = (p2, n2)
            dirs = [(d, p) for d, p in dirs if start <= p <= end]
        else:
            print(f"错误：range 格式不正确，应为 '728.1-728.10' 格式", file=sys.stderr)
            sys.exit(1)

    # 排序
    dirs.sort(key=lambda x: x[1])

    return [d for d, _ in dirs]


def generate_summary(base_dir: Path, output_file: Path, prefix: int | None, range_str: str | None) -> None:
    """生成整理文档"""
    folders = get_folders_to_process(base_dir, prefix, range_str)

    if not folders:
        print("警告：没有找到符合条件的文件夹", file=sys.stderr)
        return

    processed = 0
    skipped = 0

    with open(output_file, "w", encoding="utf-8") as out:
        for folder in folders:
            parsed = parse_folder_name(folder.name)
            if not parsed:
                continue

            section_num = f"{parsed[0]}.{parsed[1]}"
            md_file = folder / "素材信息.md"

            if not md_file.exists():
                print(f"  跳过 {section_num}：素材信息.md 不存在", file=sys.stderr)
                skipped += 1
                continue

            try:
                lines = md_file.read_text(encoding="utf-8").splitlines(keepends=True)
                library_id = extract_field(lines, "资料库编号")
                title = extract_title(lines)
                impressions = normalize_impressions(extract_field(lines, "展示次数"))
                description = extract_field(lines, "广告描述")
                copy = extract_copy(lines)

                out.write(f"## {section_num}：\n\n")
                out.write(f"#### 资料库编号：\n{library_id}\n\n")
                out.write(f"#### 广告标题：\n{title}\n\n")
                if impressions == "100<":
                    out.write(f"#### 展示次数：\n{impressions}\n\n")
                out.write(f"#### 广告描述：\n{description}\n\n")
                out.write(f"#### 文案：\n{copy}\n\n\n")

                processed += 1
                print(f"  处理 {section_num} ✓")

            except Exception as e:
                print(f"  跳过 {section_num}：读取失败 - {e}", file=sys.stderr)
                skipped += 1

    print(f"\n完成！共处理 {processed} 个，跳过 {skipped} 个")
    print(f"输出文件：{output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="广告素材信息整理工具 - 扫描编号文件夹并合并输出 Markdown",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 扫描当前目录下所有编号文件夹
  python generate_summary.py

  # 指定输入目录和输出文件
  python generate_summary.py -i /path/to/整理 -o 整理.md

  # 只处理 729.x 的文件夹
  python generate_summary.py -i ./整理 --prefix 729

  # 只处理 728.1 到 728.10 的文件夹
  python generate_summary.py -i ./整理 --range 728.1-728.10

  # 处理 813.1 到 813.44
  python generate_summary.py -i ./整理 --range 813.1-813.44
        """,
    )

    parser.add_argument(
        "-i", "--input",
        type=Path,
        default=Path("."),
        help="输入目录路径，默认为当前目录",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="输出文件路径，默认为 <输入目录>/整理.md",
    )
    parser.add_argument(
        "--prefix",
        type=int,
        default=None,
        help="只处理指定前缀的文件夹，如 --prefix 729 只处理 729.x",
    )
    parser.add_argument(
        "--range",
        type=str,
        default=None,
        help="只处理指定范围的文件夹，格式如 '728.1-728.10'",
    )

    args = parser.parse_args()

    base_dir = args.input.resolve()
    output_file = args.output or (base_dir / "整理.md")

    print(f"扫描目录：{base_dir}")
    print(f"输出文件：{output_file}")

    if args.prefix is not None:
        print(f"筛选前缀：{args.prefix}")
    if args.range:
        print(f"筛选范围：{args.range}")
    print()

    generate_summary(base_dir, output_file, args.prefix, args.range)


if __name__ == "__main__":
    main()
