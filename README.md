# PLCN

PLCN 是一个面向 RetroArch 用户的本地播放列表中文化与缩略图匹配工具。它当前以 Python CLI + 本地 Web UI 的形式运行，会读取 `.lpl` 播放列表，基于本地中文名称数据和 Libretro 数据库生成可校对的中文显示名、标准英文缩略图来源，并在确认后写回播放列表、下载封面/截图/标题图。

> 当前实现是 RetroArch 外部的本地辅助工具，不是运行在 RetroArch 内部的插件，也不会修改 RetroArch 程序本体。

[English Readme](README_EN.md)

## 主要功能

- **播放列表中文化**：读取 RetroArch `.lpl` 文件，将游戏显示名匹配为中文名称。
- **匹配与校对工作台**：Web UI 支持单个播放列表和批量处理，提供预览、变更表、行级勾选、右侧详情、运行日志和真实下载结果概览。
- **智能缩略图下载**：
  - 即使 ROM 文件名或播放列表标签为中文，也会尝试反查标准英文名称。
  - 从官方 Libretro 缩略图服务器下载 `Named_Boxarts`、`Named_Snaps`、`Named_Titles`。
  - 结合 `libretro-database` 修正常见命名差异，降低缩略图匹配失败率。
- **批量处理**：支持一次处理目录中的多个 `.lpl` 播放列表。
- **本地数据缓存**：使用 SQLite 缓存翻译数据与匹配结果，减少重复解析成本。
- **跨平台打包**：通过 PyInstaller 面向 Windows、macOS 和 Linux 分发。

## 安装说明

请从 [Releases](https://github.com/MightyKartz/PLCN/releases) 页面下载对应平台的最新版本。

- **Windows**：下载 `PLCN-Windows.exe`
- **macOS**：下载 `PLCN-macOS`
- **Linux**：下载 `PLCN-Linux`

## 使用方法

### 快速开始

1. **下载并解压**：从 [Releases](https://github.com/MightyKartz/PLCN/releases) 下载最新版本。

2. **赋予执行权限**（macOS/Linux）：

   ```bash
   # macOS
   chmod +x PLCN-macOS

   # Linux
   chmod +x PLCN-Linux
   ```

   > **macOS 安全提示**：首次运行时，如果遇到“无法打开，因为无法验证开发者”的提示，请前往 **系统设置 > 隐私与安全性**，选择允许打开。

3. **运行程序**：
   - **Windows**：双击 `PLCN-Windows.exe` 或在命令行运行。
   - **macOS**：双击 `PLCN-macOS` 或在终端运行 `./PLCN-macOS`。
   - **Linux**：在终端运行 `./PLCN-Linux`。

   程序会自动在默认浏览器中打开 Web UI。

### Web UI 操作

1. **配置目录与系统**：
   - 单个处理：选择一个 `.lpl` 文件、对应系统（如 `Sony - PlayStation`）和缩略图保存目录。
   - 批量处理：选择包含多个 `.lpl` 文件的目录和缩略图保存目录。

2. **预览与校对**：
   - 先生成预览，检查原始名称、建议中文名、缩略图来源和匹配状态。
   - 可取消勾选不准备写回的行，未勾选项不会进入应用和下载流程。
   - 对不确定项进行人工确认后再应用变更。

3. **应用与下载**：
   - 确认后写回 `.lpl` 文件。
   - 自动下载匹配的封面、游戏截图和标题图。
   - 在进度区查看日志、成功/失败/跳过统计和下载明细。

### 从源码运行

```bash
pip install -r requirements.txt

# 无参数启动本地 Web UI
python3 src/plcn.py

# 或显式启动 Web UI
python3 src/plcn.py ui

# 单个播放列表命令行处理
python3 src/plcn.py \
  --playlist "/path/to/playlist.lpl" \
  --system "Sony - PlayStation" \
  --thumbnails-dir "/path/to/RetroArch/thumbnails"

# 批量处理目录中的 .lpl 文件
python3 src/plcn.py \
  --batch-dir "/path/to/playlists" \
  --thumbnails-dir "/path/to/RetroArch/thumbnails"
```

## 开发状态

- 当前核心链路集中在 `src/plcn.py`、`src/server.py`、`src/database.py`、`src/translator.py`、`src/libretro_db.py` 和 `src/thumbnail_downloader.py`。
- Web UI 目前位于 `src/templates/plcn.html`，是单文件模板，后续需要继续拆分和强化可维护性。
- 后续优化路线见 [DOC/OPTIMIZATION_PLAN.md](DOC/OPTIMIZATION_PLAN.md)。

常用验证命令：

```bash
python3 -m py_compile src/*.py
python3 -m pytest --collect-only -q
```

## 致谢与鸣谢

特别感谢 **yingw** 提供的详尽 ROM 名称翻译数据库：

- [rom-name-cn](https://github.com/yingw/rom-name-cn)

本项目使用了 `rom-name-cn` 的数据，为成千上万的怀旧游戏提供中文翻译基础。
