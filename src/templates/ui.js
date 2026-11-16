/* Display preferences, translations and shared presentation helpers. */
let currentUILanguage = 'zh';
let currentTheme = 'light';

const UI_EN = {
    '图片目录或主机无效': 'Invalid artwork folder or system',
    '名称编辑请使用本地或 MTP 图片目录': 'Use a local or MTP artwork folder to edit names',
    '图片目录必须属于当前掌机': 'The artwork folder must belong to the current handheld',
    '无法检查原图片：': 'Cannot check existing artwork: ',
    '图片超过 8 MiB，请先调整大小：': 'Artwork exceeds 8 MiB. Resize it first: ',
    '新名称已有不同图片，请选择其他名称：': 'The new name has different artwork. Choose another name: ',
    '修改游戏名称': 'Edit game name',
    '请填写有效游戏名称（最多 300 字）': 'Enter a valid game name (up to 300 characters)',
    '目标目录不能位于来源目录内部': 'The destination cannot be inside the source folder',
    '目标子目录包含指向外部的符号链接：': 'Destination subfolder links outside the selected folder: ',
    '＋ 添加游戏': '＋ Add games',
    '导入游戏': 'Import games',
    '移出列表': 'Remove from playlist',
    '预览游戏管理操作': 'Preview game management',
    '更新游戏库': 'Update game library',
    '请选择主机和目标目录': 'Choose a system and destination folder',
    '请选择电脑上的游戏文件或目录': 'Choose game files or a folder on your computer',
    '掌机启动目录无效': 'Invalid Android launch folder',
    '目标目录必须属于当前掌机': 'The destination must belong to the current handheld',
    '请填写掌机实际游戏目录，例如 /storage/卡号/Roms/GBA': 'Enter the Android game folder, for example /storage/CARD-ID/Roms/GBA',
    '导入请使用本地目录或 MTP 连接': 'Use a local folder or an MTP connection for importing',
    'RetroArch 目录不存在': 'The RetroArch folder does not exist',
    '来源必须是电脑上的文件或目录': 'The source must be a file or folder on your computer',
    '游戏列表字段无效': 'Invalid playlist fields',
    '请选择本地或 MTP 游戏列表': 'Choose a local or MTP playlist',
    '请选择要移出列表的游戏': 'Select the games to remove from the playlist',
    '列表已变化，请重新读取后选择游戏': 'The playlist changed. Reload it before selecting games',
    '游戏条目不存在，请重新读取列表': 'The entry no longer exists. Reload the playlist',
    '列表已变化，请重新预览': 'The playlist changed. Preview again',
    '来源不存在或为符号链接：': 'Source missing or a symbolic link: ',
    '来源包含符号链接，请先移出：': 'Remove the symbolic link from the source first: ',
    '所选来源中有同名目标，请分开导入：': 'Sources have the same destination name. Import them separately: ',
    '请将 CCD/TOC 转为 CHD 或选择 CUE 后导入：': 'Convert CCD/TOC to CHD or import a CUE file: ',
    '光盘描述文件超过 1 MiB：': 'Disc descriptor exceeds 1 MiB: ',
    '无法解析光盘引用：': 'Cannot parse disc references: ',
    '光盘引用必须位于所选来源目录内：': 'Disc references must stay inside the selected source folder: ',
    '来源已变化，请重新预览：': 'Source changed. Preview again: ',
    '自动匹配中文名与图片，预览后确认应用。': 'Match Chinese names and artwork automatically; preview before applying.',
    '查看任务': 'View tasks',
    '一键补全': 'Auto-complete',
    '修改名称': 'Rename games',
    '补全图片': 'Complete artwork',
    '选项变化后重新分析': 'Changing options reanalyzes the list',
    '需手动处理': 'Needs manual work',
    '结果': 'Result',
    '查看任务明细': 'View task details',
    '关闭': 'Close',

    "设置": "Settings",
    "设备与游戏库": "Device & library",
    "资料来源": "Data sources",
    "偏好设置": "Preferences",
    "界面语言": "Interface language",
    "外观": "Appearance",
    "浅色": "Light",
    "深色": "Dark",
    "语言与外观偏好会自动保存。": "Language and appearance preferences are saved automatically.",
    "游戏库": "Library",
    "退出 RetroArch 助手": "Quit RetroArch Assistant",
    "助手": "Assistant",
    "主机分类": "Systems",
    "全部存储": "All storage",
    "内部存储": "Internal",
    "存储卡": "SD card",
    "更换图片": "Change artwork",
    "Android 掌机连接帮助": "Connect an Android handheld",
    "在掌机的设置中找到关于设备，连续点击版本号 7 次，开启开发者选项。": "In device settings, open About device and tap Build number seven times to enable Developer options.",
    "在开发者选项中打开 USB 调试，用支持数据传输的 USB 线连接电脑。": "Enable USB debugging in Developer options, then connect to the computer with a data-capable USB cable.",
    "解锁掌机，在允许 USB 调试的弹窗中授权这台电脑。": "Unlock the handheld and allow USB debugging for this computer when prompted.",
    "回到这里点击重新检测；也可以直接打开电脑或 SD 卡上的本地目录。": "Return here and refresh. You can also open a local folder on your computer or SD card.",
    "不同 Android 系统的设置名称可能略有不同。": "Setting names can differ between Android devices.",
    "Android 官方调试说明": "Official Android debugging guide",

    '范围': 'Scope',
    '当前主机': 'Current system',
    '全部主机': 'All systems',
    '处理全部主机': 'Process all systems',
    '处理游戏库中的全部主机，自动应用已识别的名称和图片源。': 'Process all systems in this library and automatically apply identified names and artwork sources.',
    '游戏库目录': 'Library folder',
    '图片目录（可选覆盖）': 'Artwork folder (optional override)',
    '留空使用游戏库自动检测的目录': 'Leave empty to use the detected library folder',
    '留空时跟随游戏库；手动覆盖会用于当前库的所有主机。': 'Leave empty to follow the library. An override applies to every system in this library.',
    '指定图片目录': 'Choose artwork folder',
    "选择左侧列表，然后预览名称与图片变更。": "Choose a list on the left, then preview name and artwork changes.",
    "整理你的 RetroArch 游戏库": "Organize your RetroArch library",
    "先预览名称与图片变更，确认后再应用。": "Preview name and artwork changes before applying.",
    "支持 RetroArch、SD 卡或 playlists 目录。": "Choose a RetroArch, SD card or playlists folder.",
    "手动选择文件或路径": "Choose a file or path manually",
    "当前游戏库": "Current library",
    "管理": "Manage",
    "主机": "Systems",
    "更换目录": "Change folder",
    "路径设置": "Path settings",
    "选择游戏库": "Choose library",
    "应用变更": "Apply changes",
    "可应用": "Ready to apply",
    "任务与恢复": "Tasks & restore",
    "工具": "Tools",
    "完成": "Done",
    "自定义数据路径": "Custom data paths",
    "浏览": "Browse",
    "处理全部列表": "Process all lists",
    "处理此目录中的全部列表，自动应用已识别的名称和图片源。": "Process every list in this folder using the identified names and artwork sources.",
    "关闭": "Close",

    "数据库": "Database",
    "任务": "Tasks",
    "恢复": "Restore",
    "退出": "Quit",
    "选择游戏目录": "Choose game folder",
    "继续上次目录": "Continue previous library",
    "本次操作": "Operation",
    "修复名称并补全图片": "Repair names and artwork",
    "仅修复名称": "Names only",
    "仅补全图片（保留当前名称）": "Artwork only (keep names)",
    "高级配置与手动路径": "Advanced configuration",
    "名称数据库": "Name database",
    "恢复历史": "Restore history",
    "RetroArch 助手管理": "RetroArch Assistant management",
    "匹配依据": "Match evidence",

    '当前列表': 'Current list',
    '全部列表': 'All lists',
    '本地数据库': 'Local DB',
    '设备与目录': 'Device & Paths',
    '连接目标': 'Target',
    '自动检测': 'Auto Detect',
    '扫描目录': 'Scan Path',
    '目录详情': 'Directory Details',
    '游戏列表目录': 'Game List Directory',
    '封面缩略图目录': 'Thumbnail Directory',
    '配置文件': 'Config File',
    '检测到的游戏列表': 'Detected Game Lists',
    '扫描后显示 .lpl 游戏列表': 'Scan to show .lpl game lists',
    '扫描后按主机名称显示 .lpl 游戏列表': 'Scan to show .lpl game lists grouped by system',
    '未命名主机': 'Unnamed System',
    '修复流程': 'Repair Flow',
    '扫描设备': 'Scan Device',
    '选择游戏列表': 'Choose Game List',
    '生成修复计划': 'Build Repair Plan',
    '修复并下载': 'Apply & Download',
    '先确认低置信匹配': 'Review low-confidence matches first',
    '当前': 'Current',
    '写入 playlist，下载三类缩略图': 'Write playlist and download three thumbnail types',
    '等待': 'Waiting',
    '单项配置': 'Single Config',
    '游戏列表路径': 'Game List Path',
    '系统名称': 'System',
    '缩略图保存路径': 'Thumbnail Save Path',
    '缩略图目录': 'Thumbnail Directory',
    'rom-name-cn 路径': 'rom-name-cn Path',
    '自动使用高置信度结果': 'Use high-confidence matches automatically',
    '下载缺失的封面和截图': 'Download missing covers and screenshots',
    '优先使用本地数据库': 'Prefer local database',
    '处理重复条目时自动重命名': 'Auto-rename duplicates when processing',
    '预览校对': 'Preview',
    '预览后应用': 'Preview & Apply',
    '批量配置': 'Batch Config',
    '每个 playlist 自动备份': 'Back up each playlist',
    '批量下载三类缩略图': 'Download all thumbnail types',
    '开始批量处理': 'Start Batch',
    '游戏库扫描': 'Game Library Scan',
    '全部': 'All',
    '可自动修复': 'Auto Repair',
    '待补充信息': 'Missing information',
    '重复需处理': 'Duplicates',
    '无需修复': 'No Repair Needed',
    '已就绪': 'Ready',
    '仅下载封面': 'Download Cover Only',
    '仅改中文名': 'Rename Only',
    '已完成': 'Completed',
    '缺封面源': 'Missing Cover',
    '图片待处理': 'Artwork needs attention',
    '已手动编辑': 'Edited',
    '缺少中文名': 'Missing Chinese name',
    '名称未变化': 'Name unchanged',
    '低置信匹配': 'Low-confidence match',
    '发现重复条目': 'Duplicate entry found',
    '待保存本地修正': 'Pending local correction save',
    '后端状态缺失': 'Backend status missing',
    '本地修正规则已保存': 'Local correction saved',
    '本地修正规则已保存，重新预览后应用': 'Local correction saved; preview again before applying',
    '保存为本地修正规则': 'Save Local Correction',
    '中文名、封面源和封面已就绪': 'Chinese name, cover source, and cover are ready',
    '中文名和封面源已就绪，仅需下载封面': 'Chinese name and cover source are ready; only cover download is needed',
    '封面已存在，仅需写入中文名': 'Cover exists; only display name needs writing',
    '将写入中文名并下载封面': 'Will write Chinese name and download cover',
    '已有封面 · 缺源': 'Cover exists · Missing source',
    '无需处理': 'No action needed',
    '当前：无需处理': 'Current: no action needed',
    '名称和封面可写入': 'Name and cover are ready',
    '后端建议需复核': 'Backend marked for review',
    '预览变更': 'Preview Changes',
    '应用已选修复': 'Apply Selected',
    '准备应用修复': 'Ready to apply repairs',
    '确认应用': 'Confirm Apply',
    '取消': 'Cancel',
    '已取消应用': 'Apply cancelled',
    '将写回游戏列表': 'Will write to game list',
    '将下载封面': 'Will download covers',
    '跳过下载': 'Downloads skipped',
    '重复项': 'duplicates',
    '筛选': 'Filter',
    '搜索游戏名 / rom 名称': 'Search game / ROM name',
    '选择游戏列表后开始预览': 'Choose a game list to preview',
    'RetroArch 助手会先展示写入名称、封面源和匹配状态，低置信结果可在右侧手动校对。': 'RetroArch Assistant shows the name to write, cover source, and match status. Low-confidence results can be reviewed on the right.',
    '游戏名称': 'Game Name',
    '修复状态': 'Status',
    '封面源英文名': 'Cover Source Name',
    '封面状态': 'Cover',
    '修复预览': 'Repair Preview',
    '匹配详情': 'Match',
    '元数据': 'Metadata',
    '文件信息': 'File',
    '文件名': 'File',
    '中文库（rom-name-cn）': 'Chinese DB (rom-name-cn)',
    'DAT（Libretro）': 'DAT (Libretro)',
    '缩略图 URL': 'Thumbnail URL',
    '显示名称（将写入游戏列表）': 'Display Name (written to game list)',
    '封面源': 'Cover Source',
    '匹配置信度': 'Match Confidence',
    '打开封面文件夹': 'Open Cover Folder',
    '任务进度': 'Task Progress',
    '任务详情': 'Task Details',
    '日志和下载明细按需查看。': 'Logs and download details are available on demand.',
    '任务日志': 'Task Logs',
    '清空日志': 'Clear Logs',
    '等待任务开始，处理日志会显示在这里。': 'Logs will appear here after a task starts.',
    '下载汇总': 'Download Summary',
    '刷新下载明细': 'Refresh Download Details',
    '下载官方封面': 'Download Covers',
    '加载中': 'Loading',
    '未就绪': 'Not ready',
    '读取失败': 'Failed',
    '未检测': 'Not detected',
    '就绪': 'Ready',
    '待处理': 'Idle',
    '等待预览校对': 'Waiting for preview',
    '当前：未开始': 'Current: not started',
    '已选 0 项 · 等待游戏库': 'Selected 0 · Waiting for library',
    '等待扫描 RetroArch 目录': 'Waiting to scan RetroArch directory',
    '等待选择 .lpl 文件': 'Waiting for .lpl file',
    '等待生成修复计划': 'Waiting to build repair plan',
    '请选择系统...': 'Choose system...',
    '系统：': 'System: ',
    '待补充': 'Missing information',
    '待确认': 'Missing information',
    '待应用': 'Ready',
    '已分析': 'Analyzed',
    '当前：等待人工确认': 'Current: waiting for review',
    '项待补充信息': 'need information',
    '项可应用': 'ready to apply',
    '已选': 'Selected',
    '项': 'items',
    '等待游戏库': 'Waiting for library',
    '待下载': 'Pending Download',
    '已有封面': 'Cover Exists',
    '已下载': 'Downloaded',
    '下载失败': 'Download Failed',
    '已跳过下载': 'Download Skipped',
    '缺少封面源': 'Missing Cover Source',
    '本地': 'Local',
    '未命名': 'Untitled',
    '留空则不下载': 'Leave empty to skip download',
    '没有符合当前筛选条件的项目。': 'No items match the current filters.',
    'UI：中文': 'UI: Chinese',
    '切换界面语言': 'Switch UI language',
    '切换到英文界面': 'Switch to English UI',
    '切换到中文界面': 'Switch to Chinese UI',
    '切换浅色/深色主题': 'Switch light/dark theme',
    '切换到深色模式': 'Switch to dark mode',
    '切换到浅色模式': 'Switch to light mode',
    '已切换界面语言': 'UI language changed',
    '已反选': 'Inverted',
    '浅色模式已开启': 'Light mode enabled',
    '深色模式已开启': 'Dark mode enabled',
    '浅色': 'Light',
    '深色': 'Dark',
    '修复完成': 'Repair complete',
    '已写入 playlist': 'Written to playlist',
    '项已写回': 'items written',
    '扫描中': 'Scanning',
    '正在扫描 RetroArch 目录': 'Scanning RetroArch directory',
    '当前：读取 playlists': 'Current: reading playlists',
    '已扫描': 'Scanned',
    '未找到': 'Not found',
    '扫描失败': 'Scan failed',
    '无法扫描 RetroArch 目录': 'Unable to scan RetroArch directory',
    '成功': 'success',
    '失败': 'failed',
    '跳过': 'skipped'
};


