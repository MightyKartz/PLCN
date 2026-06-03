# PLCN

GitHub 默认显示中文版 README；英文版请点击：[English README](README_EN.md)。

PLCN 是一个面向 RetroArch 用户的本地游戏列表中文化与缩略图匹配工具。它当前以 Python CLI + 本地 Web UI 的形式运行，会读取 `.lpl` 游戏列表，基于本地中文名称数据和 Libretro 数据库生成可校对的中文显示名、标准英文缩略图来源，并在确认后写回游戏列表、下载封面/截图/标题图。

> 当前实现是 RetroArch 外部的本地辅助工具，不是运行在 RetroArch 内部的插件，也不会修改 RetroArch 程序本体。

## 最新版本：v3.1.0

- 升级 PLCN v3.1 状态驱动修复工作台，区分“可自动修复 / 无需修复 / 已完成 / 需人工确认 / 重复需处理”。
- 移除逐行人工确认按钮，改为通过清晰状态、勾选队列和应用摘要决定是否写回。
- 修复完成后会即时更新当前名称、封面状态和本地/ADB 封面预览，不再依赖刷新页面。
- 优化“写入名称”和“封面源英文名”的显示与编辑逻辑，避免把英文封面源误读为中文推荐名。
- 改进封面匹配安全性：中文目录或中文当前名不再用宽松中文模糊结果覆盖文件名/DAT 线索，修复 `Snatcher.bin` 被匹配到无关英文名的问题。
- 增强 FBNeo/Arcade 本地匹配：支持 ROM 路径、zip 短名、RetroArch `crc32`、本地 zip CRC 和 DAT 校验值别名。
- 新增封面路径回写、下载汇总、FBNeo 匹配、搜索精度和 UI 状态模型回归测试。

## 主要功能

- **游戏列表中文化**：读取 RetroArch `.lpl` 文件，将游戏显示名匹配为中文名称。
- **RetroArch 目录扫描**：Web UI 可扫描本地 RetroArch 根目录、`playlists` 目录、已挂载设备目录，或已通过 ADB 授权连接的 Android 掌机/设备，列出检测到的 `.lpl` 游戏列表。
- **匹配与校对工作台**：Web UI 支持单个游戏列表和批量处理，提供预览、变更表、行级勾选、右侧详情、运行日志和真实下载结果概览。
- **智能缩略图下载**：
  - 即使 ROM 文件名或游戏列表标签为中文，也会尝试反查标准英文名称。
  - 从官方 Libretro 缩略图服务器下载 `Named_Boxarts`、`Named_Snaps`、`Named_Titles`。
  - 结合 `libretro-database` 修正常见命名差异，降低缩略图匹配失败率。
  - 对 FBNeo/Arcade 游戏会优先使用 `.lpl` 中的 ROM 路径、zip 短名、RetroArch `crc32` 字段、本地 zip 内部 CRC 和 DAT 校验值别名解析标准标题，减少街机短名导致的封面源错误。
  - 保持本地离线优先，不集成 ScreenScraper/Skraper API；匹配诊断会说明是 DAT 命中、ROM 指纹不可读，还是需要人工确认。
- **批量处理**：支持一次处理目录中的多个 `.lpl` 游戏列表。
- **本地数据缓存**：使用 SQLite 缓存翻译数据与匹配结果，减少重复解析成本。
- **跨平台打包**：通过 PyInstaller 面向 Windows、macOS 和 Linux 分发。

## 安装说明

请从 [Releases](https://github.com/MightyKartz/PLCN/releases) 页面下载对应平台的最新版本。

- **Windows**：下载 `PLCN-Windows-x64.exe`
- **macOS**：下载 `PLCN-macOS-x64.tar.gz`
- **Linux**：下载 `PLCN-Linux-x64.tar.gz`

## 使用方法

### 快速开始

1. **下载并解压**：从 [Releases](https://github.com/MightyKartz/PLCN/releases) 下载最新版本。

2. **赋予执行权限**（macOS/Linux）：

   ```bash
   # macOS，先解压 PLCN-macOS-x64.tar.gz
   chmod +x PLCN-macOS

   # Linux，先解压 PLCN-Linux-x64.tar.gz
   chmod +x PLCN-Linux
   ```

   > **macOS 安全提示**：首次运行时，如果遇到“无法打开，因为无法验证开发者”的提示，请前往 **系统设置 > 隐私与安全性**，选择允许打开。

3. **运行程序**：
   - **Windows**：双击 `PLCN-Windows-x64.exe` 或在命令行运行。
   - **macOS**：双击 `PLCN-macOS` 或在终端运行 `./PLCN-macOS`。
   - **Linux**：在终端运行 `./PLCN-Linux`。

   程序会自动在默认浏览器中打开 Web UI。

### Web UI 操作

1. **扫描设备与目录**：
   - 在左侧“设备与目录”中选择 RetroArch 根目录、`playlists` 目录，或已挂载 SD 卡/掌机中的 RetroArch 目录。
   - 点击“自动检测”可优先扫描常见本地/挂载目录；如果 Android 设备已完成 ADB 授权，也会自动识别 `/sdcard/RetroArch` 等常见路径。
   - 点击“扫描目录”后，PLCN 会检测游戏列表目录、缩略图目录和 `retroarch.cfg`，并列出发现的 `.lpl` 文件。
   - 选择一个游戏列表后，系统名、游戏列表路径和缩略图目录会自动填入并生成预览。

2. **配置目录与系统**：
   - 单项修复：也可以手动选择一个 `.lpl` 文件、对应系统（如 `Sony - PlayStation`）和缩略图保存目录。
   - 批量修复：选择包含多个 `.lpl` 文件的目录和缩略图保存目录。

3. **预览与校对**：
   - 先生成预览，检查当前名称、写入名称、封面源英文名、封面状态和修复状态。
   - 可取消勾选不准备写回的行，未勾选项不会进入应用和下载流程。
   - 对不确定项直接编辑写入名称或封面源；状态满足条件后再加入应用队列。

4. **应用与下载**：
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

# 单个游戏列表命令行处理
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
- RetroArch 目录扫描集中在 `src/retroarch_scanner.py`，当前支持本地/挂载目录浅层扫描和 ADB 授权设备扫描；SSH/SFTP 远程连接仍在后续计划中。
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
