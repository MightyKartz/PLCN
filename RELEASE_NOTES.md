# PLCN v3.2.1 光盘游戏列表修复

## 中文更新

- 修复 PS 等光盘游戏把 `.cue` 和附属 `.bin/.img` 显示成多个游戏的问题。
- 当前游戏列表和批量预览只显示同目录同名的一组光盘文件中的一条，优先显示 `.m3u` 或 `.cue`。
- 附属光盘数据文件保留在设备上，不会被删除；没有被同组描述文件引用的单独 `.bin/.img` 仍会显示。
- README 精简并移除拍摄的掌机照片，保留正式界面截图。
- 明确普通用户无需安装 Xcode、Node.js 或接受 SDK 许可；正式安装包由 GitHub Actions 构建。
- 保留 v3.2.0 的设备连接、游戏浏览、批量整理、单游戏补图和 ADB 写回校验。

## English Updates

- Fixed disc-based systems such as PlayStation showing `.cue` and companion `.bin/.img` files as multiple games.
- The current game list and batch preview now show one row for same-directory same-title disc files, preferring `.m3u` or `.cue`.
- Companion disc data files stay on the device and are not deleted. Standalone `.bin/.img` files without a descriptor still appear.
- Simplified the README and removed the photographed handheld image, keeping formal UI screenshots.
- Clarified that users do not need Xcode, Node.js, or SDK license approval; release packages are built by GitHub Actions.
- Preserves v3.2.0 device discovery, game browsing, batch repair, single-game artwork repair, and ADB write verification.
