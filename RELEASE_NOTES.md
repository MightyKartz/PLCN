# PLCN v3.2.0 设备游戏库工作台

## 中文更新

- 新的本地欢迎页会列出已连接 Android 设备、最近使用和本地游戏库目录，启动时不再因自动扫描卡住。
- 选择主机后直接浏览当前游戏列表，显示封面、游戏名称、ROM 文件名，并支持搜索、缺图与需检查筛选。
- 单游戏补图可自动识别英文名并搜索 Libretro 官方图库，也可导入本地图片；写入前预览，替换旧图时自动备份。
- 图片读取和写入按 RetroArch 的 ROM 文件名优先规则同步，避免改名后 PLCN 与掌机内显示不一致。
- 支持为共用图片名称的游戏设置独立名称；不再共用后也可单独改名，列表写入前会创建备份。
- 批量整理保留在右上角菜单中；任务取消、下载失败和部分完成状态区分得更清楚。
- 修复 ADB 识别、PCE 官方图库名称显示、压缩包内 ROM 文件名展示和切换列表后的路径恢复问题。
- 写回继续使用协作锁、快照检查、备份、原子替换和读回验证；ADB 写入暂存并校验远端内容。
- 桌面预览 CI 构建 Windows 安装包/便携 ZIP、macOS Intel 与 Apple Silicon DMG；产物仍为未签名预览。

## English Updates

- The new home page lists connected Android devices, recent folders, and local game-library directories without blocking startup on an automatic scan.
- Selecting a system opens its current game list directly, with artwork, playlist names, ROM filenames, search, and missing/problem image filters.
- Single-game artwork repair can identify an English title and search the official Libretro library, or import a local image. It previews before writing and backs up replaced artwork.
- Artwork lookup and updates follow RetroArch's ROM-filename-first local matching order so PLCN and the handheld show the same image after renaming.
- Games sharing one artwork name can receive independent playlist labels; non-shared entries can also be renamed from the artwork dialog. Playlist writes are backed up.
- Batch repair moved into the top-right Organize menu, and task cancellation, failed downloads, and partial completion are reported distinctly.
- Fixed ADB detection, PCE official-library title lookup, archive-member ROM filename display, and thumbnail-path recovery after returning to the game list.
- Writes keep cooperative locks, snapshot checks, backups, atomic replacement, and readback verification. ADB writes stage and verify remote files.
- Desktop preview CI builds a Windows installer/portable ZIP and macOS Intel/Apple Silicon DMGs. These artifacts remain unsigned previews.