// App-owned static labels; game names, paths and source data are never translated.
Object.assign(UI_EN, {
    "Android ARM 32 位": "Android ARM 32-bit",
    "Android ARM 64 位": "Android ARM 64-bit",
    "Android x86 32 位": "Android x86 32-bit",
    "Android x86 64 位": "Android x86 64-bit",
    "CHD 回传与替换": "Transfer and replace CHD files",
    "M3U 文件名": "M3U filename",
    "MTP 无法验证应用私有目录，填写路径不代表已安装。请先在 RetroArch 中确认核心可用。": "MTP cannot inspect private app folders. A path does not confirm installation. Check that the core is available in RetroArch first.",
    "RetroArch 应用架构": "RetroArch app architecture",
    "一键补全 · 全部主机": "Complete all systems",
    "上一级": "Parent folder",
    "下载来源：Libretro 官方 Buildbot。请选择 RetroArch 应用的架构（不是仅看掌机 CPU）。下载不会自动安装或替换现有核心。": "Source: official Libretro Buildbot. Select the RetroArch app architecture, which may differ from the device CPU. Downloading does not install or replace cores.",
    "与所选核心及 ROM 集匹配的 XML DAT": "XML DAT matching the selected core and ROM set",
    "主机": "System",
    "主机名称.lpl": "System name.lpl",
    "主机平铺目标目录": "System destination folder",
    "仅保存 M3U，保留当前列表": "Save M3U only; keep the current playlist",
    "仅加入 DAT 中匹配的游戏": "Only add games matched by the DAT",
    "仅回传 CHD，保留原文件与引用": "Transfer CHD only; keep originals and references",
    "仅复制到目标，保留原文件与引用": "Copy only; keep originals and references",
    "从 RetroArch 核心信息核对；复制模式可留空": "Check RetroArch core information; optional for copy-only mode",
    "从现有列表找到以下路径，请核对它是否对应刚选的本机或存储卡目录。": "These paths were found in existing playlists. Check that the selected path matches your local or SD card folder.",
    "任务中心": "Task center",
    "传到掌机待安装": "Transfer for installation",
    "使用所选路径": "Use selected path",
    "使用本机 MAME chdman，不自动下载或分发。": "Uses the local MAME chdman tool; it is not downloaded or distributed automatically.",
    "使用此目录": "Use this folder",
    "例如 /storage/4A21-0000/Roms/SS": "For example: /storage/4A21-0000/Roms/SS",
    "保存 M3U 并更新当前列表": "Save M3U and update the current playlist",
    "保留原即时存档，不迁移；切换后从游戏内存档继续": "Keep save states in place; resume from an in-game save after switching",
    "候选分组": "Candidate groups",
    "先仅复制，再在 RetroArch 中使用目标文件验证运行、游戏内存档及所需换盘。更新引用时保留名称、人工核心和图片选择；原存档与即时存档不移动。": "Copy first, then test the destination in RetroArch, including in-game saves and disc changes. Updating references preserves names, assigned cores and artwork. Saves and save states are not moved.",
    "先分析目录与冲突，再单独预览整理或 ZIP 回传方案。默认仅复制，更新引用与清理需核对存档、运行报告及备份。": "Analyze folders and conflicts, then preview organization or ZIP transfer separately. Copy-only is the default; reference updates and cleanup require save, runtime and backup checks.",
    "先采用“仅回传”，在掌机原核心中加载这些 CHD，验证游戏内存档与所需换盘。以下为用户运行报告，MTP 无法独立确认核心安装版本。确认执行前请退出 RetroArch。": "Transfer only first, then test the CHD files with the original core, including saves and disc changes. The following is your runtime report; MTP cannot verify the installed core version. Quit RetroArch before applying.",
    "光盘 CHD 转换": "Disc CHD conversion",
    "全部分组": "All groups",
    "关闭": "Close",
    "关闭文件选择器": "Close file picker",
    "分析目录与 ZIP 支持": "Analyze folders and ZIP support",
    "分析空间 → 选择光盘 → 电脑转换与内容验证": "Analyze space → select discs → convert and verify on this computer",
    "分析空间与工具": "Analyze space and tools",
    "切换浅色/深色主题": "Switch light/dark theme",
    "切换界面语言": "Switch UI language",
    "切换设备": "Switch device",
    "列表保存位置：": "Playlist destination:",
    "包含子目录": "Include subfolders",
    "取消": "Cancel",
    "取消任务": "Cancel task",
    "取消选择": "Cancel selection",
    "只读检查，不改写列表、核心或游戏文件。候选组仍需核对。": "Read-only inspection; playlists, cores and game files are unchanged. Review candidate groups.",
    "回传、更新引用并清理可移除原文件（保留电脑备份）": "Transfer, update references and remove eligible originals; keep a computer backup",
    "回传并更新引用，保留原文件": "Transfer and update references; keep originals",
    "图片筛选": "Artwork filters",
    "在 RetroArch 核心信息中核对": "Check RetroArch core information",
    "在 RetroArch 的设置 → 目录 → 核心中查看": "Find it in RetroArch: Settings → Directory → Cores",
    "在本机或存储卡中选择游戏目录，列表仍更新到当前游戏库。": "Choose a local or SD card game folder. Playlists are written to the current library.",
    "增量合并，保留已有条目与单独核心设置。不删除失效项。ZIP/7z 按单个游戏入口扫描，不读取包内内容。": "Merge incrementally and preserve existing entries and assigned cores. Missing entries are not removed. ZIP/7z archives are treated as single entries without inspecting their contents.",
    "复制、更新引用并清理有备份的原文件": "Copy, update references and remove backed-up originals",
    "复制并更新引用，保留原文件": "Copy and update references; keep originals",
    "多盘 M3U 方案": "Multi-disc M3U plan",
    "多盘与引用检查": "Disc and reference inspection",
    "存储优化": "Storage optimization",
    "存储空间": "Storage",
    "存档衔接选项": "Save continuity options",
    "官方 MAME 工具": "Official MAME tools",
    "官方下载": "Download from official source",
    "实际使用的核心版本": "Tested core version",
    "导入后补全名称与封面": "Complete names and artwork after import",
    "工作目录与转换工具": "Workspace and conversion tool",
    "工具": "Tools",
    "已安装核心的完整路径": "Full path to the installed core",
    "已有 M3U": "Existing M3U",
    "已用目标路径／ZIP 在原核心验证运行、游戏内存档与所需换盘": "I tested the destination/ZIP with the original core, including saves and disc changes",
    "已用这些 CHD 在原核心验证启动、游戏内存档与所需换盘": "I tested these CHD files with the original core, including launch, saves and disc changes",
    "已连接设备与目录": "Connected devices and folders",
    "已验证的原核心版本": "Verified original core version",
    "延续哪张盘的游戏内存档": "Disc supplying the in-game save",
    "建议的掌机游戏目录": "Suggested handheld game folder",
    "建议的掌机路径": "Suggested handheld paths",
    "开始扫描": "Start scan",
    "当前扫描配置": "Current scan configuration",
    "当前掌机": "Handheld",
    "当前游戏列表": "Current game list",
    "当前游戏的独立名称": "Individual game name",
    "手动指定目录": "Choose folder manually",
    "手动添加游戏": "Add games manually",
    "打开其他游戏库": "Open another library",
    "打开游戏库": "Open library",
    "执行方式": "Operation mode",
    "执行方式与运行报告": "Operation mode and runtime report",
    "扫描变更预览": "Scan changes preview",
    "扫描新增游戏": "Scan new games",
    "扫描设置与高级选项": "Scan settings and advanced options",
    "扫描选项": "Scan options",
    "扫描配置": "Scan profile",
    "指定目录、主机与核心，预览后增量加入游戏列表。": "Choose a folder, system and core; review before adding games incrementally.",
    "掌机中的实际游戏目录": "Actual game folder on the handheld",
    "掌机启动路径": "Handheld launch path",
    "搜索主机": "Search systems",
    "搜索备用来源": "Search alternate sources",
    "搜索游戏名 / rom 名称": "Search game or ROM name",
    "搜索游戏名或 ROM 名称": "Search game or ROM name",
    "搜索游戏或文件路径": "Search games or file paths",
    "搜索游戏组": "Search game groups",
    "操作范围": "Operation scope",
    "收起/展开筛选项": "Collapse/expand filters",
    "文件格式（空格分隔）": "File extensions (space separated)",
    "新增游戏": "New games",
    "无法确认实际存档目录、覆盖设置或核心规则时，不自动切换列表，可选择仅保存 M3U。": "If save folders, overrides or core behavior cannot be confirmed, the playlist will not switch automatically. You can save the M3U only.",
    "显示名称": "Display name",
    "显示更多": "Show more",
    "更新引用前的运行验证": "Runtime verification before reference updates",
    "最近使用": "Recent libraries",
    "未检测": "Not detected",
    "未连接": "Disconnected",
    "未选择目录": "No folder selected",
    "本机 chdman": "Local chdman",
    "本次整理": "This operation",
    "本次方案": "This plan",
    "本次更新": "This update",
    "本次范围": "Current scope",
    "本步仅在电脑生成 CHD 副本，保留原文件和启动引用。完成后可另行预览回传与替换方案。": "This step creates CHD copies on this computer and keeps original files and launch references. Preview transfer or replacement separately afterwards.",
    "核对内容验证结果 → 预览目标与备份 → 确认执行": "Review verification results → preview destinations and backups → apply",
    "核对目标与存档 → 预览引用和备份 → 确认执行": "Review destinations and saves → preview references and backups → apply",
    "检查源目录 → 核对冲突与格式 → 生成电脑 ZIP 副本": "Inspect source folders → review conflicts and formats → create ZIP copies on this computer",
    "正在读取…": "Loading…",
    "正在读取游戏库": "Loading your library",
    "正在读取配置…": "Reading settings…",
    "清理前确认：预览中的目录包含全部相关列表与光盘描述引用": "Before cleanup, I confirm that the preview covers all related playlists and disc descriptor references",
    "游戏存储范围": "Game storage scope",
    "游戏库概览": "Library overview",
    "游戏所在存储": "Game storage",
    "游戏来源：": "Game source:",
    "游戏源目录": "Game source folder",
    "游戏目录": "Game folder",
    "用于 RetroArch 启动游戏，与电脑传输地址不同。未能自动识别时，可从已有路径选择，或在 RetroArch 中查看完整路径。": "Used to launch games in RetroArch; this differs from the computer transfer address. Choose an existing path or check the full path in RetroArch if it cannot be detected.",
    "电脑 ZIP 工作目录": "Computer ZIP workspace",
    "电脑工作目录": "Computer workspace",
    "留空使用应用数据目录": "Leave empty to use the application data folder",
    "留空使用游戏库自动检测的目录": "Leave empty to use the detected library folder",
    "目录与输出位置": "Folders and output location",
    "目录与输出设置": "Folders and output settings",
    "目录整理与 ROM 压缩": "Organize folders and compress ROMs",
    "目录整理与 ZIP 回传": "Organize folders and transfer ZIP files",
    "目标列表文件名": "Target playlist filename",
    "确认仅在电脑转换": "Convert on this computer only",
    "确认导入": "Confirm import",
    "确认应用": "Apply changes",
    "确认应用方案": "Apply plan",
    "确认执行方案": "Execute plan",
    "确认执行此方案": "Execute this plan",
    "确认更新列表": "Update playlist",
    "确认更新前请退出 RetroArch，避免它覆盖列表。写入前自动备份原列表。": "Quit RetroArch before updating so it cannot overwrite the playlist. The original playlist is backed up before writing.",
    "确认生成电脑 ZIP 副本": "Create ZIP copies on this computer",
    "等待扫描 RetroArch 目录": "Waiting to scan the RetroArch folder",
    "筛选游戏组": "Filter game groups",
    "缺少核心？从官方下载安装": "Missing a core? Download from the official source",
    "自动从 PATH 查找 chdman": "Find chdman on PATH automatically",
    "自动匹配中文名与图片，预览后确认应用。": "Match Chinese names and artwork automatically; review before applying.",
    "自动发现 Roms / Games 等目录中的主机文件夹；其他目录可手动添加。": "Find system folders inside Roms / Games and similar locations; add other folders manually.",
    "自动识别的配置可在下方修改；已有游戏单独设置的核心会保留。": "Edit detected settings below; cores assigned to individual games are preserved.",
    "街机 DAT 文件路径（可选，MAME 必填）": "Arcade DAT path (optional; required for MAME)",
    "设备详情": "Device details",
    "设置": "Settings",
    "设置页面": "Settings pages",
    "请选择应用架构": "Select app architecture",
    "转换设置": "Conversion settings",
    "返回游戏列表": "Back to games",
    "选择 RetroArch 目录": "Choose RetroArch folder",
    "选择与排序 → 预览文件、列表和存档变化 → 确认应用": "Select and sort → preview file, playlist and save changes → apply",
    "选择主机列表和源目录；街机 ROM 集与多文件镜像保留原结构。": "Choose a system playlist and source folder. Arcade ROM sets and multi-file disc images keep their structure.",
    "选择光盘与执行方式": "Select discs and operation mode",
    "选择存储与目录": "Choose storage and folder",
    "选择当前列表后分析；节省比例在转换前未知。": "Select a playlist to analyze. Space savings are unknown before conversion.",
    "选择当前目录": "Use current folder",
    "选择扫描范围后开始分析。": "Select the scan scope to begin.",
    "选择掌机上的游戏文件夹": "Choose a game folder on the handheld",
    "选择文件": "Choose file",
    "选择本机或存储卡上的游戏目录": "Choose a local or SD card game folder",
    "选择游戏列表": "Choose playlist",
    "选择游戏目录": "Choose game folder",
    "选择目录": "Choose folder",
    "选择程序": "Choose executable",
    "重新检测": "Refresh devices",
    "重新读取": "Retry",
    "重试": "Retry",
    "需检查": "Needs review",
    "预览变更与备份": "Preview changes and backups",
    "预览名称与图片补全": "Preview names and artwork",
    "预览回传方案": "Preview transfer plan",
    "预览方案": "Preview plan",
    "预览目录包含全部相关列表与描述文件，执行前已退出 RetroArch": "The preview covers all related playlists and descriptors, and RetroArch is closed",
    "预览目录整理": "Preview folder organization",
    "首次读取掌机可能需要一些时间，请保持连接。": "The first read may take a moment. Keep your device connected.",
    "默认与源目录相同": "Same as the source folder by default",
    "默认核心": "Default core",
    "＋ 手动添加": "＋ Add manually",
    "网格视图": "Grid view",
    "列表视图": "List view",
    "本地游戏目录（游戏库同级）": "Local game folder (next to the library)",
    "设备存储": "Device storage",
    "待配置": "Needs setup",
    "请先打开一个游戏库": "Open a library first",
    "选择需要扫描的存储。扫描只读取目录，确认后才生成游戏列表。": "Select storage to scan. Scanning only reads folders; playlists are created after confirmation.",
    "没有可扫描的存储，请确认掌机已选择文件传输。": "No storage is available to scan. Check that file transfer is enabled on the handheld.",
    "请等待当前任务完成": "Wait for the current task to finish",
    "正在分析…": "Analyzing…",
    "任务已取消": "Task cancelled",
    "进度连接中断，正在重连；任务不会重复提交。": "The progress connection was interrupted. Reconnecting without resubmitting the task.",
    "请选择至少一个有新增游戏的主机。": "Select at least one system with new games.",
    "正在取消，已完成的结果会保留。": "Cancelling; completed results are kept.",
    "取消请求未送达：": "Could not send cancellation: ",
    "正在读取扫描配置…": "Loading scan configuration…",
    "新建扫描配置": "New scan profile",
    "MTP 无法验证应用私有目录，请在 RetroArch 中确认核心已安装。": "MTP cannot inspect private app folders. Confirm core installation in RetroArch.",
    "请填写当前设备已安装核心文件的完整路径。": "Enter the full path to the installed core on this device.",
    "首次指定目录、主机与核心；更新成功后会记住配置。": "Choose the folder, system and core. The profile is saved after a successful update.",
    "重新扫描": "Scan again",
    "默认推荐": "Recommended",
    "正在读取目录…": "Reading folder…",
    "处理中…": "Processing…",
    "正在读取目录，请稍后再开始扫描。": "Reading the folder. Wait before starting the scan.",
    "扫描完成，请核对后确认更新列表。": "Scan complete. Review before updating the playlist.",
    "没有新增游戏或配置变化。": "No new games or configuration changes.",
    "原列表已备份。": "The original playlist was backed up.",
    "已创建新列表。": "A new playlist was created.",
    "核心已下载，尚未安装；可传到掌机后在 RetroArch 中安装。": "The core was downloaded but is not installed. Transfer it to the handheld, then install it in RetroArch.",
    "已传输，待 RetroArch 端安装。": "Transferred; installation in RetroArch is still required.",
    "已选择掌机路径。核对后点击“开始扫描”，扫描不会立即写入列表。": "Handheld path selected. Review it, then start scanning. Scanning does not write playlists.",
    "已从现有配置或游戏列表自动识别掌机目录，可直接开始扫描。": "The handheld folder was detected from existing settings or playlists. You can start scanning.",
    "正在取消，等待当前读取完成…": "Cancelling after the current read finishes…",
    "待选择核心": "Select a core",
    "请先连接掌机并打开或指定 RetroArch 目录": "Connect the handheld and open or specify its RetroArch folder first",
    "请选择主机列表": "Select a system playlist",
    "未知": "Unknown",
    "请等待当前任务": "Wait for the current task",
    "分析当前列表；本地直接转换，MTP 确认后拉取源备份并转换，已有 CHD 自动跳过。": "Analyze the current playlist. Local files convert directly; MTP sources are backed up after confirmation. Existing CHD files are skipped.",
    " · 默认推荐": " · Recommended",
    "Beetle Saturn 是兼容性候选，需在掌机验证性能；缺少 BIOS 时也无法正常运行。": "Beetle Saturn is a compatibility option. Test performance on the handheld; the required BIOS must also be available.",
    "MAME 核心必须与 ROM 集及 DAT 版本一致，不自动认定任意版本可用。": "The MAME core, ROM set and DAT versions must match. Compatibility is not assumed for arbitrary versions.",
    "。压缩包作为单个入口处理。": ". Archives are treated as single entries.",
    "官方核心支持：": "Official core formats: ",
    "官方格式信息暂不可读，当前使用主机预设，可手动核对：": "Official format information is unavailable. Using the system defaults; review manually: ",
    "尚未识别掌机中的实际路径。请在 RetroArch 的“加载内容”中查看这个目录的完整路径后填写。": "The actual handheld path is unknown. Find the full folder path under Load Content in RetroArch and enter it here.",
    "已找到现有列表中的建议路径，请核对后点击“使用所选路径”，再开始扫描。": "An existing playlist suggests a path. Review it, choose Use selected path, then start scanning.",
    "扫描配置已变化，请重新预览": "The scan configuration changed. Preview again.",
    "指定核心路径后检查安装状态。": "Specify the core path to check installation status.",
    "无法从已有列表恢复路径：": "Could not recover a path from existing playlists: ",
    "核心状态尚未检查": "Core status not checked",
    "核心状态检查失败": "Could not check core status",
    "请先选择需要扫描的游戏目录。": "Select a game folder to scan first.",
    "请确认已安装核心的完整路径；缺少核心时可展开“从官方下载安装”。": "Confirm the full installed core path. If it is missing, expand the official download instructions.",
    "默认推荐可更换。已有游戏单独设置的核心将保留，不自动升级已安装核心。": "You can change the recommended core. Cores assigned to existing games are preserved; installed cores are not upgraded automatically.",
    "待指定核心路径": "Core path required",
    "请在扫描设置中指定核心文件，或按官方下载引导安装。": "Specify a core file in scan settings, or follow the official installation instructions.",
    "安装状态未知": "Installation status unknown",
    "文件传输无法验证掌机的核心安装状态；请在 RetroArch 中确认。下载和传输不代表安装完成。": "File transfer cannot verify installed cores. Check in RetroArch; downloading and transferring do not complete installation.",
    "核心文件已找到": "Core file found",
    "已确认本地文件存在，尚未验证核心能否实际加载运行。": "The local file exists; loading and runtime compatibility have not been verified.",
    "核心文件未找到": "Core file not found",
    "请更正核心路径，或先安装所选核心。": "Correct the core path or install the selected core first.",
    "目录名称未识别，可使用手动添加指定主机": "Unrecognized folder name. Use manual addition to select the system.",
    "需要确认掌机实际启动路径；请通过手动添加设置一次": "Confirm the handheld launch path once through manual addition."
});

