# 尚未发布：预览、设置与游戏库流程简化

## 中文更新

- 标题栏“整理本主机”直接进入预览；预览顶部用“修改名称”“补全图片”勾选框选择操作，切换后重新分析。移除右侧检查器和流程条，编辑过的行保留“记住修正”。
- “整理全部主机”独立放在左侧导航顶部，先列出各主机的改名／补图数量与读取错误，再确认应用。确认后使用同一批提案；列表在汇总后变动则要求重新生成。关闭汇总不会写入列表。
- 仅补图在本地和 ADB 上均保留 `.lpl` 文件；修复设备端仅补图仍可能回推未改名列表的问题。批量列表错误明确显示为部分完成。

- 后端接口改用按领域组织的路由表，命令行与 HTTP 服务共用独立的列表处理核心；保留现有分析与写回规则。修复打开数据目录／文件所在目录请求被旧路由截走的问题。

- 预览中的名称和图片源默认显示为文本，点击后编辑，Enter 或失焦提交、Esc 取消；每行仅保留“更换图片”，统一进入包含搜索、导入和图片预览的补图窗口。副标题只显示 ROM 文件名，完整路径保留在悬停提示中；紧凑窗口也能看到完整的五列表格。
- 顶栏管理入口统一为“设置”，包含“游戏库 / 名称数据库 / 任务与恢复”；恢复记录与任务同页，侧栏只保留“打开其他游戏库”。首页无可用设备时提供可折叠的 Android USB 调试与授权步骤。
- 本地图片下载器明确拒绝 `adb://` 目标，避免把设备 URI 误建为本地 `adb:` 目录。任务页重试仅支持本地图片，设备图片通过游戏行的补图窗口处理。
- 路径设置只需游戏库目录和可选的图片目录覆盖；列表、主机名称及默认图片目录由游戏库自动推导。手动覆盖在切换主机及重开当前库后保留，清空即可恢复自动检测；打开其他库时清除覆盖。旧配置路径仍可读取。
- 顶栏的“当前列表 / 全部列表”移入“批量整理 → 范围：当前主机 / 全部主机”，切换范围不再隐藏当前游戏列表。“当前主机”预览左侧所选列表；“全部主机”仍在一次确认后自动应用全部列表，无须逐项预览。
- 缺少图片目录时，列表顶部集中显示“指定图片目录”入口；图片列留空，不再逐行重复提示，也不计入单个游戏的“需检查”。损坏图片和读取失败仍归入“需检查”。

## English Updates

- Organize this system opens preview directly. Rename and artwork checkboxes reanalyze on change. Remove the inspector and flow strip; edited rows retain Remember correction.
- Organize all systems is a separate sidebar action. Review per-system rename/artwork counts and errors before applying the exact saved proposals. Changed playlists require a new summary; closing it writes nothing.
- Artwork-only processing preserves playlist files locally and over ADB. Fix unnecessary remote playlist pushes and report batch playlist errors as partial completion.

- Split HTTP routes by domain and share an independent playlist service with the CLI, preserving analysis and writeback rules. Restore folder-opening requests previously intercepted by the old dispatcher.

- Preview names and artwork sources are text until clicked. Enter or blur commits an edit; Escape cancels it. Each row has one Change artwork action for search, import and preview. ROM subtitles show only the filename, with full paths in tooltips; the five-column table also fits compact desktop windows.
- Consolidate management into Settings: Library / Name database / Tasks & restore. Tasks and restore history share one page, and the sidebar keeps only Open another library. Empty-device states include collapsible Android USB debugging and authorization steps.
- Reject device URIs in the local image downloader instead of creating a local `adb:` directory. Task retries support local artwork; use the game-row artwork dialog for device images.
- Path settings now expose only the library folder and an optional artwork-folder override. Systems, playlists and default artwork folders are derived from the library. Overrides survive system changes and reopening the same library; clearing an override restores detection, and opening another library clears it. Legacy paths remain readable.
- Move processing scope into Organize games: Current system / All systems. The current games remain visible when the scope changes. The current-system preview uses the selected playlist; all-system processing still automatically applies every playlist after one confirmation.
- Show one library-level artwork-folder prompt with a Choose artwork folder action. Leave unconfigured artwork cells blank and exclude missing directory setup from per-game Check counts; damaged and unreadable artwork still needs checking.

# PLCN v3.3.1 多碟显示与界面精简

## 中文更新

- 光盘游戏改为按碟显示：没有 `.m3u` 时每张碟单独一行，存在 `.m3u` 时只显示 m3u，同一张碟的 cue 与音轨文件仍然合并。此前部分多碟游戏会被错误合并或重复。
- 预览页精简为 5 列，删除独立的“写入名称”列；名称可在行内直接编辑，改名后旁注显示原名，便于核对。
- “缺图”状态的理由改为悬停提示与读屏标签；官方图库查不到时明确标注，并提示可从备用图库手动补图。
- 移除旧的名称搜索工作台窗口；列表行与检查器里的放大镜改为打开单游戏补图窗口，其中包含名称库候选与备用图库回退。
- 旧版单机配置键会在首次读取时自动迁移到新的库配置，并写回配置文件；游戏列表与图片不受影响。

## English Updates

- Disc-based games are now listed per disc: without an `.m3u`, each disc gets its own row; with an `.m3u`, only the playlist is shown. cue and track files belonging to the same disc still merge. Some multi-disc games were previously merged or duplicated incorrectly.
- The repair preview is down to 5 columns; the separate write-name column is gone. Names are edited inline, and a renamed row shows the original name beside it.
- Missing-artwork reasons moved into tooltips and accessible labels; when the official gallery has no match this is stated, with a hint that the secondary gallery can be used manually.
- The old name-search workbench is removed. The magnifier in the list and inspector now opens a single-game artwork dialog with catalog candidates and a secondary-gallery fallback.
- Legacy single-game configuration keys are migrated automatically on first read and written back; playlists and artwork are unaffected.

# PLCN v3.3.0 中文名找图与分类图片状态

## 中文更新

- 可以直接用中文游戏名搜索官方图库图片。命中后会换算英文名并在候选列表中显示中文名与匹配来源，必须手动点选确认，不会自动写入。
- 候选按可靠性分级：完全匹配 → 名称库译名 → 英文关键词 → 模糊匹配。只有更高一级没有结果时才降级；模糊结果标注匹配度，供人工判断。
- 游戏列表的图片列按“封面 / 游戏截图 / 标题图”三类分别显示 `✓ 已有`、`○ 缺少`、`! 损坏`；“缺图”筛选在任意一类缺失时命中。
- 单个游戏可以一次勾选多个类型补图。三类图片仍互相独立，更换一类不会自动修复其他类型。
- 统一了图片相关术语与提示文案；批量窗口标题改为“搜索游戏名（中/英）”。
- 本次没有配置或游戏列表格式变更，覆盖安装即可升级。

## English Updates

- Chinese titles can now be searched against the official gallery. A match is translated to its English name and the candidates show both names plus how they were found; nothing is written until you click one.
- Candidates are graded: exact → catalog translation → English keyword → fuzzy. A lower tier is only used when higher ones return nothing, and fuzzy matches display their score for manual judgement.
- The playlist image column reports 封面 / 游戏截图 / 标题图 separately with `✓ present`, `○ missing`, `! damaged`; the missing filter matches a game when any of the three is absent.
- Several artwork types can be requested for one game at once. The three types stay independent — replacing one never repairs the others.
- Unified artwork wording; the batch dialog is now “搜索游戏名（中/英）”.
- No configuration or playlist format changes; install over the previous version.
