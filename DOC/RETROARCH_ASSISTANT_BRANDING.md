# RetroArch 助手：品牌更名与兼容

中文展示名为 **RetroArch 助手**，英文为 **RetroArch Assistant**。定位为 RetroArch 游戏库与掌机管理工具：扫描游戏、整理列表、补全资料。

## 已统一的展示面

- 浏览器标题、侧栏品牌、文件选择器、退出与错误提示。
- 原创掌机／手柄与勾选图标，供网页、favicon、macOS 与 Windows 应用使用。
- 桌面可执行文件 `RetroArchAssistant`、`RetroArch Assistant.app`、DMG、Setup 与便携 ZIP 文件名。
- README、中英文操作说明、桌面指南及未来 Release 草稿配置。
- 设置入口简化为“设置”，内部提供设备与游戏库、资料来源、偏好设置、任务与恢复。

## 保留的兼容标识

- `src/plcn.py` 与 Linux `plcn` 命令。
- 仓库 URL、PLCN_HOME／PLCN_VERSION 等环境变量。
- 原 PLCN 用户数据与缓存目录、备份和恢复记录、浏览器语言与主题键。
- macOS bundle identifier `io.github.mightykartz.plcn` 与原 Windows AppId。
- Windows 原安装路径，并在新构建中提供 `PLCN.exe` 兼容入口。
- RetroArch 标准主机标识、列表字段、ROM 与核心路径，以及已有工作目录前缀。

没有自动迁移用户数据、重命名 ROM 或发布新的 Release。历史 Release 的 PLCN 文件名仍然有效；更名包将由后续发布提供。

## 验证

- 完整 Python 回归 534 项通过，Node 测试 132 项通过；最后的偏好设置交互调整另经两种浏览器视口验证通过。
- 中文、英文、1400×900 桌面与 780×900 窄窗口截图已核对，无品牌文字溢出；原偏好键与数据路径沿用。
- Apple Silicon DMG 已本机构建并验收：Info.plist、图标、包资源、镜像复制后启动、自检、同配置单实例、不同配置端口隔离与正常退出通过。
- Windows 和 Intel Mac 打包配置已同步，尚未在本机执行这两个平台的构建；由 CI 继续验收。
- 视觉与导入相关截图使用缓存副本，没有应用掌机写入。

[中文界面](design/retroarch-assistant-desktop.png) · [英文界面](design/retroarch-assistant-desktop-en.png) · [紧凑窗口](design/retroarch-assistant-compact.png) · [偏好设置](design/retroarch-assistant-preferences.png)
