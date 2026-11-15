/* Discovery updates the home screen only; opening a library is always explicit. */
const libraryHome = {generation: 0, loading: true, data: null, error: '', openError: '', opening: '', device: null};
const homeText = (zh, en) => workbenchText(zh, en);
function homeStatus(source) {
    const labels = {
        usb_only: ['USB 已连接 · 文件传输未就绪', 'USB connected · File transfer unavailable'],
        ready: source.transport !== 'local' ? ['设备已连接', 'Device connected'] : ['目录可用', 'Available'],
        unauthorized: ['等待设备授权 · 请在设备上允许 USB 调试', 'Authorization required · Allow USB debugging on the device'],
        offline: ['设备离线 · 请重新连接 USB', 'Device offline · Reconnect USB'],
        disconnected: ['设备未连接', 'Device disconnected'],
        missing: ['目录不存在或磁盘未挂载', 'Folder missing or drive not mounted'],
        no_library: source.transport === 'mtp'
            ? ['此存储的默认位置未找到游戏列表', 'No playlist found in this storage’s default location']
            : ['设备已连接，未找到游戏目录', 'Connected; game folder not found']
    };
    return homeText(...(labels[source.status] || ['无法读取', 'Unavailable']));
}
function renderLibraryHome() {
    const panel = document.getElementById('library-onboarding');
    if (!panel) return;
    const busy = Boolean(workbench.operation);
    const text = (id, zh, en) => { document.getElementById(id).textContent = homeText(zh, en); };
    text('home-title', '选择设备', 'Choose a device');
    text('home-back', '切换设备', 'Switch device');
    text('home-description', '选择要管理的掌机，进入后查看游戏库、扫描新增游戏和补全图片。', 'Choose your handheld, then browse, scan new games and complete artwork.');
    text('home-devices-title', '已连接掌机', 'Connected handhelds');
    text('home-recent-title', '最近使用', 'Recent libraries');
    const refresh = document.getElementById('scan-default-btn');
    refresh.textContent = libraryHome.loading ? homeText('检测中…', 'Detecting…') : homeText('重新检测', 'Refresh');
    refresh.disabled = busy || libraryHome.loading;
    panel.setAttribute('aria-busy', String(libraryHome.loading || Boolean(libraryHome.opening)));
    const message = document.getElementById('home-message');
    message.textContent = libraryHome.openError || libraryHome.error;
    message.hidden = !message.textContent;
    for (const [id, entries, recent] of [['home-devices', homeDeviceSources(libraryHome.data?.sources || []), false], ['home-recent', libraryHome.data?.recent || [], true]]) {
        const list = document.getElementById(id);
        list.replaceChildren();
        if (!entries.length) {
            const empty = document.createElement('p');
            empty.className = 'home-empty';
            empty.textContent = libraryHome.loading ? homeText('正在检查设备与目录…', 'Checking devices and folders…')
                : recent ? (libraryHome.data?.sources?.some(source => source.status === 'ready')
                    ? homeText('已连接的游戏库已在上方显示。', 'Connected libraries are shown above.')
                    : homeText('打开游戏库后，会在这里保留最近使用记录。', 'Libraries you open will appear here.'))
                : libraryHome.error ? homeText('检测未完成，请重新检测。', 'Discovery failed. Please retry.')
                : homeText('未检测到可用掌机连接，请确认设备连接后重新检测。', 'No handheld found. Select USB file transfer, unlock the device, then refresh.');
            list.appendChild(empty);
        }
        for (const source of entries) {
            const row = document.createElement('div'); row.className = 'home-source'; row.dataset.status = source.status;
            const icon = document.createElement('span'); icon.className = 'home-source-icon'; icon.textContent = source.transport !== 'local' ? 'USB' : homeText('目录', 'DIR'); icon.setAttribute('aria-hidden', 'true');
            const body = document.createElement('div'); body.className = 'home-source-body';
            const title = document.createElement('strong'); title.textContent = source.label;
            const path = document.createElement('p'); path.className = 'home-source-path';
            path.textContent = source.status === 'usb_only' ? source.error || homeText('请在掌机上选择文件传输并解锁', 'Select file transfer and unlock your handheld') : source.transport !== 'local' ? decodeURIComponent(source.path.replace(/^mtp:\/\/[^/]+\/[^/]+|^adb:\/\/[^/]+/, '')) || homeText('设备存储', 'Device storage') : source.path;
            if (source.storages) path.textContent = homeText(`${source.storages.length} 个存储空间`, `${source.storages.length} storage locations`);
            path.title = source.path;
            const state = document.createElement('p'); state.className = 'home-source-state'; state.textContent = homeStatus(source);
            if (source.storages) state.textContent = homeText('设备已连接', 'Device connected');
            body.append(title, path, state);
            const button = document.createElement('button'); button.type = 'button';
            button.className = 'btn' + (source.status !== 'ready' ? ' btn-muted' : '');
            button.textContent = libraryHome.opening && libraryHome.opening === source.path ? homeText('正在打开…', 'Opening…')
                : source.status === 'usb_only' ? homeText('等待文件传输', 'Waiting for file transfer')
                : ['ready', 'no_library'].includes(source.status) ? (source.storages ? homeText('进入设备', 'Open device') : homeText('打开游戏库', 'Open library'))
                : homeText('等待连接', 'Waiting for connection');
            button.setAttribute('aria-label', button.textContent + ' · ' + source.label);
            button.disabled = busy || libraryHome.loading || !['ready', 'no_library'].includes(source.status);
            button.onclick = () => openLibrarySource(source);
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
    libraryHome.device = source.storages ? source : null;
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
    const path = scan.root_path || scan.target_path;
    const source = libraryHome.data?.sources?.find(source => source.path === path);
    const entry = {path, label: source?.label || scan.device?.model?.replaceAll('_', ' ') || shortPath(path)};
    try { await desktopRequest('/api/library/recent', entry); }
    catch (error) { console.warn('Could not save recent library:', error.message); }
}
function showLibraryHome() {
    if (workbench.operation) return;
    libraryHome.device = null;
    currentDeviceScan = null;
    renderDeviceScan(null);
    for (const id of ['playlist_path', 'system_name']) document.getElementById(id).value = '';
    invalidateWorkbenchPreview();
    refreshLibrarySources();
}


function homeDeviceSources(sources) {
    const devices = [], grouped = new Map();
    for (const source of sources) {
        if (source.transport !== 'mtp') { devices.push(source); continue; }
        const key = source.serial || source.path.split('/')[2];
        let device = grouped.get(key);
        if (!device) {
            device = {...source, label: homeText('Android 掌机', 'Android handheld'), storages: []};
            grouped.set(key, device); devices.push(device);
        }
        device.storages.push(source);
        if (source.status === 'ready' && device.status !== 'ready') {
            device.path = source.path; device.status = source.status;
        }
    }
    return devices;
}

function renderDeviceStorage() {
    const field = document.getElementById('device-storage-field');
    const select = document.getElementById('device-storage-select');
    const storages = libraryHome.device?.storages || [];
    field.hidden = storages.length < 2;
    select.disabled = Boolean(workbench.operation);
    if (field.hidden) return;
    const root = document.getElementById('retroarch_root').value;
    select.replaceChildren(...storages.map(source => new Option(source.label, source.path)));
    select.value = root;
}

async function selectDeviceStorage() {
    if (workbench.operation) return;
    document.getElementById('retroarch_root').value = document.getElementById('device-storage-select').value;
    await scanDevice();
}
