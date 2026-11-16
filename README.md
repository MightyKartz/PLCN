# RetroArch 助手

[English](README_EN.md) · [下载安装包](https://github.com/MightyKartz/PLCN/releases/latest)

RetroArch 游戏库与掌机管理工具。扫描游戏、整理列表、补全资料，管理你的掌机游戏库。双击启动，在浏览器中管理本地、SD 卡或 USB Android 掌机上的游戏库，无需安装 Python、Node.js 或 Xcode。

## 主要功能

- 按主机浏览游戏，支持真实封面、搜索和存储范围筛选。
- 增量扫描保留已有名称和核心，排除 BIOS 与内部支持 ROM。
- 补全名称、封面、截图与标题图，展示失败明细并支持重试。
- 提供多盘列表、CHD 转换、ROM 整理与操作恢复。

![RetroArch 助手](DOC/design/retroarch-assistant-desktop.png)

## 下载与启动

以下为更名后构建的文件名。历史 Release 仍使用 PLCN 前缀，旧安装继续兼容；新的更名安装包尚未发布。

请下载 **Release 附件中的安装包**，不要下载 Source code。公开下载无需 GitHub 账号。

| 系统 | 文件 | 启动方式 |
|---|---|---|
| Windows 10/11 x64 | `RetroArchAssistant-Windows-x64-Setup.exe` | 双击安装，从开始菜单打开 |
| Windows 便携版 | `RetroArchAssistant-Windows-x64-Portable.zip` | 完整解压，双击 `RetroArchAssistant.exe` |
| Mac M 系列 | `RetroArchAssistant-macOS-arm64.dmg` | 打开，拖入“应用程序”，启动 RetroArch 助手 |
| Mac Intel | `RetroArchAssistant-macOS-x64.dmg` | 同上 |
| Linux x64（命令行） | `RetroArchAssistant-Linux-x64.tar.gz` | 解压，运行 `./plcn --help` |

**当前 GitHub 自动构建的 macOS / Windows 包未做发行证书签名，macOS 未公证。** 首次打开可能被系统拦截；请先核对下载来源，再按 [Apple 官方说明](https://support.apple.com/102445) 或 [Windows 安全说明](https://support.microsoft.com/en-us/windows/security/threat-malware-protection/smart-app-control-frequently-asked-questions)处理。企业策略或 Smart App Control 可能阻止运行，不建议关闭系统防护。

从 v3.2.5 起，Windows / macOS 安装包内置 ADB，无需另装命令行工具。连接 Android 掌机仍需开启 USB 调试，并在掌机上允许此电脑；部分 Windows 设备需要厂商 USB 驱动。本地目录和 SD 卡不需要 ADB。

## 使用

1. 打开已连接掌机、存储卡或本地 RetroArch 游戏库。
2. 点击 **扫描新增游戏**，自动发现支持的主机目录，预览后增量生成游戏列表。
3. 点击 **补全名称与封面** 处理已有列表；需要自行指定目录、主机或核心时选择 **手动添加**。
4. 在“工具”中检查多盘引用、转换 CHD、整理目录或创建 ROM ZIP 副本。写入前退出 RetroArch。
5. 右上角任务图标可查看进度、失败重试、取消与恢复记录；点击设备名称查看详情或切换游戏库，设置中可管理资料来源、语言与外观。

图片优先搜索 Libretro 官方图库；无结果时可选择备用来源或本地图片。备用图片显示来源和版本提示，预览确认后才写入。

同一光盘的 CUE/BIN 等重复入口会在相应写回操作中清理，ROM 文件不会删除。不同光盘和版本不会仅因中文名相同而删除。修改有备份与读回校验；请在写入前退出 RetroArch，避免它用内存中的旧列表覆盖修改。

配置、缓存及恢复数据保存在本机。图库搜索和图片下载需要联网，不上传 ROM。更多说明见 [使用指南](DOC/DESKTOP_GUIDE.md)。

## 更名与兼容

产品展示名改为 RetroArch 助手。仓库地址、`plcn` 命令、`PLCN_HOME`、应用识别码及原有 PLCN 数据／缓存目录继续兼容，设置、备份、恢复记录和浏览器语言／主题偏好直接沿用，无需迁移。RetroArch 列表格式、主机标识和 ROM 路径不变。

## 开发

```sh
pip install -r requirements.txt
python3 src/plcn.py
```

```sh
python3 -m pytest -q
python3 scripts/check_ui_js.py
```

桌面包由 GitHub Actions 在对应系统构建并检查。自动检查覆盖资源、内置 ADB、服务启动、实例隔离和安装卸载；不等同于所有系统安全策略或所有 USB 设备均已人工验证。

感谢 [rom-name-cn](https://github.com/yingw/rom-name-cn) 与 [Libretro](https://www.libretro.com/)。ADB 的第三方许可随安装包保留在 `platform-tools/NOTICE.txt`。
