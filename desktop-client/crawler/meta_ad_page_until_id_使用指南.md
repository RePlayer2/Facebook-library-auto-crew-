# meta_ad_page_until_id.py 使用指南

这个脚本用于“页面从上到下抓取”，遇到指定的资料库编号后停止。它还支持先扫描投放者，再按投放者选择抓取或排除抓取。

## 1. 先扫描投放者

```bash
cd /Users/zzh/C/similar_craw

python3 crawler/meta_ad_page_until_id.py \
  --mode scan \
  --headless \
  --url '你的Meta广告资料库URL' \
  --scroll-rounds 20 \
  --stop-after-stable-rounds 5 \
  --wait-ms 2500 \
  --output 'meta素材/投放者扫描.json'
```

扫描结果会输出类似：

```text
[投放者] 当前已发现 1 个 | Brand A
[投放者] 当前已发现 2 个 | Brand B
扫描完成：共发现 2 个投放者
```

同时会生成 JSON：

```json
[
  {
    "投放者": "Brand A",
    "投放者头像": "https://...",
    "首次资料库编号": "1234567890"
  }
]
```

## 2. 抓取直到指定资料库编号停止

```bash
cd /Users/zzh/C/similar_craw

python3 crawler/meta_ad_page_until_id.py \
  --mode crawl \
  --headless \
  --download-images \
  --require-hd-video \
  --url '你的Meta广告资料库URL' \
  --stop-library-id 1234567890123456 \
  --asset-dir 'meta素材/测试/广告素材文件' \
  --output 'meta素材/测试/广告素材.json' \
  --result-count-root 'meta素材/测试' \
  --scroll-rounds 120 \
  --stop-after-stable-rounds 8 \
  --wait-ms 2500
```

说明：

- 会按页面从上到下滚动。
- 每发现一条符合条件的卡片，会立即保存 JSON 和素材文件夹。
- 抓到 `--stop-library-id` 指定编号后停止。
- 如果目标编号前面的素材符合条件，也会被保存。

## 3. 只抓指定投放者

```bash
python3 crawler/meta_ad_page_until_id.py \
  --mode crawl \
  --headless \
  --download-images \
  --require-hd-video \
  --url '你的Meta广告资料库URL' \
  --stop-library-id 1234567890123456 \
  --include-advertiser 'Brand A' \
  --include-advertiser 'Brand B' \
  --asset-dir 'meta素材/测试/广告素材文件' \
  --output 'meta素材/测试/广告素材.json'
```

也可以逗号分隔：

```bash
--include-advertiser 'Brand A,Brand B'
```

## 4. 排除指定投放者

```bash
python3 crawler/meta_ad_page_until_id.py \
  --mode crawl \
  --headless \
  --download-images \
  --require-hd-video \
  --url '你的Meta广告资料库URL' \
  --stop-library-id 1234567890123456 \
  --exclude-advertiser 'Brand C' \
  --asset-dir 'meta素材/测试/广告素材文件' \
  --output 'meta素材/测试/广告素材.json'
```

## 5. 参数说明

| 参数 | 作用 |
| --- | --- |
| `--mode scan` | 只扫描投放者，不下载素材 |
| `--mode crawl` | 正式抓取素材 |
| `--stop-library-id` | 抓到该资料库编号后停止 |
| `--include-advertiser` | 只抓指定投放者 |
| `--exclude-advertiser` | 排除指定投放者 |
| `--download-images` | 下载图片/视频素材 |
| `--require-hd-video` | 视频尽量切换到 HD 后下载 |
| `--max-cards` | 最多保存多少条符合条件的素材 |
| `--scroll-rounds` | 最多滚动次数 |
| `--stop-after-stable-rounds` | 连续多少轮没新增后停止 |
| `--wait-ms` | 每次滚动后等待时间 |

## 6. 后续接入客户端的设计

客户端可以分两步：

1. 点击“扫描投放者”按钮：运行 `--mode scan`，把投放者列表展示成卡片。
2. 用户勾选“只抓这些投放者”或“排除这些投放者”：运行 `--mode crawl` 并传入 `--include-advertiser` 或 `--exclude-advertiser`。
