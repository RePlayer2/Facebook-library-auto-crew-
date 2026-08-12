# Facebook Library Auto Crew

Facebook Library Auto Crew 是一个围绕 **Meta / Facebook Ads Library 广告素材采集、整理、Markdown 汇总和剪映草稿导入** 的自动化脚本集合。

本发布包只保留脚本代码和使用说明，不包含广告投流分析文档、投放数据 CSV、素材视频或图片文件。

## 功能概览

- 按 Facebook Ads Library 页面链接抓取广告卡片、素材和 JSON 数据
- 按广告资料库编号批量抓取广告素材
- 将抓取结果整理成日期编号文件夹，例如 `810.1`、`810.2`
- 从整理目录生成 Markdown 素材总结
- 可选：将整理后的视频素材导入剪映草稿

## 剪映导入依赖说明

本项目中的剪映草稿导入功能使用了开源项目 [capcut-mate](https://github.com/Hommy-master/capcut-mate) 提供的本地 API 能力。

如果你只使用 Facebook Ads Library 抓取、素材整理或 Markdown 总结功能，不需要启动 `capcut-mate`。

如果你需要使用 `capcut_local_draft_import.py` 或 `meta_material_pipeline.py` 中的剪映导入步骤，请先在本地启动 `capcut-mate` 后端服务。

示例：

```bash
cd '/Users/zzh/C/capcut-mate-main/capcut-mate-main'
source .venv/bin/activate
python main.py
```

然后再运行本项目的剪映导入命令。

## 目录结构

```text
项目根目录/
├── README.md
└── scripts/
    ├── meta_material_pipeline.py          # 一键总控脚本
    ├── meta_ad_card_extractor.py          # Ads Library 单页面抓取
    ├── meta_ad_card_batch_by_ids.py       # 按资料库编号批量抓取
    ├── create_and_copy_dated_folders.py   # 创建日期编号整理目录
    ├── generate_summary.py                # 生成 Markdown 素材总结
    └── capcut_local_draft_import.py       # 导入剪映草稿，依赖 capcut-mate
```

## 快速开始

进入项目根目录：

```bash
cd /Users/zzh/C/similar_craw
```

如果使用本地虚拟环境：

```bash
source /Users/zzh/C/similar_craw/crawler/.venv/bin/activate
```

## 一键流程：按资料库编号抓取

```bash
python3 scripts/meta_material_pipeline.py all \
  --crawl-mode ids \
  --ids 1526356798675388 \
  --crawl-output-root '/Users/zzh/C/similar_craw/meta素材/防滑垫/810素材爬取' \
  --scroll-rounds 5 \
  --stop-after-stable-rounds 3 \
  --wait-ms 2000 \
  --organize-target '/Users/zzh/C/similar_craw/meta素材/防滑垫/810整理' \
  --summary-script 'scripts/generate_summary.py' \
  --capcut-from-dir '/Users/zzh/C/similar_craw/meta素材/防滑垫/810整理' \
  --capcut-draft-name '810suc防滑垫'
```

参数说明：

- `--crawl-mode ids`：按资料库编号抓取
- `--ids`：Facebook 广告资料库编号，可传多个
- `--crawl-output-root`：抓取结果输出根目录
- `--scroll-rounds 5`：最多滚动 5 次
- `--stop-after-stable-rounds 3`：连续 3 次没有新增就停止
- `--wait-ms 2000`：每轮滚动等待 2 秒
- `--organize-target`：整理后的编号文件夹目录
- `--summary-script`：素材总结脚本路径
- `--capcut-from-dir`：剪映导入来源目录
- `--capcut-draft-name`：剪映草稿名称

如果不需要导入剪映，可以加上：

```bash
--skip-capcut
```

## 一键流程：按页面链接抓取

```bash
python3 scripts/meta_material_pipeline.py all \
  --crawl-mode page \
  --url 'https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&media_type=video&q=sleepease&search_type=keyword_unordered' \
  --asset-dir '/Users/zzh/C/similar_craw/meta素材/鼻贴/广告素材文件' \
  --crawl-output '/Users/zzh/C/similar_craw/meta素材/鼻贴/HD前三条测试/广告素材文件.json' \
  --result-count-root '/Users/zzh/C/similar_craw/meta素材/鼻贴/广告素材文件' \
  --scroll-rounds 5 \
  --stop-after-stable-rounds 3 \
  --wait-ms 2000 \
  --organize-target '/Users/zzh/C/similar_craw/meta素材/鼻贴/810整理' \
  --summary-script 'scripts/generate_summary.py' \
  --capcut-from-dir '/Users/zzh/C/similar_craw/meta素材/鼻贴/810整理' \
  --capcut-draft-name '810suc'
```

## 单独运行各步骤

### 1. 只抓取资料库编号

```bash
python3 scripts/meta_material_pipeline.py crawl-ids \
  --ids 1526356798675388 \
  --crawl-output-root '/Users/zzh/C/similar_craw/meta素材/防滑垫/810素材爬取' \
  --scroll-rounds 5 \
  --stop-after-stable-rounds 3 \
  --wait-ms 2000
```

### 2. 只整理素材文件夹

```bash
python3 scripts/meta_material_pipeline.py organize \
  --organize-ids 1526356798675388 \
  --organize-target '/Users/zzh/C/similar_craw/meta素材/防滑垫/810整理' \
  --organize-source-root '/Users/zzh/C/similar_craw/meta素材/防滑垫/810素材爬取' \
  --organize-prefix 810
```

### 3. 只生成 Markdown 总结

```bash
python3 scripts/meta_material_pipeline.py summary \
  --summary-input '/Users/zzh/C/similar_craw/meta素材/防滑垫/810整理' \
  --summary-output '/Users/zzh/C/similar_craw/meta素材/防滑垫/810整理/整理.md'
```

### 4. 只导入剪映草稿

使用这一步前，需要先启动 [capcut-mate](https://github.com/Hommy-master/capcut-mate) 后端。

```bash
python3 scripts/meta_material_pipeline.py capcut \
  --capcut-from-dir '/Users/zzh/C/similar_craw/meta素材/防滑垫/810整理' \
  --capcut-one-per-folder \
  --capcut-exclude-glob '*_1080x1920_*' \
  --capcut-exclude-glob '*_match_capcut*' \
  --capcut-width 1080 \
  --capcut-height 1920 \
  --capcut-scale 1.03 \
  --capcut-speed 0.93 \
  --capcut-draft-name '810suc防滑垫'
```

## 开源协议

本发布包建议采用 **MIT License** 开源。

除非仓库根目录另有 `LICENSE` 文件或其他明确声明，本目录下代码可以按照 MIT License 的精神使用、复制、修改、合并、发布和再授权，但需要保留原始版权声明和许可声明。

简要说明：

- 允许个人或商业用途使用本工具。
- 允许复制、修改、分发和二次开发。
- 作者不对使用本工具造成的数据损失、账号风险、平台限制、法律争议或商业损失承担责任。
- 本 README 中的协议说明不构成法律意见；如用于商业项目，请自行确认适用的开源协议和合规要求。

建议在仓库根目录补充正式 `LICENSE` 文件，内容可使用标准 MIT License。

## 使用责任声明

本项目是一个用于学习、研究和整理公开广告素材信息的自动化工具集合。使用者在运行任何爬虫、自动化抓取、素材下载或数据整理功能前，应自行确认其行为符合所在地法律法规、目标网站服务条款以及相关平台政策。

使用本项目即表示你理解并同意：

- 本项目不隶属于 Meta、Facebook、Instagram、CapCut、剪映或其关联公司。
- 剪映导入部分依赖第三方开源项目 [capcut-mate](https://github.com/Hommy-master/capcut-mate)，请同时遵守该项目的开源协议和使用要求。
- 本项目不提供绕过登录、权限、验证码、风控、付费墙或访问限制的功能。
- 使用者应只采集自己有权访问的公开信息，避免采集、存储或传播个人隐私、敏感信息或受保护内容。
- 使用者应合理控制请求频率、滚动次数和下载规模，避免对目标网站、接口或第三方服务造成压力。
- 使用者应遵守 Meta / Facebook Ads Library 的使用规则、服务条款、版权规则和数据使用限制。
- 抓取到的广告图片、视频、文案、商标和品牌信息可能受版权、商标权或其他权利保护；使用者不得擅自商用、冒用、抄袭或误导性传播。
- 因使用本项目导致的账号限制、平台封禁、数据丢失、侵权投诉、商业损失或其他风险，由使用者自行承担。

建议使用方式：

- 优先用于公开资料研究、广告素材归档、竞品观察和内部学习。
- 不要高频、大规模、并发抓取。
- 不要用于侵犯版权、复制竞争对手素材、规避平台审查或违反广告平台政策的用途。
- 上传公开仓库前，请移除私密数据、客户数据、投放账户信息、订单数据和未经授权的素材文件。

## 注意事项

- 本发布包不包含素材视频、图片、投放数据 CSV 或广告投流分析文档。
- 如果抓取需要登录态，请使用原脚本支持的 `--storage-state` 参数。
- 如果页面只有 1 条广告，建议使用 `--scroll-rounds 5 --stop-after-stable-rounds 3 --wait-ms 2000`，避免滚动等待太久。
- 剪映导入依赖本地 [capcut-mate](https://github.com/Hommy-master/capcut-mate) 服务，需要先启动后端。
