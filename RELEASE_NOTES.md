# v3.0.0 - PLCN 设备库工作台

## 中文更新说明

PLCN v3.0.0 把项目从“单个游戏列表修复工具”推进到“设备库扫描 + 修复预览 + 一键应用”的工作台形态。

### 主要更新

- 新增设备与目录扫描，可识别本地 RetroArch 目录、已挂载设备目录，以及已授权 ADB Android 掌机/设备中的 `/sdcard/RetroArch` 等常见路径。
- 新增游戏列表库视图，按主机缩写横向筛选，点击主机后直接显示对应游戏列表的所有游戏。
- 新增 ADB 游戏列表读取与写回基础能力：预览时会把远端 `.lpl` 拉取到本地缓存，应用时会先备份远端游戏列表再推回。
- 重构 PLCN v3.0 Web UI：左侧聚焦设备与目录，中间显示游戏库扫描和修复表格，右侧修复预览改为按需浮层，底部只保留任务进度和按需任务详情。
- 优化表格体验：增加封面缩略图、封面状态、人工确认按钮、选中态、主机缩写筛选、搜索数据库默认英文名自动搜索。
- 优化顶部工具区：中英文 UI 切换、深色/浅色主题切换改为无文字 SVG 图标，并修复切换后的图标状态。
- 优化深色模式：降低选中状态、按钮边框、状态徽章的亮度，长时间校对更耐看。
- 更新 README，GitHub 默认展示中文说明，英文 README 可通过链接打开。
- 新增设备扫描、UI 信息架构、深色主题状态等回归测试。

### 已知限制

- ADB 需要用户先在设备上完成授权；多设备选择、授权失败解释和更细的超时重试仍需继续优化。
- SSH/SFTP 连接实机尚未实现，后续会作为独立连接器设计。
- 本地封面存在性检查仍在计划中，目前 UI 已区分“待下载 / 已有封面 / 缺少封面源”的前端状态。

## English Release Notes

PLCN v3.0.0 moves the project from a single game-list repair helper toward a device-library workbench with scan, review, and one-click apply workflows.

### Highlights

- Added device and folder scanning for local RetroArch folders, mounted device folders, and authorized ADB Android handhelds/devices with common paths such as `/sdcard/RetroArch`.
- Added a game-list library view with horizontal system-abbreviation tabs. Selecting a system shows the matching game list directly.
- Added foundational ADB game-list read/write support: remote `.lpl` files are materialized into a local cache for preview, then backed up and pushed back during apply.
- Reworked the PLCN v3.0 Web UI: device/folder entry on the left, game-library scan and repair table in the center, on-demand repair preview on the right, and task progress at the bottom.
- Improved table workflows with cover thumbnails, cover status, manual confirmation, stronger selected states, system tabs, and automatic database search using the default English game name.
- Refined the top toolbar: UI language and light/dark theme toggles now use text-free SVG icons with correct icon-state switching.
- Tuned dark mode by reducing active-state brightness, button border intensity, and status badge contrast.
- Updated README so GitHub shows Chinese by default, with the English README available through a link.
- Added regression tests for device scanning, UI information architecture, and dark-theme active states.

### Known Limitations

- ADB still requires device-side authorization first. Multi-device selection, authorization diagnostics, and finer timeout/retry handling remain follow-up work.
- SSH/SFTP device connections are not implemented yet and will need a dedicated connector design.
- Local cover existence detection is still planned. The UI now distinguishes pending download, existing cover, and missing cover-source states.
