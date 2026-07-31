# Facebook Library Auto Crew

这是一个用于抓取、整理和备份 Facebook / Meta 广告资料库素材的脚本集合。

主要功能包括：

- 从 Meta 广告资料库页面抓取广告卡片信息。
- 支持按指定 URL 抓取广告素材。
- 支持按资料库编号批量抓取广告素材。
- 支持图片和视频素材分文件夹保存。
- 支持视频 HD 高清抓取模式。
- 支持为每条广告创建独立文件夹。
- 支持生成广告素材 JSON 和 Markdown 文档。
- 支持把抓取到的素材复制整理成日期编号文件夹。

## 文件说明

```text
meta_ad_card_extractor.py
```

核心抓取脚本，用于从 Meta 广告资料库页面抓取广告素材、下载图片或视频，并生成 JSON / Markdown 文件。

```text
meta_ad_card_batch_by_ids.py
```

按资料库编号批量抓取广告的脚本。输入多个资料库编号后，会自动拼接 Meta 广告资料库搜索 URL 并逐个抓取。

```text
create_dated_folders.py
```

创建日期编号文件夹的辅助脚本，例如生成 `729.1`、`729.2` 这样的文件夹。

```text
copy_ads_to_dated_folders.py
```

根据 `广告素材.json` 中的资料库编号顺序，把对应图片或视频素材文件夹复制到日期编号整理目录。

```text
generate_summary.py
```

根据整理后的素材文件夹生成汇总 Markdown 文档。

```text
meta_ad_card_batch_by_ids_使用指南.md
```

按资料库编号批量抓取脚本的使用指南。

```text
dated_folder_scripts_使用指南.md
```

日期编号文件夹创建和素材复制脚本的使用指南。

## 基础使用

### 1. 按 URL 抓取广告资料库

示例：

```bash
python3 meta_ad_card_extractor.py \
  --crawl \
  --headless \
  --download-images \
  --require-hd-video \
  --scroll-rounds 30 \
  --stop-after-stable-rounds 6 \
  --wait-ms 6000 \
  --url '你的Meta广告资料库URL' \
  --asset-dir '广告素材文件' \
  --output '广告素材文件/广告素材.json' \
  --result-count-root '广告素材文件'
```

### 2. 按资料库编号批量抓取

示例：

```bash
python3 meta_ad_card_batch_by_ids.py \
  2100745807450676 \
  994592432962928 \
  --output-root '按资料库编号抓取' \
  --require-hd-video
```

脚本会自动把编号转换成类似下面的 Meta 广告资料库 URL：

```text
https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&is_targeted_country=false&media_type=all&q=资料库编号&search_type=keyword_unordered&sort_data[direction]=desc&sort_data[mode]=total_impressions
```

### 3. 复制素材到日期编号文件夹

示例：

```bash
python3 copy_ads_to_dated_folders.py \
  --json '广告素材.json' \
  --target '整理'
```

会按照 `广告素材.json` 中从上到下的资料库编号顺序，把对应素材复制成：

```text
729.1
729.2
729.3
```

这类日期编号文件夹。

## HD 视频说明

如果需要尽量抓取高清视频，请使用：

```bash
--require-hd-video
```

脚本会尝试在广告卡片中切换视频清晰度到 HD 后，再采集动态变化后的视频链接。

如果没有加这个参数，脚本可能会保存默认加载的 SD 视频。

## 上传 GitHub 的脚本

本地目录还提供两个上传脚本：

```text
upload_github_root_pr.sh
upload_github_root_force.sh
```

推荐使用 PR 版本：

```bash
cd /Users/zzh/C/similar_craw
./upload_github_root_pr.sh
```

执行成功后，终端会输出 Pull Request 创建链接。

不建议优先使用强制覆盖版本：

```bash
cd /Users/zzh/C/similar_craw
./upload_github_root_force.sh
```

因为它会使用 `--force` 覆盖 GitHub 的 `main` 分支。

## 注意事项

- Meta 广告资料库页面是动态加载页面，抓取数量受滚动次数、等待时间、网络速度和页面加载状态影响。
- 如果抓取不完整，可以适当增加 `--scroll-rounds`、`--stop-after-stable-rounds` 和 `--wait-ms`。
- 视频 HD 抓取依赖页面中清晰度按钮和视频链接的动态变化，页面结构变化时可能需要更新选择逻辑。
- 不建议把大量下载的广告素材图片、视频直接提交到 GitHub，建议只备份脚本和说明文档。