function showStatus(message, type = 'info') {
    const el = document.getElementById('status');
    el.textContent = message;
    el.className = 'status ' + type;
    setTimeout(() => {
        el.textContent = '';
        el.className = 'status';
    }, 3000);
}

function toggleUILanguage() {
    applyUILanguage(currentUILanguage === 'zh' ? 'en' : 'zh');
    localStorage.setItem('plcn-ui-language', currentUILanguage);
    showStatus(uiText('已切换界面语言'), 'info');
}

function uiText(text) {
    return currentUILanguage === 'en' ? (UI_EN[text] || text) : text;
}

function iconOnlyButton(button, svg, label) {
    if (!button) return;
    button.innerHTML = svg;
    button.title = label;
    button.setAttribute('aria-label', label);
}

function getLanguageIconSvg(language) {
    if (language === 'en') {
        return '<svg class="ui-language-icon" data-icon="ui-to-zh" width="20" height="20" viewBox="0 0 24 24" preserveAspectRatio="xMidYMid meet" aria-hidden="true"><circle cx="12" cy="12" r="10"></circle><path d="M21.54 15H17a2 2 0 0 0-2 2v4.54"></path><path d="M7 3.34V5a3 3 0 0 0 3 3h.5a2 2 0 0 1 2 2 2 2 0 0 0 2 2 2 2 0 0 1 2 2c0 .83.67 1.5 1.5 1.5H22"></path><path d="M11 21.95V18a2 2 0 0 0-2-2 2 2 0 0 1-2-2v-1a2 2 0 0 0-2-2H2.05"></path></svg>';
    }
    return '<svg class="ui-language-icon" data-icon="ui-to-en" width="20" height="20" viewBox="0 0 24 24" preserveAspectRatio="xMidYMid meet" aria-hidden="true"><circle cx="12" cy="12" r="10"></circle><path d="M12 2a14.5 14.5 0 0 1 0 20"></path><path d="M12 2a14.5 14.5 0 0 0 0 20"></path><path d="M2 12h20"></path></svg>';
}

