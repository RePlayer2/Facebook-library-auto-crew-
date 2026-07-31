# 日期编号文件夹脚本使用指南

本文档说明两个脚本的用法：

- `crawler/create_dated_folders.py`：批量创建当天日期编号文件夹。
- `crawler/copy_ads_to_dated_folders.py`：按 `广告素材.json` 顺序，把抓取到的素材文件夹复制到当天日期编号文件夹。

## 1. 日期编号规则

两个脚本都使用当天日期作为编号前缀：

```text
月份 + 日期
```

例如：

```text
2026年7月29日 -> 729
```

对应文件夹：

```text
729.1
729.2
729.3
```

## 2. 批量创建空编号文件夹

脚本：

```bash
python3 crawler/create_dated_folders.py
```

### 2.1 在默认目录创建

默认目录是：

```text
/Users/zzh/C/similar_craw/meta素材/防滑垫
```

创建 10 个当天编号文件夹：

```bash
python3 crawler/create_dated_folders.py 10
```

如果当天是 2026年7月29日，会创建：

```text
729.1
729.2
729.3
...
729.10
```

### 2.2 指定目标目录

```bash
python3 crawler/create_dated_folders.py 10 'meta素材/鼻贴/HD单卡测试729/整理'
```

也可以使用 `--target`：

```bash
python3 crawler/create_dated_folders.py 10 \
  --target 'meta素材/鼻贴/HD单卡测试729/整理'
```

### 2.3 已存在文件夹会怎样

如果目标文件夹已经存在，脚本会跳过，不会覆盖。例如 `729.1` 已存在，则会显示跳过。

## 3. 按广告素材 JSON 顺序复制素材

脚本：

```bash
python3 crawler/copy_ads_to_dated_folders.py
```

这个脚本用于读取爬虫生成的 `广告素材.json`，按 JSON 从上到下的顺序读取每条广告的 `资料库编号`，然后在源素材目录的 `图片/视频` 子目录里查找文件夹名包含该编号的素材文件夹，并复制到整理目录。

例如 JSON 顺序是：

```json
[
  { "资料库编号": "1929541504431807" },
  { "资料库编号": "2006807903279406" },
  { "资料库编号": "578501710010389" }
]
```

复制结果会是：

```text
1929541504431807 -> 729.1
2006807903279406 -> 729.2
578501710010389  -> 729.3
```

### 3.1 复制前三条测试数据

```bash
python3 crawler/copy_ads_to_dated_folders.py \
  --json 'meta素材/鼻贴/HD前三条测试/广告素材.json' \
  --target 'meta素材/鼻贴/HD单卡测试729/整理' \
  --limit 3
```

### 3.2 先预览，不实际复制

建议正式复制前先执行 `--dry-run`：

```bash
python3 crawler/copy_ads_to_dated_folders.py \
  --json 'meta素材/鼻贴/HD前三条测试/广告素材.json' \
  --target 'meta素材/鼻贴/HD单卡测试729/整理' \
  --dry-run
```

输出会显示每条资料库编号对应的源文件夹和目标文件夹。

### 3.3 正式复制全部素材

```bash
python3 crawler/copy_ads_to_dated_folders.py \
  --json 'meta素材/鼻贴/HD前三条测试/广告素材.json' \
  --target 'meta素材/鼻贴/HD单卡测试729/整理'
```

### 3.4 指定编号前缀

如果你不想使用当天日期，可以手动指定前缀：

```bash
python3 crawler/copy_ads_to_dated_folders.py \
  --json 'meta素材/鼻贴/HD前三条测试/广告素材.json' \
  --target 'meta素材/鼻贴/HD单卡测试729/整理' \
  --prefix 729
```

### 3.5 指定起始编号

从 `729.20` 开始复制：

```bash
python3 crawler/copy_ads_to_dated_folders.py \
  --json 'meta素材/鼻贴/HD前三条测试/广告素材.json' \
  --target 'meta素材/鼻贴/HD单卡测试729/整理' \
  --prefix 729 \
  --start-index 20
```

### 3.6 覆盖已有编号文件夹

如果你想从 `729.1` 重新覆盖复制：

```bash
python3 crawler/copy_ads_to_dated_folders.py \
  --json 'meta素材/鼻贴/HD前三条测试/广告素材.json' \
  --target 'meta素材/鼻贴/HD单卡测试729/整理' \
  --prefix 729 \
  --start-index 1 \
  --overwrite
```

注意：`--overwrite` 会删除同名目标文件夹后再复制，请谨慎使用。

### 3.7 指定源素材根目录

通常不需要传 `--source-root`，脚本会根据 JSON 里的 `素材文件夹` 自动推断。

如果 JSON 里没有 `素材文件夹`，可以手动指定源素材根目录：

```bash
python3 crawler/copy_ads_to_dated_folders.py \
  --json 'meta素材/鼻贴/HD前三条测试/广告素材.json' \
  --source-root 'meta素材/鼻贴/HD前三条测试' \
  --target 'meta素材/鼻贴/HD单卡测试729/整理'
```

源素材根目录下面通常包含：

```text
图片/
视频/
广告素材.json
```

## 4. 常用组合流程

### 4.1 先抓取前三条广告素材

```bash
python3 crawler/meta_ad_card_extractor.py \
  --crawl \
  --headless \
  --download-images \
  --require-hd-video \
  --max-cards 3 \
  --scroll-rounds 1 \
  --stop-after-stable-rounds 1 \
  --wait-ms 2000 \
  --url '你的广告库URL' \
  --asset-dir 'meta素材/鼻贴/HD前三条测试' \
  --output 'meta素材/鼻贴/HD前三条测试/广告素材.json' \
  --result-count-root 'meta素材/鼻贴/HD前三条测试'
```

### 4.2 再按 JSON 顺序复制到整理目录

```bash
python3 crawler/copy_ads_to_dated_folders.py \
  --json 'meta素材/鼻贴/HD前三条测试/广告素材.json' \
  --target 'meta素材/鼻贴/HD单卡测试729/整理' \
  --limit 3
```

## 5. Git 上传命令

只提交这两个脚本和本使用指南：

```bash
cd /Users/zzh/C/similar_craw

git status

git add crawler/create_dated_folders.py
git add crawler/copy_ads_to_dated_folders.py
git add crawler/dated_folder_scripts_使用指南.md

git commit -m "Add dated folder organization scripts and guide"

git push
```

如果还没有绑定 GitHub 远程仓库：

```bash
git remote add origin https://github.com/你的用户名/你的仓库名.git
git branch -M main
git push -u origin main
```

## 6. 注意事项

- 不建议把下载的图片、视频素材一起上传 GitHub。
- 提交前先运行 `git status`，确认只包含脚本和说明文件。
- 如果你已经把素材文件夹加入 Git 暂存区，可以用 `git restore --staged 路径` 取消暂存。
