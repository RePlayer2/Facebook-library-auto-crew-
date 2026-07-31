# 按资料库编号批量抓取使用指南

脚本路径：

```bash
python3 crawler/meta_ad_card_batch_by_ids.py
```

这个脚本用于批量输入 Meta 广告资料库编号，然后自动把编号拼到 URL 的 `q=` 参数里，再逐个调用原来的：

```bash
crawler/meta_ad_card_extractor.py
```

原爬虫的抓取、下载、HD 视频切换、实时保存等逻辑都不变。

## 1. URL 生成规则

输入：

```text
2100745807450676
```

会生成：

```text
https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&is_targeted_country=false&media_type=all&q=2100745807450676&search_type=keyword_unordered&sort_data[direction]=desc&sort_data[mode]=total_impressions
```

输入：

```text
994592432962928
```

会生成：

```text
https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&is_targeted_country=false&media_type=all&q=994592432962928&search_type=keyword_unordered&sort_data[direction]=desc&sort_data[mode]=total_impressions
```

## 2. 直接输入多个编号

```bash
python3 crawler/meta_ad_card_batch_by_ids.py \
  2100745807450676 \
  994592432962928 \
  --require-hd-video
```

默认会输出到：

```text
meta素材/批量资料库编号抓取/2100745807450676/
meta素材/批量资料库编号抓取/994592432962928/
```

每个编号下面会有：

```text
广告素材.json
样式_抓取.html
广告素材文件/
本次返回N个结果/
```

## 3. 使用编号文件批量抓取

先创建一个文本文件，例如：

```text
ids.txt
```

内容可以一行一个：

```text
2100745807450676
994592432962928
```

运行：

```bash
python3 crawler/meta_ad_card_batch_by_ids.py \
  --ids-file ids.txt \
  --require-hd-video
```

## 4. 指定输出根目录

```bash
python3 crawler/meta_ad_card_batch_by_ids.py \
  2100745807450676 \
  994592432962928 \
  --output-root 'meta素材/鼻贴/按资料库编号抓取' \
  --require-hd-video
```

输出：

```text
meta素材/鼻贴/按资料库编号抓取/2100745807450676/
meta素材/鼻贴/按资料库编号抓取/994592432962928/
```

## 5. 先预览命令，不实际抓取

```bash
python3 crawler/meta_ad_card_batch_by_ids.py \
  2100745807450676 \
  994592432962928 \
  --dry-run
```

## 6. 只测试每个编号前 1 条

```bash
python3 crawler/meta_ad_card_batch_by_ids.py \
  2100745807450676 \
  994592432962928 \
  --max-cards 1 \
  --scroll-rounds 1 \
  --require-hd-video
```

## 7. 抓更多结果

```bash
python3 crawler/meta_ad_card_batch_by_ids.py \
  --ids-file ids.txt \
  --scroll-rounds 30 \
  --stop-after-stable-rounds 6 \
  --wait-ms 6000 \
  --require-hd-video
```

## 8. 常用参数

| 参数 | 作用 |
| --- | --- |
| `ids` | 直接传入一个或多个资料库编号。 |
| `--ids-file` | 从文件读取资料库编号。 |
| `--output-root` | 批量输出根目录。 |
| `--require-hd-video` | 要求视频切换并保存 HD。 |
| `--max-cards` | 每个编号最多保存多少条。 |
| `--scroll-rounds` | 每个编号最多滚动多少轮。 |
| `--stop-after-stable-rounds` | 连续多少轮无新增后停止。 |
| `--wait-ms` | 每轮滚动后等待毫秒数。 |
| `--dry-run` | 只打印命令，不实际执行。 |
| `--stop-on-error` | 某个编号失败后停止整个批量任务。 |
| `--no-download-images` | 只保存 JSON，不下载素材。 |

## 9. Git 提交命令

```bash
cd /Users/zzh/C/similar_craw

git add crawler/meta_ad_card_batch_by_ids.py \
  crawler/meta_ad_card_batch_by_ids_使用指南.md

git commit -m "Add batch Meta ad crawler by library IDs"

git push
```
