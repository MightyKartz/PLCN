# PLCN v3.1.0 状态与封面匹配优化

## 中文更新

- 升级状态驱动修复工作台，清晰区分“可自动修复 / 无需修复 / 已完成 / 需人工确认 / 重复需处理”。
- 移除逐行人工确认按钮，改为通过状态、勾选队列和应用摘要决定是否写回。
- 修复完成后即时更新当前名称、封面状态和本地/ADB 封面预览，不再依赖刷新页面。
- 将表格字段调整为“写入名称”和“封面源英文名”，避免把英文封面源误读为推荐中文名。
- 优化中文目录和中文当前名的封面源匹配：优先使用文件名、精确别名和 Libretro DAT 线索，修复 `Snatcher.bin` 被匹配到无关英文名的问题。
- 增强 FBNeo/Arcade 本地匹配，支持 ROM 路径、zip 短名、RetroArch `crc32`、本地 zip CRC 和 DAT 校验值别名。
- 补充封面路径回写、下载汇总、FBNeo 匹配、搜索精度和 UI 状态模型回归测试。

## English Updates

- Upgraded the status-driven repair workbench with clear auto-repair, no-repair-needed, completed, review, and duplicate states.
- Removed per-row manual confirmation buttons; status labels, the selected queue, and the apply summary now drive write-back decisions.
- Current names, cover states, and local/ADB cover previews update immediately after apply without requiring a page refresh.
- Renamed table fields to “Write Name” and “Cover Source Name” so English artwork sources are not confused with recommended Chinese names.
- Hardened artwork-source matching for Chinese folders and existing Chinese labels by preferring filename, exact alias, and Libretro DAT evidence; this fixes cases like `Snatcher.bin` matching an unrelated English title.
- Improved FBNeo/Arcade local matching with ROM paths, zip short names, RetroArch `crc32`, local zip CRCs, and DAT checksum aliases.
- Added regression coverage for cover-path write-back, download summaries, FBNeo matching, search precision, and the UI status model.
