# PLCN

PLCN 是一个专为 RetroArch 用户设计的强大工具，可以自动将播放列表中的游戏名称翻译成中文，并从官方 Libretro 服务器下载匹配的缩略图。

[English Readme](README_EN.md)

## 主要功能

- **自动翻译**：利用本地数据库将 `.lpl` 播放列表中的游戏名称自动翻译为中文。
- **智能缩略图下载**：
  - 即使文件名为中文，也能自动识别游戏的标准英文名称。
  - 从官方 Libretro 服务器下载缩略图（封面、截图、标题画面）。
  - 集成官方 `libretro-database`，自动修正常见的命名错误（例如 "Rage Racer" -> "Ridge Racer"）。
- **批量处理**：支持一次性处理文件夹中的多个播放列表。
- **Web 界面**：提供友好的网页界面，方便配置和操作。
- **跨平台**：支持 Windows、macOS 和 Linux。

## 安装说明

请从 [Releases](https://github.com/MightyKartz/PLCN/releases) 页面下载对应平台的最新版本。

- **Windows**: 下载 `PLCN-Windows.exe`
- **macOS**: 下载 `PLCN-macOS`
- **Linux**: 下载 `PLCN-Linux`

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
   
   > **macOS 安全提示**：首次运行时，如果遇到"无法打开，因为无法验证开发者"的提示，请前往**系统偏好设置 > 安全性与隐私**，点击"仍要打开"按钮。

3. **运行程序**：
   - **Windows**: 双击 `PLCN-Windows.exe` 或在命令行运行
   - **macOS**: 双击 `PLCN-macOS` 或在终端运行 `./PLCN-macOS`
   - **Linux**: 在终端运行 `./PLCN-Linux`
   
   程序会自动在默认浏览器中打开 Web 界面。

### Web 界面操作

1. **配置**：
   - **单个处理**：选择单个 `.lpl` 文件，选择对应的系统（如 `Sony - PlayStation`），并设置缩略图保存目录。
   - **批量处理**：选择包含多个 `.lpl` 文件的目录，即可批量处理所有列表。

2. **开始处理**：
   - 点击"开始运行"按钮。
   - 在浏览器窗口下方查看实时的运行日志。

## 致谢与鸣谢

特别感谢 **yingw** 提供的详尽 ROM 名称翻译数据库：
- [rom-name-cn](https://github.com/yingw/rom-name-cn)

本项目使用了 `rom-name-cn` 的数据，为成千上万的怀旧游戏提供了准确的中文翻译。
