# 尚未发布：预览、设置与游戏库流程简化

## 中文更新

- 补入完整 SS Redump、SNES No-Intro 主库并保留旧补充记录，记录来源/版本/摘要；已知旧补充缓存不再遮住完整库，桌面包自检校验数据完整性。
- 修复中文名已匹配但图片仍使用缩写/汉化包名的问题。SS 预览核对三类官方图片，版本不唯一时可直接选择图片源；多盘保留盘号，避免格兰蒂亚两盘写向同名图片。
- 名称写入成功但图片失败时显示“名称完成 · 图片待补全”，可继续补图；仅图片重试不重复改名。MTP 复用已有图片，并只发布列表校验通过的目标。

- 当前主机补全简化为“一键补全 → 预览 → 确认应用 N 项”：移除重复的二次确认，摘要直接显示在预览中并随选择更新；执行期间禁用重复提交。

- 首页统一已连接与最近使用卡片的命名、状态样式和“打开游戏库”按钮；同一路径的已连接游戏库不再在最近使用中重复出现。断开后保留历史并显示“等待连接”，不会删除记录。

- 首页聚焦掌机连接，移除本地目录入口和 Android 帮助，不再自动检查本地最近记录。macOS 新增 MTP 文件传输连接：选择“文件传输”并解锁即可发现掌机、浏览列表/图片及确认后写回，无须 USB 调试；支持内部与外置存储，写入保留备份并回读校验。安装包内置 libmtp/libusb。Windows 本轮仍使用 ADB。

- 当前主机入口更名“一键补全”，旁注“自动匹配中文名与图片，预览后确认应用。”；左侧选中“全部主机”时同一按钮分析并直接补全全部主机后显示结果；选中单个主机时保留预览与确认流程。

- 核心按分析、提案、图片查找、写回和命令行批处理拆分，`playlist_service.py` 保留统一公开入口。匹配规则、提案格式、写回与备份协议保持不变；游戏列表浏览直接复用只读图片查找模块。

- 三类图片全缺时，游戏行仅显示“缺图”；部分缺失或损坏时才展开类型标签。有封面但其它类型损坏的游戏也计入“需检查”。
- 补图窗口打开后自动列出官方候选，点选即预览并定位到对比，取消重复的“预览图片”按钮。官方无结果时显示备用来源入口，备用查询和最终写入都需要手动操作；本地导入保留。
- 移除底部任务栏和旧详情抽屉，进度、处理记录、图片汇总、错误、取消和重试集中在“设置 → 任务与恢复”。运行提示可直接进入任务页；长明细滚动时仍可关闭窗口。

- 标题栏“整理本主机”直接进入预览；预览顶部用“修改名称”“补全图片”勾选框选择操作，切换后重新分析。移除右侧检查器和流程条，编辑过的行保留“记住修正”。
- 左侧主机列表顶部新增“全部主机”，打开游戏库后默认选中；右上角“一键补全”按左侧选择作用于全部主机或当前主机。全部主机一键补全分析后直接应用并列出各主机结果，可取消，无选项或确认步骤；应用的是分析时保存的提案，列表变动则拒绝处理。
- 库中没有图片目录时按 `<游戏库>/thumbnails` 处理并在首次补图时自动创建；“设置 → 游戏库”会标注“尚不存在，首次补图时自动创建”，仍可手动覆盖。
- 仅补图在本地和 ADB 上均保留 `.lpl` 文件；修复设备端仅补图仍可能回推未改名列表的问题。批量列表错误明确显示为部分完成。

- 后端接口改用按领域组织的路由表，命令行与 HTTP 服务共用独立的列表处理核心；保留现有分析与写回规则。修复打开数据目录／文件所在目录请求被旧路由截走的问题。

- 预览中的名称和图片源默认显示为文本，点击后编辑，Enter 或失焦提交、Esc 取消；每行仅保留“更换图片”，统一进入包含搜索、导入和图片预览的补图窗口。副标题只显示 ROM 文件名，完整路径保留在悬停提示中；紧凑窗口也能看到完整的五列表格。
- 顶栏管理入口统一为“设置”，包含“游戏库 / 名称数据库 / 任务与恢复”；恢复记录与任务同页，侧栏只保留“打开其他游戏库”。首页无可用设备时提供可折叠的 Android USB 调试与授权步骤。
- 本地图片下载器明确拒绝 `adb://` 目标，避免把设备 URI 误建为本地 `adb:` 目录。任务页重试仅支持本地图片，设备图片通过游戏行的补图窗口处理。
- 路径设置只需游戏库目录和可选的图片目录覆盖；列表、主机名称及默认图片目录由游戏库自动推导。手动覆盖在切换主机及重开当前库后保留，清空即可恢复自动检测；打开其他库时清除覆盖。旧配置路径仍可读取。
- 顶栏的“当前列表 / 全部列表”移入“批量整理 → 范围：当前主机 / 全部主机”，切换范围不再隐藏当前游戏列表。“当前主机”预览左侧所选列表；“全部主机”仍在一次确认后自动应用全部列表，无须逐项预览。
- 缺少图片目录时，列表顶部集中显示“指定图片目录”入口；图片列留空，不再逐行重复提示，也不计入单个游戏的“需检查”。损坏图片和读取失败仍归入“需检查”。

## English Updates

- Rename the current-system entry to Auto-complete with a short preview-before-applying explanation. With All systems selected on the left, the same button analyzes and applies to all systems, then shows the result; selecting a single system keeps the preview-then-confirm flow.

- Split the playlist core into analysis, proposals, artwork lookup, writeback and CLI batch modules while retaining the public `playlist_service.py` entry. Preserve matching rules, proposal formats, writeback and backups; browsing uses the read-only artwork module directly.

- Show one Missing mark when all artwork types are absent; expand type badges only for partial or damaged sets. Damaged secondary images count toward Check even when box art loads.
- Automatically list official artwork candidates; selecting one previews it and scrolls to the comparison. Remove the redundant Preview image button. Alternate searches and final writes remain explicit; local import stays available.
- Consolidate task progress, recent activity, image summaries, errors, cancellation and retries in Settings → Tasks & restore. Remove the old bottom dock and details drawer; keep the close control visible while scrolling.

- Organize this system opens preview directly. Rename and artwork checkboxes reanalyze on change. Remove the inspector and flow strip; edited rows retain Remember correction.
- Add an All systems row at the top of the sidebar system list, selected by default after opening a library; the top-right Auto-complete button acts on all systems or the selected system according to the sidebar selection. All-systems auto-complete analyzes, then applies directly and lists a per-system result; it can be cancelled and has no options or confirmation step. The saved analysis proposals are applied, and changed playlists are rejected.
- A library without an artwork folder uses `<library>/thumbnails`, created on first write; Settings → Library marks it as “will be created on first use”, and a manual override remains available.
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

- 新增“更新游戏库”：选择目录、主机与核心，扫描新增项并预览后合并到列表，自动备份、保存扫描配置并衔接名称与图片补全。
- 新增 Android 官方核心下载及传输入口；核对应用 ABI、ZIP 与 ELF 架构，明确区分已下载、待安装与安装状态未知。
- 支持 MTP 无已有列表时创建游戏列表、复用原列表路径与单项设置、街机 XML DAT 命名/过滤及多盘入口去重。
- 修复 macOS 无 USB 设备时将 ioreg 空输出误报为 Invalid file。
