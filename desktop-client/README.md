# Meta Pinboard 广告素材客户端

这是用 **Python + Tkinter** 写的 macOS 客户端。Tkinter 的优点是不用再安装 Electron/Node，打包后体积和依赖更容易控制；缺点是不能完全达到 Figma/网页那种动画效果。当前界面已经按 Pinterest 风格重新整理：左侧菜单、右侧分页、卡片化投放者看板、红色强调、运行进度动效。

## 新版页面

左侧菜单可切换：

1. **总控台**
   - 设置输出目录、素材类型、HD、滚动参数、剪映参数。
2. **页面抓取**
   - 输入 Meta 广告资料库 URL。
   - 可设置“抓到指定资料库编号后停止”。
   - 可先扫描投放者。
3. **编号全流程**
   - 输入资料库编号。
   - 视频自动执行：抓取 → 整理 → Markdown → 剪映。
   - 图片自动执行：抓取 → 整理 → Markdown → 导出日期图片素材。
4. **投放者看板**
   - 扫描后显示投放者卡片。
   - 支持全部抓取、只抓选中、排除选中。
5. **实时日志**
   - 查看运行过程。
   - 可清空日志。
   - 可停止当前任务。

## 停止按钮

新版已经添加停止按钮：

- 顶部右侧：`停止当前任务`
- 编号全流程页面：`停止`
- 实时日志页面：`停止任务`

点击后会先 `terminate` 当前子进程；如果 5 秒内没退出，会自动 `kill`。

## 输出目录

只需要选择一次输出目录，客户端会自动在里面创建：

```text
输出目录/
├── 素材爬取/
├── 整理/
├── 920图片素材/       # 图片全流程会自动生成，日期与整理编号前缀一致
├── 广告素材.json
└── 投放者扫描.json
```

`920图片素材` 中的广告图片会按整理文件夹编号命名，例如 `920.1.jpg`、`920.2.png`。

## 单独导出图片素材

现在可以不打开客户端，直接运行：

```bash
python3 Meta广告素材客户端包/crawler/export_image_materials.py \
  --input '/Users/zzh/C/similar_craw/meta素材/男女方糖/918/918图片/整理' \
  --prefix 920
```

默认会生成同级目录 `920图片素材`。可以加 `--dry-run` 只预览，或用 `--output` 指定其他输出目录。

## 运行环境

`.app` 已经内置：

- 独立 CapCut Mate 后端及 Python 运行时，无需在使用电脑上安装后端源码、Python 或 uv
- 后端所需的 FFmpeg、FFprobe、MediaInfo 和模板
- 爬虫脚本
- 投放者扫描脚本
- Playwright Python 依赖
- Playwright 浏览器缓存

因此正常情况下不需要用户再手动执行：

```bash
pip install playwright
python -m playwright install chromium
```

侧栏「CapCut Mate 后端」可直接启动内置服务；视频全流程在导入前也会自动启动。
内置服务地址为 `http://127.0.0.1:30001`，不会停止或重启已有的 30000 端口后端。
草稿、数据库及日志保存于 `~/Library/Application Support/SimilarCrawClient/CapcutBackend/`，
后端启动日志为该目录下的 `backend.log`。使用端只需完整保留 `.app`。
当前打包目标为 Apple Silicon Mac（arm64）。

构建端需要先运行 `bash build_bundled_backend.sh` 生成独立后端，再运行打包脚本。
`BACKEND_SOURCE` 可指定构建时使用的 CapCut Mate 源码位置；此路径不用于应用运行。

## 打包位置

```text
/Users/zzh/C/similar_craw/Meta广告素材客户端包/dist/Meta广告素材客户端.app
```

## 重新打包

```bash
cd /Users/zzh/C/similar_craw
bash Meta广告素材客户端包/crawler/build_mac_app.sh
```
# 源码快照构建补充（v2026.11.25）

本目录是现有桌面客户端的源码备份，不包含构建缓存、虚拟环境或广告素材。历史说明中提到的开发机示例路径不代表运行时依赖。

ARM 构建需安装 Python 3.14、Tcl/Tk、`requirements.txt`，并为 `vendor/capcut-mate/.venv` 准备 Python 3.12 和 `requirements-backend-arm64.lock.txt`。执行 `bash build_bundled_backend.sh`，再执行 `bash 打包mac应用.command`。

Intel 构建需要 x86_64 Python：客户端环境 `.venv-intel` 使用 `requirements-intel.txt`，后端环境 `.venv-backend-intel` 使用 `requirements-backend-intel.lock.txt`。在 `intel-tools/` 放置 Intel FFmpeg 和 FFprobe，再执行 `bash build_intel_mac.sh`。Apple Silicon 主机执行 Intel 工具需要 Rosetta。

后端源码默认从 `vendor/capcut-mate` 读取，也可用 `BACKEND_SOURCE` 覆盖；公共贴纸目录已无损压缩，构建时自动还原。FFmpeg/FFprobe 构建输入可通过 `FFMPEG_BIN`、`FFPROBE_BIN` 指定，运行时随应用分发。Playwright 浏览器由打包脚本按版本、架构自动下载并验证。

测试：`python3 -m unittest discover -s tests -v`。
正式安装包是完整自包含 `.app`，不需要上述构建依赖；用户数据按目标电脑当前用户目录保存。

