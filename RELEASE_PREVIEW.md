# RetroArch 助手：更名后桌面预览 / Desktop preview

## 中文更新

- 更名为 RetroArch 助手，使用 `retroarch-assistant` 命令、`RETROARCH_ASSISTANT_HOME` 和 `RetroArchAssistant` 数据目录。
- 提供按主机浏览、搜索、封面网格与列表、游戏详情、导入预览、增量扫描、批量移出列表和名称编辑。
- 补全名称与封面会分析后直接处理可自动应用的项；身份存疑的游戏留待人工核对。补全记录支持撤销，补全后被其它操作改动的内容会保留。
- 桌面包默认在独立窗口打开，首页显示掌机名称。设置仅保留语言、外观和退出入口；macOS MTP 改善锁屏后的会话恢复。
- 补全记录和各工具的操作记录提供失败明细、重试及恢复入口。高级工具包括多盘引用检查、M3U、CHD 副本、目录整理与恢复。

升级前退出应用，并在首次启动新版前完成[一次性数据迁移](https://github.com/MightyKartz/retroarch-assistant/blob/main/DOC/MIGRATION.md)。保留配置、人工规则、备份、恢复记录和缓存；迁移不移动设备 ROM，已有新目录不会被自动合并覆盖。

下载对应系统的 Release 附件，无需 Python、Node.js 或 Xcode。Windows/macOS 包内置 ADB；macOS 另内置 MTP 运行库。Android 连接方式及 Windows 驱动要求见 [README](https://github.com/MightyKartz/retroarch-assistant#readme)。

当前 Windows/macOS 包未做发行证书签名，macOS 未公证。自动测试不代表所有设备已验收；真实掌机的换盘、存档衔接、CHD 替换及目录移动仍需验证。请先使用副本验证高级工具，核对任务结果。

## English updates

- Rename the application, CLI and profile directories to RetroArch Assistant / `retroarch-assistant` / `RetroArchAssistant`.
- Browse and search systems, import games with a preview, scan incrementally, remove playlist entries in batches and edit display names.
- Complete names and artwork directly after analysis. Uncertain identities remain for manual review. Durable undo receipts preserve content changed by other operations after completion.
- Desktop packages open in their own window and show the handheld name. Settings contain language, appearance and exit controls; macOS MTP improves session recovery after locking.
- Find errors, retries and recovery in completion history and each tool's operation history. Advanced tools cover disc references, M3U, CHD copies and ROM organization.

Quit both versions and [migrate the existing profile](https://github.com/MightyKartz/retroarch-assistant/blob/main/DOC/MIGRATION.md) before first launching this preview. Migration keeps settings, manual rules, backups, recovery records and caches; it does not move device ROMs or merge existing destinations.

Download the matching release attachment; Python, Node.js and Xcode are unnecessary. Windows/macOS packages bundle ADB, and macOS bundles the MTP runtime. Packages are not distribution-signed; macOS is not notarized. Device gameplay, disc swapping, save continuity and advanced replacement/move operations still require hardware acceptance. Validate advanced tools using copies first.
