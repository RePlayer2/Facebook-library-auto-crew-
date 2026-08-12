#!/usr/bin/env python3
"""Meta 广告素材一键流水线。

把快速使用说明里的几个步骤串起来：
1) 按页面或按资料库编号抓取广告素材
2) 将素材整理到日期编号文件夹
3) 生成 Markdown 总结
4) 可选：导入剪映草稿

示例：
  # 按资料库编号批量抓取 + 整理 + 总结
  python3 crawler/meta_material_pipeline.py all \
    --crawl-mode ids \
    --ids 1535616134688097 1075061404956603 \
    --crawl-output-root /Users/zzh/C/similar_craw/meta素材/鼻贴/810素材爬取 \
    --organize-target /Users/zzh/C/similar_craw/meta素材/鼻贴/810整理 \
    --summary-script /Users/zzh/C/similar_craw/meta素材/防滑垫/广告素材文件/整理/generate_summary.py

  # 按页面抓取 + 整理 + 总结 + 导入剪映草稿
  python3 crawler/meta_material_pipeline.py all \
    --crawl-mode page \
    --url 'https://www.facebook.com/ads/library/?...' \
    --asset-dir /Users/zzh/C/similar_craw/meta素材/鼻贴/广告素材文件 \
    --crawl-output /Users/zzh/C/similar_craw/meta素材/鼻贴/HD前三条测试/广告素材文件.json \
    --organize-target /Users/zzh/C/similar_craw/meta素材/鼻贴/807整理 \
    --summary-output /Users/zzh/C/similar_craw/meta素材/鼻贴/807整理.md \
    --capcut-from-dir /Users/zzh/C/similar_craw/meta素材/鼻贴/807整理 \
    --capcut-draft-name 807suc
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTRACTOR = PROJECT_ROOT / "crawler" / "meta_ad_card_extractor.py"
BATCH_BY_IDS = PROJECT_ROOT / "crawler" / "meta_ad_card_batch_by_ids.py"
COPY_FOLDERS = PROJECT_ROOT / "crawler" / "create_and_copy_dated_folders.py"
CAPCUT_IMPORT = PROJECT_ROOT / "crawler" / "capcut_local_draft_import.py"
DEFAULT_SUMMARY_SCRIPT = PROJECT_ROOT / "meta素材" / "防滑垫" / "广告素材文件" / "整理" / "generate_summary.py"


def run_command(command: list[str], *, dry_run: bool = False) -> None:
    print("$", " ".join(shlex.quote(str(part)) for part in command))
    if dry_run:
        return
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def build_crawl_page_command(args: argparse.Namespace) -> list[str]:
    if not args.url:
        raise SystemExit("crawl-page 需要 --url")
    if not args.asset_dir:
        raise SystemExit("crawl-page 需要 --asset-dir")
    if not args.crawl_output:
        raise SystemExit("crawl-page 需要 --crawl-output")

    command = [
        sys.executable,
        str(EXTRACTOR),
        "--crawl",
        "--url",
        args.url,
        "--asset-dir",
        str(Path(args.asset_dir).expanduser().resolve()),
        "--output",
        str(Path(args.crawl_output).expanduser().resolve()),
    ]

    if args.result_count_root:
        command.extend(["--result-count-root", str(Path(args.result_count_root).expanduser().resolve())])
    if args.save_html:
        command.extend(["--save-html", str(Path(args.save_html).expanduser().resolve())])
    if args.scroll_rounds is not None:
        command.extend(["--scroll-rounds", str(args.scroll_rounds)])
    if args.stop_after_stable_rounds is not None:
        command.extend(["--stop-after-stable-rounds", str(args.stop_after_stable_rounds)])
    if args.wait_ms is not None:
        command.extend(["--wait-ms", str(args.wait_ms)])
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
        command.extend(["--storage-state", str(Path(args.storage_state).expanduser().resolve())])

    return command


def build_crawl_ids_command(args: argparse.Namespace) -> list[str]:
    if not args.ids:
        raise SystemExit("crawl-ids 需要至少一个资料库编号")
    if not args.crawl_output_root:
        raise SystemExit("crawl-ids 需要 --crawl-output-root")

    command = [
        sys.executable,
        str(BATCH_BY_IDS),
        *args.ids,
        "--output-root",
        str(Path(args.crawl_output_root).expanduser().resolve()),
    ]

    if args.headless:
        command.append("--headless")
    if args.show:
        command.append("--show")
    if args.download_images:
        command.append("--download-images")
    if args.require_hd_video:
        command.append("--require-hd-video")
    if args.scroll_rounds is not None:
        command.extend(["--scroll-rounds", str(args.scroll_rounds)])
    if args.stop_after_stable_rounds is not None:
        command.extend(["--stop-after-stable-rounds", str(args.stop_after_stable_rounds)])
    if args.wait_ms is not None:
        command.extend(["--wait-ms", str(args.wait_ms)])
    if args.max_cards is not None:
        command.extend(["--max-cards", str(args.max_cards)])
    if args.no_expand_grouped_ads:
        command.append("--no-expand-grouped-ads")
    if args.no_result_count_folder:
        command.append("--no-result-count-folder")
    if args.fast_hd:
        command.append("--fast-hd")
    if args.storage_state:
        command.extend(["--storage-state", str(Path(args.storage_state).expanduser().resolve())])

    return command


def build_organize_command(args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        str(COPY_FOLDERS),
    ]
    if getattr(args, "organize_ids", None):
        command.extend(args.organize_ids)
    if getattr(args, "organize_ids_file", None):
        command.extend(["--ids-file", str(Path(args.organize_ids_file).expanduser().resolve())])
    if getattr(args, "organize_json", None):
        command.extend(["--json", str(Path(args.organize_json).expanduser().resolve())])
    if getattr(args, "organize_target", None):
        command.extend(["--target", str(Path(args.organize_target).expanduser().resolve())])
    if getattr(args, "organize_source_root", None):
        command.extend(["--source-root", str(Path(args.organize_source_root).expanduser().resolve())])
    if getattr(args, "organize_prefix", None):
        command.extend(["--prefix", str(args.organize_prefix)])
    if getattr(args, "organize_count", None) is not None:
        command.extend(["--count", str(args.organize_count)])
    if getattr(args, "organize_start_index", None) is not None:
        command.extend(["--start-index", str(args.organize_start_index)])
    if getattr(args, "organize_overwrite", False):
        command.append("--overwrite")
    if getattr(args, "organize_dry_run", False):
        command.append("--dry-run")
    return command


def build_summary_command(args: argparse.Namespace) -> list[str]:
    summary_script = Path(args.summary_script).expanduser().resolve()
    if not getattr(args, "summary_input", None):
        raise SystemExit("summary 需要 --summary-input")
    command = [
        sys.executable,
        str(summary_script),
        "-i",
        str(Path(args.summary_input).expanduser().resolve()),
    ]
    if args.summary_output:
        command.extend(["-o", str(Path(args.summary_output).expanduser().resolve())])
    return command


def build_capcut_command(args: argparse.Namespace) -> list[str]:
    if not args.capcut_from_dir:
        raise SystemExit("capcut 需要 --capcut-from-dir")

    command = [
        sys.executable,
        str(CAPCUT_IMPORT),
        "--from-dir",
        str(Path(args.capcut_from_dir).expanduser().resolve()),
    ]
    if args.capcut_one_per_folder:
        command.append("--one-per-folder")
    for pattern in args.capcut_exclude_glob:
        command.extend(["--exclude-glob", pattern])
    if args.capcut_width is not None:
        command.extend(["--width", str(args.capcut_width)])
    if args.capcut_height is not None:
        command.extend(["--height", str(args.capcut_height)])
    if args.capcut_scale is not None:
        command.extend(["--scale", str(args.capcut_scale)])
    if args.capcut_speed is not None:
        command.extend(["--speed", str(args.capcut_speed)])
    if args.capcut_draft_name:
        command.extend(["--draft-name", args.capcut_draft_name])
    if args.capcut_api_base:
        command.extend(["--api-base", args.capcut_api_base])
    if args.capcut_mate_root:
        command.extend(["--capcut-mate-root", str(Path(args.capcut_mate_root).expanduser().resolve())])
    if args.capcut_jianying_draft_dir:
        command.extend(["--jianying-draft-dir", str(Path(args.capcut_jianying_draft_dir).expanduser().resolve())])
    if args.capcut_http_root:
        command.extend(["--http-root", str(Path(args.capcut_http_root).expanduser().resolve())])
    if args.capcut_http_port is not None:
        command.extend(["--http-port", str(args.capcut_http_port)])
    if args.capcut_host:
        command.extend(["--host", args.capcut_host])
    if args.capcut_overwrite:
        command.append("--overwrite")
    if args.capcut_keep_server:
        command.append("--keep-server")
    if args.capcut_list_only:
        command.append("--list-only")
    return command


def add_common_crawl_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--headless", action="store_true", help="无头模式")
    parser.add_argument("--show", action="store_true", help="显示浏览器窗口")
    parser.add_argument("--download-images", action="store_true", help="下载图片素材")
    parser.add_argument("--require-hd-video", action="store_true", help="要求高清视频")
    parser.add_argument("--scroll-rounds", type=int, help="滚动轮数")
    parser.add_argument("--stop-after-stable-rounds", type=int, help="稳定后停止轮数")
    parser.add_argument("--wait-ms", type=int, help="等待毫秒数")
    parser.add_argument("--max-cards", type=int, help="最多抓取卡片数")
    parser.add_argument("--no-expand-grouped-ads", action="store_true", help="不展开分组广告")
    parser.add_argument("--no-result-count-folder", action="store_true", help="不创建 result-count 文件夹")
    parser.add_argument("--storage-state", help="浏览器存储状态文件")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Meta 广告素材总控脚本：抓取、整理、总结、导入剪映一体化。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    crawl_page = subparsers.add_parser("crawl-page", help="基于广告页面抓取素材")
    crawl_page.add_argument("--url", required=True, help="Facebook Ads Library 链接")
    crawl_page.add_argument("--asset-dir", required=True, help="素材输出目录")
    crawl_page.add_argument("--crawl-output", required=True, help="抓取 JSON 输出路径")
    crawl_page.add_argument("--result-count-root", help="结果计数根目录")
    crawl_page.add_argument("--save-html", help="保存页面 HTML 路径")
    add_common_crawl_arguments(crawl_page)

    crawl_ids = subparsers.add_parser("crawl-ids", help="基于资料库编号批量抓取素材")
    crawl_ids.add_argument("ids", nargs="+", help="资料库编号列表")
    crawl_ids.add_argument("--crawl-output-root", required=True, help="批量抓取输出根目录")
    add_common_crawl_arguments(crawl_ids)
    crawl_ids.add_argument("--fast-hd", action="store_true", help="快速高清视频模式")

    organize = subparsers.add_parser("organize", help="按 JSON 或资料库编号整理素材文件夹")
    organize.add_argument("--organize-json", help="广告素材 JSON 路径")
    organize.add_argument("--organize-target", required=True, help="整理输出目录")
    organize.add_argument("--organize-source-root", help="源素材根目录")
    organize.add_argument("--organize-prefix", help="编号前缀")
    organize.add_argument("--organize-count", type=int, help="只处理前 N 条")
    organize.add_argument("--organize-start-index", type=int, help="起始序号")
    organize.add_argument("--organize-overwrite", action="store_true", help="覆盖已存在文件夹")
    organize.add_argument("--organize-dry-run", action="store_true", help="只打印不执行")
    organize.add_argument("--organize-ids", nargs="*", help="手动指定资料库编号")
    organize.add_argument("--organize-ids-file", help="资料库编号文件")

    summary = subparsers.add_parser("summary", help="生成 Markdown 总结")
    summary.add_argument("--summary-script", default=str(DEFAULT_SUMMARY_SCRIPT), help="generate_summary.py 路径")
    summary.add_argument("--summary-input", required=True, help="输入目录")
    summary.add_argument("--summary-output", help="输出 Markdown 路径")

    capcut = subparsers.add_parser("capcut", help="导入剪映草稿")
    capcut.add_argument("--capcut-from-dir", required=True, help="整理目录")
    capcut.add_argument("--capcut-one-per-folder", action="store_true", help="每个文件夹只取一个视频")
    capcut.add_argument("--capcut-exclude-glob", action="append", default=[], help="排除文件 glob")
    capcut.add_argument("--capcut-width", type=int, default=1080, help="草稿宽度")
    capcut.add_argument("--capcut-height", type=int, default=1920, help="草稿高度")
    capcut.add_argument("--capcut-scale", type=float, default=1.03, help="缩放比例")
    capcut.add_argument("--capcut-speed", type=float, default=0.93, help="倍速")
    capcut.add_argument("--capcut-draft-name", help="草稿名称")
    capcut.add_argument("--capcut-api-base", default=None, help="capcut-mate API 前缀")
    capcut.add_argument("--capcut-mate-root", default=None, help="capcut-mate 项目根目录")
    capcut.add_argument("--capcut-jianying-draft-dir", default=None, help="剪映草稿目录")
    capcut.add_argument("--capcut-http-root", default=None, help="本地 HTTP 根目录")
    capcut.add_argument("--capcut-http-port", type=int, default=None, help="本地 HTTP 端口")
    capcut.add_argument("--capcut-host", default=None, help="HTTP host")
    capcut.add_argument("--capcut-overwrite", action="store_true", help="覆盖草稿目录")
    capcut.add_argument("--capcut-keep-server", action="store_true", help="保持 HTTP 服务运行")
    capcut.add_argument("--capcut-list-only", action="store_true", help="只列出视频顺序")

    all_cmd = subparsers.add_parser("all", help="按快速使用说明串联执行全流程")
    all_cmd.add_argument("--crawl-mode", choices=["page", "ids"], required=True, help="抓取模式")
    all_cmd.add_argument("--url", help="page 模式的 Ads Library 链接")
    all_cmd.add_argument("--asset-dir", help="page 模式的素材输出目录")
    all_cmd.add_argument("--crawl-output", help="page 模式的输出 JSON")
    all_cmd.add_argument("--result-count-root", help="page 模式的结果计数根目录")
    all_cmd.add_argument("--save-html", help="page 模式的 HTML 保存路径")
    all_cmd.add_argument("ids", nargs="*", help="ids 模式的资料库编号；也可以使用 --ids")
    all_cmd.add_argument("--ids", dest="ids_option", nargs="+", help="ids 模式的资料库编号")
    all_cmd.add_argument("--crawl-output-root", help="ids 模式的输出根目录")
    add_common_crawl_arguments(all_cmd)
    all_cmd.add_argument("--fast-hd", action="store_true", help="ids 模式的快速高清视频模式")

    all_cmd.add_argument("--organize-json", help="整理用 JSON 路径")
    all_cmd.add_argument("--organize-target", help="整理输出目录")
    all_cmd.add_argument("--organize-source-root", help="整理源目录")
    all_cmd.add_argument("--organize-prefix", help="整理前缀")
    all_cmd.add_argument("--organize-count", type=int, help="整理条数")
    all_cmd.add_argument("--organize-start-index", type=int, help="整理起始序号")
    all_cmd.add_argument("--organize-overwrite", action="store_true", help="覆盖整理目录")
    all_cmd.add_argument("--organize-dry-run", action="store_true", help="只打印整理步骤，不实际复制")
    all_cmd.add_argument("--organize-ids", nargs="*", help="整理时手动指定资料库编号")
    all_cmd.add_argument("--organize-ids-file", help="整理时资料库编号文件")
    all_cmd.add_argument("--skip-organize", action="store_true", help="跳过整理步骤")

    all_cmd.add_argument("--summary-script", default=str(DEFAULT_SUMMARY_SCRIPT), help="generate_summary.py 路径")
    all_cmd.add_argument("--summary-input", help="总结输入目录；不传则默认使用 --organize-target")
    all_cmd.add_argument("--summary-output", help="总结输出 Markdown")
    all_cmd.add_argument("--skip-summary", action="store_true", help="跳过总结步骤")

    all_cmd.add_argument("--capcut-from-dir", help="剪映导入来源目录")
    all_cmd.add_argument("--capcut-one-per-folder", action="store_true", help="剪映每个文件夹只取一个视频")
    all_cmd.add_argument("--capcut-exclude-glob", action="append", default=[], help="剪映排除文件 glob")
    all_cmd.add_argument("--capcut-width", type=int, default=1080, help="剪映草稿宽度")
    all_cmd.add_argument("--capcut-height", type=int, default=1920, help="剪映草稿高度")
    all_cmd.add_argument("--capcut-scale", type=float, default=1.03, help="剪映缩放比例")
    all_cmd.add_argument("--capcut-speed", type=float, default=0.93, help="剪映倍速")
    all_cmd.add_argument("--capcut-draft-name", help="剪映草稿名称")
    all_cmd.add_argument("--capcut-api-base", default=None, help="capcut-mate API 前缀")
    all_cmd.add_argument("--capcut-mate-root", default=None, help="capcut-mate 项目根目录")
    all_cmd.add_argument("--capcut-jianying-draft-dir", default=None, help="剪映草稿目录")
    all_cmd.add_argument("--capcut-http-root", default=None, help="本地 HTTP 根目录")
    all_cmd.add_argument("--capcut-http-port", type=int, default=None, help="本地 HTTP 端口")
    all_cmd.add_argument("--capcut-host", default=None, help="HTTP host")
    all_cmd.add_argument("--capcut-overwrite", action="store_true", help="覆盖剪映草稿目录")
    all_cmd.add_argument("--capcut-keep-server", action="store_true", help="保持 HTTP 服务运行")
    all_cmd.add_argument("--capcut-list-only", action="store_true", help="只列出剪映视频顺序")
    all_cmd.add_argument("--skip-capcut", action="store_true", help="跳过剪映导入步骤")

    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.command == "crawl-page":
        run_command(build_crawl_page_command(args))
        return 0

    if args.command == "crawl-ids":
        run_command(build_crawl_ids_command(args))
        return 0

    if args.command == "organize":
        run_command(build_organize_command(args))
        return 0

    if args.command == "summary":
        run_command(build_summary_command(args))
        return 0

    if args.command == "capcut":
        run_command(build_capcut_command(args))
        return 0

    if args.command == "all":
        if getattr(args, "ids_option", None):
            args.ids = args.ids_option

        crawl_output_path: Path | None = None
        if args.crawl_mode == "page":
            crawl_output_path = Path(args.crawl_output).expanduser().resolve() if args.crawl_output else None
            crawl_args = argparse.Namespace(**vars(args))
            run_command(build_crawl_page_command(crawl_args))
        else:
            if not args.crawl_output_root:
                raise SystemExit("all --crawl-mode ids 需要 --crawl-output-root")
            crawl_args = argparse.Namespace(**vars(args))
            run_command(build_crawl_ids_command(crawl_args))

        if not args.skip_organize:
            organize_args = argparse.Namespace(**vars(args))
            if args.crawl_mode == "ids" and not organize_args.organize_ids:
                organize_args.organize_ids = list(args.ids)
            if args.crawl_mode == "ids" and not organize_args.organize_source_root:
                organize_args.organize_source_root = args.crawl_output_root
            if not organize_args.organize_json and crawl_output_path and crawl_output_path.exists():
                organize_args.organize_json = str(crawl_output_path)
            run_command(build_organize_command(organize_args))

        if not args.skip_summary:
            summary_args = argparse.Namespace(**vars(args))
            if not getattr(summary_args, "summary_input", None):
                if args.organize_target:
                    summary_args.summary_input = args.organize_target
            if not summary_args.summary_output and args.organize_target:
                summary_args.summary_output = str(Path(args.organize_target).expanduser().resolve() / "整理.md")
            run_command(build_summary_command(summary_args))

        if not args.skip_capcut:
            capcut_args = argparse.Namespace(**vars(args))
            if not capcut_args.capcut_from_dir and args.organize_target:
                capcut_args.capcut_from_dir = args.organize_target
            run_command(build_capcut_command(capcut_args))

        return 0

    raise SystemExit(f"未知命令：{args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