function getThemeIconSvg(theme) {
    if (theme === 'dark') {
        return '<svg class="theme-toggle-icon" data-icon="theme-to-light" width="20" height="20" viewBox="0 0 24 24" preserveAspectRatio="xMidYMid meet" aria-hidden="true"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2"></path><path d="M12 20v2"></path><path d="m4.93 4.93 1.41 1.41"></path><path d="m17.66 17.66 1.41 1.41"></path><path d="M2 12h2"></path><path d="M20 12h2"></path><path d="m4.93 19.07 1.41-1.41"></path><path d="m17.66 6.34 1.41-1.41"></path></svg>';
    }
    return '<svg class="theme-toggle-icon" data-icon="theme-to-dark" width="20" height="20" viewBox="0 0 24 24" preserveAspectRatio="xMidYMid meet" aria-hidden="true"><path d="M20.4 14.4A7.8 7.8 0 0 1 9.6 3.6a8.2 8.2 0 1 0 10.8 10.8Z"></path></svg>';
}

function renderLanguageButton() {
    const button = document.getElementById('language-display-btn');
    const label = currentUILanguage === 'en' ? uiText('切换到中文界面') : uiText('切换到英文界面');
    iconOnlyButton(button, getLanguageIconSvg(currentUILanguage), label);
}

