# RetroArch 助手：品牌更名与兼容

中文展示名为 **RetroArch 助手**，英文为 **RetroArch Assistant**。定位为 RetroArch 游戏库与掌机管理工具：扫描游戏、整理列表、补全资料。

## 已统一的展示面

- 浏览器标题、侧栏品牌、文件选择器、退出与错误提示。
- 原创掌机／手柄与勾选图标，供网页、favicon、macOS 与 Windows 应用使用。
- 桌面可执行文件 `RetroArchAssistant`、`RetroArch Assistant.app`、DMG、Setup 与便携 ZIP 文件名。
- README、中英文操作说明、桌面指南及未来 Release 草稿配置。
- 设置入口简化为“设置”，内部提供设备与游戏库、资料来源、偏好设置、任务与恢复。

## 更名后的运行约定

- CLI 使用 `retroarch-assistant`，源码入口 `src/retroarch_assistant.py`。
- 数据与缓存目录改为 `RetroArchAssistant`，环境变量使用 `RETROARCH_ASSISTANT_` 前缀；不提供旧名称回退或 CLI 别名。
- 现有配置、人工规则、备份和恢复记录通过[一次性迁移](MIGRATION.md)保留。
- macOS bundle identifier 为 `io.github.mightykartz.retroarchassistant`。Windows 使用新安装目录，保留中性的安装器 GUID 以识别安装登记。
- 仓库为 `MightyKartz/retroarch-assistant`。RetroArch 标准主机标识、列表格式和设备 ROM 路径保持原格式。


## 验证

- 完整 Python 回归 534 项通过，Node 测试 132 项通过；最后的偏好设置交互调整另经两种浏览器视口验证通过。
- 中文、英文、1400×900 桌面与 780×900 窄窗口截图已核对，无品牌文字溢出；原偏好键与数据路径沿用。
- Apple Silicon DMG 已本机构建并验收：Info.plist、图标、包资源、镜像复制后启动、自检、同配置单实例、不同配置端口隔离与正常退出通过。
- Windows 和 Intel Mac 打包配置已同步，尚未在本机执行这两个平台的构建；由 CI 继续验收。
- 视觉与导入相关截图使用缓存副本，没有应用掌机写入。

[中文界面](design/retroarch-assistant-desktop.png) · [英文界面](design/retroarch-assistant-desktop-en.png) · [紧凑窗口](design/retroarch-assistant-compact.png) · [偏好设置](design/retroarch-assistant-preferences.png)

## 英文界面补充验收

- 全部存储／内部存储／存储卡、主机分类、工具菜单、扫描与工具弹窗的静态文字、占位符、悬停与辅助阅读标签均接入显式翻译标记。
- 自动扫描的进度、完成摘要和导入结果，以及手动扫描的推荐说明、安装状态与前端提示支持英文。界面翻译不会全局替换游戏名、文件路径、封面内容或底层原始诊断。
- 新增静态文案标记和英文目录完整性检查；浏览器覆盖英文菜单、扫描结果、手动配置和中英文切换。Node 134 项通过；完整回归曾发现一个旧模板结构断言，保持按钮原有结构后，相关架构、语言与两种浏览器视口的 7 项检查全部通过。
- 修正英文单复数及扫描弹窗暗色标签对比度。macOS DMG 已重新构建，并再次通过资源、自检、实例隔离与退出验收。

[英文扫描结果](design/retroarch-assistant-scan-en.png) · [英文手动添加](design/retroarch-assistant-manual-en.png)
