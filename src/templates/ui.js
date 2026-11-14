/* Display preferences, translations and shared presentation helpers. */
let currentUILanguage = 'zh';
let currentTheme = 'light';

const UI_EN = {
    '查看任务': 'View tasks',
    '整理本主机': 'Organize this system',
    '整理全部主机': 'Organize all systems',
    '修改名称': 'Rename games',
    '补全图片': 'Complete artwork',
    '选项变化后重新分析': 'Changing options reanalyzes the list',
    '全部主机变更汇总': 'All-system change summary',
    '这里只分析，不会写入。确认后应用本次汇总中的变更。': 'Analysis only. Confirm to apply the changes in this summary.',
    '写回名称前自动备份；仅补图不改写游戏列表。': 'Playlists are backed up before renaming. Artwork-only tasks preserve playlist files.',
    '重新生成汇总': 'Refresh summary',
    '确认应用全部变更': 'Apply all reviewed changes',
    '关闭': 'Close',

    "设置": "Settings",
    "游戏库": "Library",
    "退出 PLCN": "Quit PLCN",
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
    "PLCN 管理": "PLCN management",
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
    '遇到错误继续处理下一个': 'Continue after errors',
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
    'PLCN 会先展示写入名称、封面源和匹配状态，低置信结果可在右侧手动校对。': 'PLCN shows the name to write, cover source, and match status. Low-confidence results can be reviewed on the right.',
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
    document.documentElement.lang = currentUILanguage === 'en' ? 'en' : 'zh-CN';
    document.body.dataset.uiLanguage = currentUILanguage;

    document.querySelectorAll('[data-i18n]').forEach((el) => {
        el.textContent = uiText(el.dataset.i18n);
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach((el) => {
        el.placeholder = uiText(el.dataset.i18nPlaceholder);
    });
    renderLanguageButton();
    renderThemeButton();

    renderPreviewTable(currentChanges);
    if (currentDeviceScan) {
        renderDeviceScan(currentDeviceScan);
    } else {
        renderDeviceScan(null);
    }
    hideApplySummary();
    updateSummary(currentChanges);
    renderWorkbench();
}

function formatGameListCount(count) {
    return currentUILanguage === 'en' ? `${count} game lists` : `${count} 个游戏列表`;
}

function formatGameCount(count) {
    return currentUILanguage === 'en' ? `${count} games` : `${count} 个游戏`;
}

function formatItemCount(count) {
    return currentUILanguage === 'en' ? `${count} items` : `${count} 项`;
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
