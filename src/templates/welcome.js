/* Discovery updates the home screen only; opening a library is always explicit. */
const libraryHome = {generation: 0, loading: false, data: null, error: '', openError: '', opening: ''};
const homeText = (zh, en) => workbenchText(zh, en);
function homeStatus(source) {
    const labels = {
        ready: source.transport === 'adb' ? ['设备已连接', 'Device connected'] : ['目录可用', 'Available'],
        unauthorized: ['等待设备授权 · 请在设备上允许 USB 调试', 'Authorization required · Allow USB debugging on the device'],
        offline: ['设备离线 · 请重新连接 USB', 'Device offline · Reconnect USB'],
        disconnected: ['设备未连接', 'Device disconnected'],
        missing: ['目录不存在或磁盘未挂载', 'Folder missing or drive not mounted'],
        no_library: ['设备已连接，未找到游戏目录', 'Connected; game folder not found']
    };
    return homeText(...(labels[source.status] || ['无法读取', 'Unavailable']));
}
function renderLibraryHome() {
    const panel = document.getElementById('library-onboarding');
    if (!panel) return;
    const busy = Boolean(workbench.operation);
    const text = (id, zh, en) => { document.getElementById(id).textContent = homeText(zh, en); };
    text('home-title', '打开游戏库', 'Open a game library');
    text('home-back', '打开其他游戏库', 'Open another library');
    text('home-description', '选择设备或本地目录，查看游戏、补全图片和整理名称。', 'Choose a device or folder to browse games, add artwork and organize names.');
    text('home-devices-title', '已连接设备与目录', 'Connected devices and folders');
    text('home-recent-title', '最近使用', 'Recent libraries');
    text('home-local-title', '本地游戏库', 'Local library');
    text('home-local-description', '打开电脑或 SD 卡上的 RetroArch、playlists 目录。', 'Open a RetroArch or playlists folder on your computer or SD card.');
    text('home-local-open', '打开本地目录', 'Open local folder');
    text('home-manual-open', '手动输入路径', 'Enter a path');
    const refresh = document.getElementById('scan-default-btn');
    refresh.textContent = libraryHome.loading ? homeText('检测中…', 'Detecting…') : homeText('重新检测', 'Refresh');
    refresh.disabled = busy || libraryHome.loading;
    panel.setAttribute('aria-busy', String(libraryHome.loading || Boolean(libraryHome.opening)));
    const message = document.getElementById('home-message');
    message.textContent = libraryHome.openError || libraryHome.error;
    message.hidden = !message.textContent;
    for (const [id, entries, recent] of [['home-devices', libraryHome.data?.sources || [], false], ['home-recent', libraryHome.data?.recent || [], true]]) {
        const list = document.getElementById(id);
        list.replaceChildren();
        if (!entries.length) {
            const empty = document.createElement('p');
            empty.className = 'home-empty';
            empty.textContent = libraryHome.loading ? homeText('正在检查设备与目录…', 'Checking devices and folders…')
                : recent ? homeText('打开游戏库后，会在这里保留最近使用记录。', 'Libraries you open will appear here.')
                : libraryHome.error ? homeText('检测未完成，请重新检测。', 'Discovery failed. Please retry.')
                : libraryHome.data?.adb_available === false ? homeText('未找到 ADB，暂时无法检测 Android 设备。仍可打开本地目录。', 'ADB is unavailable. You can still open a local folder.')
                : homeText('未发现可用设备或默认目录。连接 USB 设备并允许调试后，点击“重新检测”。', 'No device or default folder found. Connect a USB device, allow debugging, then refresh.');
            list.appendChild(empty);
        }
        for (const source of entries) {
            const row = document.createElement('div'); row.className = 'home-source'; row.dataset.status = source.status;
            const icon = document.createElement('span'); icon.className = 'home-source-icon'; icon.textContent = source.transport === 'adb' ? 'USB' : homeText('目录', 'DIR'); icon.setAttribute('aria-hidden', 'true');
            const body = document.createElement('div'); body.className = 'home-source-body';
            const title = document.createElement('strong'); title.textContent = source.label;
            const path = document.createElement('p'); path.className = 'home-source-path';
            path.textContent = source.transport === 'adb' ? source.path.replace(/^adb:\/\/[^/]+/, '') || homeText('设备存储', 'Device storage') : source.path;
            path.title = source.path;
            const state = document.createElement('p'); state.className = 'home-source-state'; state.textContent = homeStatus(source);
            body.append(title, path, state);
            const button = document.createElement('button'); button.type = 'button';
            button.className = 'btn' + (recent || source.status !== 'ready' ? ' btn-muted' : '');
            button.textContent = libraryHome.opening === source.path ? homeText('正在打开…', 'Opening…')
                : source.status === 'no_library' ? homeText('指定目录', 'Choose folder') : recent ? homeText('打开', 'Open') : homeText('打开游戏库', 'Open library');
            button.setAttribute('aria-label', button.textContent + ' · ' + source.label);
            button.disabled = busy || libraryHome.loading || !['ready', 'no_library'].includes(source.status);
            button.onclick = () => source.status === 'no_library' ? enterLibraryPath(source.path) : openLibrarySource(source);
            row.append(icon, body, button); list.appendChild(row);
        }
    }
}
async function refreshLibrarySources() {
    if (workbench.operation) return;
    const generation = ++libraryHome.generation;
    libraryHome.loading = true; libraryHome.error = ''; libraryHome.openError = '';
    renderLibraryHome();
    try {
        const response = await fetch('/api/library/sources');
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || String(response.status));
        if (generation === libraryHome.generation) libraryHome.data = data;
    } catch (error) {
        if (generation === libraryHome.generation) {
            libraryHome.data = null;
            libraryHome.error = homeText('检测失败：', 'Discovery failed: ') + error.message;
        }
    } finally {
        if (generation === libraryHome.generation) { libraryHome.loading = false; renderLibraryHome(); }
    }
}
async function openLibrarySource(source) {
    if (workbench.operation || libraryHome.loading) return;
    libraryHome.opening = source.path; libraryHome.openError = '';
    document.getElementById('retroarch_root').value = source.path;
    try { await scanDevice(false); }
    finally { libraryHome.opening = ''; renderLibraryHome(); }
}
function enterLibraryPath(path) {
    if (workbench.operation) return;
    if (path) document.getElementById('retroarch_root').value = path;
    openPathSettings();
    document.getElementById('retroarch_root').focus();
}
async function rememberOpenedLibrary(scan) {
    if (!scan.connected || !scan.playlists?.length) return;
    const entry = {path: scan.root_path || scan.target_path,
        label: scan.device?.model?.replaceAll('_', ' ') || shortPath(scan.root_path || scan.target_path)};
    try { await desktopRequest('/api/library/recent', entry); }
    catch (error) { console.warn('Could not save recent library:', error.message); }
}
function showLibraryHome() {
    if (workbench.operation) return;
    document.querySelector('.library-manage').open = false;
    currentDeviceScan = null;
    renderDeviceScan(null);
    for (const id of ['playlist_path', 'batch_dir', 'thumbnails_dir', 'batch_thumbnails_dir']) document.getElementById(id).value = '';
    invalidateWorkbenchPreview();
    refreshLibrarySources();
}