function renderThemeButton() {
    const button = document.getElementById('theme-toggle-btn');
    const label = currentTheme === 'dark' ? uiText('切换到浅色模式') : uiText('切换到深色模式');
    iconOnlyButton(button, getThemeIconSvg(currentTheme), label);
    if (button) button.setAttribute('aria-pressed', String(currentTheme === 'dark'));
}

function applyUILanguage(language) {
    currentUILanguage = language === 'en' ? 'en' : 'zh';
    document.title=currentUILanguage==='en'?'RetroArch Assistant':'RetroArch 助手';
    document.documentElement.lang = currentUILanguage === 'en' ? 'en' : 'zh-CN';
    document.body.dataset.uiLanguage = currentUILanguage;

    document.querySelectorAll('[data-i18n]').forEach((el) => {
        el.textContent = uiText(el.dataset.i18n);
    });
    for (const attribute of ['placeholder','title','aria-label']) {
        document.querySelectorAll(`[data-i18n-${attribute}]`).forEach(element => {
            element.setAttribute(attribute, uiText(element.getAttribute(`data-i18n-${attribute}`)));
        });
    }
    renderLanguageButton();
    renderThemeButton();

    renderPreviewTable(currentChanges);
    if (currentDeviceScan) {
        renderDeviceScan(currentDeviceScan);
    } else {
        renderDeviceScan(null);
    }
    updateSummary(currentChanges);
    renderWorkbench();
}

function formatGameListCount(count) {
    return currentUILanguage === 'en' ? `${count} ${count === 1 ? 'game list' : 'game lists'}` : `${count} 个游戏列表`;
}

function formatGameCount(count) {
    return currentUILanguage === 'en' ? `${count} ${count === 1 ? 'game' : 'games'}` : `${count} 个游戏`;
}

function formatItemCount(count) {
    return currentUILanguage === 'en' ? `${count} ${count === 1 ? 'item' : 'items'}` : `${count} 项`;
}

function toggleTheme() {
    applyTheme(currentTheme === 'dark' ? 'light' : 'dark');
    localStorage.setItem('plcn-theme', currentTheme);
    showStatus(uiText(currentTheme === 'dark' ? '深色模式已开启' : '浅色模式已开启'), 'info');
}

function applyTheme(theme) {
    currentTheme = theme === 'dark' ? 'dark' : 'light';
    document.body.dataset.theme = currentTheme;
    renderThemeButton();
}

function initializeDisplayPreferences() {
    applyUILanguage(localStorage.getItem('plcn-ui-language') || 'zh');
    applyTheme(localStorage.getItem('plcn-theme') || 'light');
}

function shortPath(path) {
    if (!path) return '';
    const normalized = path.replace(/\\/g, '/');
    const parts = normalized.split('/');
    return parts.length > 2 ? `${parts[parts.length - 2]}/${parts[parts.length - 1]}` : path;
}

function shortThumbnailType(typeName) {
    if (typeName === 'Named_Boxarts') return 'Boxarts';
    if (typeName === 'Named_Snaps') return 'Snaps';
    if (typeName === 'Named_Titles') return 'Titles';
    return typeName || '-';
}

function escapeHtml(value) {
    return String(value || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
