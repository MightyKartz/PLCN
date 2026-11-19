/* Library discovery results and system/playlist navigation. */
let currentDeviceScan = null;
let selectedLibrarySystem = '';
let overviewReturn = null;

async function scanDevice(useDefault = false) {
    const rootInput = document.getElementById('retroarch_root');
    const scanBtn = document.getElementById('scan-device-btn');
    const defaultBtn = document.getElementById('scan-default-btn');
    const targetPath = useDefault ? '' : rootInput.value.trim();

    if (!useDefault && !targetPath) {
        showStatus('请先选择 RetroArch 目录，或使用自动检测', 'error');
        return;
    }

    setLibraryRoot(targetPath);
    if (!beginWorkbenchOperation('scan')) return;
    if (typeof beginLibraryRead === 'function') beginLibraryRead('scan', workbenchText('正在读取主机与游戏列表…', 'Reading systems and game lists…'), targetPath);
    libraryHome.openError = '';
    invalidateWorkbenchPreview();
    if (currentDeviceScan?.root_path !== targetPath) currentDeviceScan = null;
    for (const id of ['playlist_path', 'system_name']) document.getElementById(id).value = '';
    desktopDialog.close();
    scanBtn.disabled = true;
    defaultBtn.disabled = true;

    try {
        const url = targetPath ? `/api/device/scan?path=${encodeURIComponent(targetPath)}` : '/api/device/scan';
        const scan = await desktopRequest(url);
        if (scan.error) throw new Error(scan.error);

        currentDeviceScan = scan;
        selectedLibrarySystem = '';
        document.getElementById('playlist_path').value = '';
        renderDeviceScan(scan);

        if (scan.root_path) {
            rootInput.value = scan.root_path;
            pathSettingsRoot = scan.root_path;
        }
        if (legacyThumbnailsSetting) {
            if (document.getElementById('thumbnails_override').value === scan.directories?.thumbnails)
                document.getElementById('thumbnails_override').value = '';
            legacyThumbnailsSetting = false;
        }
        const playlistCount = scan.totals?.playlists || 0;
        const itemCount = scan.totals?.items || 0;
        const scanStatusMessage = currentUILanguage === 'en'
            ? (playlistCount ? 'RetroArch directory detected' : 'No game lists found')
            : (scan.message || '扫描完成');
        showStatus(scanStatusMessage, scan.connected ? 'success' : 'error');
        if (!scan.connected) libraryHome.openError = (targetPath ? shortPath(targetPath) + '：' : '') + scanStatusMessage;
        else { await rememberOpenedLibrary(scan); await saveConfig(); }

    } catch (error) {
        currentDeviceScan = null;
        renderDeviceScan(null);
        showStatus(`${uiText('扫描失败')}: ${error.message}`, 'error');
        libraryHome.openError = `${uiText('扫描失败')}: ${error.message}`;
    } finally {
        scanBtn.disabled = false;
        defaultBtn.disabled = false;
        endWorkbenchOperation();
        if (typeof finishLibraryRead === 'function') finishLibraryRead('scan', libraryHome.openError);
        if (currentDeviceScan?.connected && selectedLibrarySystem) {
            await selectFirstPlaylistForSystem(selectedLibrarySystem);
        }
    }
}

async function refreshLibraryPlaylists(paths) {
    const scan = currentDeviceScan;
    if (!paths.length) return;
    if (!scan?.connected) {
        await scanDevice();
        return;
    }
    const changed = await Promise.all(paths.map(async path => {
        const query = new URLSearchParams({path});
        return desktopRequest('/api/library/playlist-summary?' + query);
    }));
    if (currentDeviceScan !== scan) return;
    const playlists = new Map(scan.playlists.map(playlist => [playlist.path, playlist]));
    for (const {summary} of changed) playlists.set(summary.path, summary);
    scan.directories.playlists ||= changed[0].directory;
    scan.playlists = [...playlists.values()];
    scan.totals = {playlists:scan.playlists.length,
        items:scan.playlists.reduce((count, playlist) => count + playlist.item_count, 0)};
    scan.status = 'ready';
    renderDeviceScan(scan);
    renderWorkbench();
}

function getPlaylistSystemName(playlist) {
    return playlist?.system || playlist?.db_name || playlist?.name || uiText('未命名主机');
}

function getSystemAbbreviation(systemName) {
    const name = String(systemName || '').trim();
    if (!name) return uiText('未命名主机');

    const rules = [
        [/FinalBurn\s+Neo|FBNeo/i, 'FBNeo'],
        [/Microsoft\s*[-–]\s*MSX2/i, 'MSX2'],
        [/NEC\s*[-–]\s*PC\s*Engine\s*CD|TurboGrafx\s*[-–]?\s*CD/i, 'PCE CD'],
        [/NEC\s*[-–]\s*PC\s*Engine|TurboGrafx/i, 'PCE'],
        [/NEC\s*[-–]\s*PC\s*98|PC-98/i, 'PC-98'],
        [/Nintendo\s*[-–]\s*Game\s*Boy\s*Advance/i, 'GBA'],
        [/Nintendo\s*[-–]\s*Game\s*Boy\s*Color/i, 'GBC'],
        [/Nintendo\s*[-–]\s*Game\s*Boy(?!\s*(Advance|Color))/i, 'GB'],
        [/Nintendo\s*[-–]\s*Nintendo\s*64/i, 'N64'],
        [/Nintendo\s*[-–]\s*Nintendo\s*DS/i, 'NDS'],
        [/Nintendo\s*[-–]\s*Nintendo\s*Entertainment\s*System/i, 'NES'],
        [/Nintendo\s*[-–]\s*Super\s*Nintendo\s*Entertainment\s*System/i, 'SNES'],
        [/Nintendo\s*[-–]\s*GameCube/i, 'GC'],
        [/Nintendo\s*[-–]\s*Wii/i, 'Wii'],
        [/Sega\s*[-–]\s*Mega\s*Drive|Genesis/i, 'MD'],
        [/Sega\s*[-–]\s*Dreamcast/i, 'DC'],
        [/Sega\s*[-–]\s*Saturn/i, 'SS'],
        [/Sony\s*[-–]\s*PlayStation\s*2/i, 'PS2'],
        [/Sony\s*[-–]\s*PlayStation/i, 'PS1'],
        [/DOS/i, 'DOS'],
        [/Arcade/i, 'Arcade'],
    ];

    const matched = rules.find(([pattern]) => pattern.test(name));
    if (matched) return matched[1];

    const compact = name
        .replace(/\([^)]*\)/g, '')
        .replace(/\.(lpl|json)$/i, '')
        .replace(/\s+[-–]\s+/g, ' ')
        .trim();
    if (/^[A-Z0-9][A-Z0-9 -]{1,9}$/i.test(compact)) return compact;

    const initials = compact
        .split(/[\s_\-–]+/)
        .filter(Boolean)
        .map((part) => part[0]?.toUpperCase())
        .join('');
    return initials.slice(0, 8) || compact.slice(0, 8) || name;
}

async function selectFirstPlaylistForSystem(systemName) {
    const playlists = currentDeviceScan?.playlists || [];
    const index = playlists.findIndex((playlist) => getPlaylistSystemName(playlist) === systemName && playlist.valid);
    if (index >= 0) {
        await selectScannedPlaylist(index);
    }
}

function renderDeviceScan(scan) {
    const summary = document.getElementById('device-summary');
    const list = document.getElementById('scanned-playlists');
    const librarySummary = document.getElementById('library-browser-summary');
    const previewIsActive = !document.getElementById('preview-area')?.hidden;
    updateDeviceDirectoryRows(scan);
    list.innerHTML = '';
    if (!previewIsActive) setLibraryBrowserVisible(true);

    if (!scan) {
        summary.textContent = uiText('等待扫描 RetroArch 目录');
        summary.classList.remove('ready');
        list.innerHTML = `<div class="playlist-empty">${uiText('扫描后显示 .lpl 游戏列表')}</div>`;
        if (librarySummary) librarySummary.textContent = uiText('扫描后按主机名称显示 .lpl 游戏列表');
        return;
    }

    const playlistCount = scan.totals?.playlists || 0;
    const itemCount = scan.totals?.items || 0;
    const groups = new Map();
    (scan.playlists || []).forEach((playlist, index) => {
        const groupName = getPlaylistSystemName(playlist);
        if (!groups.has(groupName)) groups.set(groupName, []);
        groups.get(groupName).push({ playlist, index });
    });

    summary.textContent = playlistCount
        ? `${shortPath(scan.root_path)} · ${formatGameListCount(playlistCount)} · ${formatGameCount(itemCount)}`
        : (currentUILanguage === 'en' ? 'No game lists found' : (scan.message || '未找到游戏列表'));
    summary.classList.toggle('ready', playlistCount > 0);
    if (librarySummary) {
        const systemCount = currentUILanguage === 'en' ? `${groups.size} systems` : `${groups.size} 个主机`;
        librarySummary.textContent = playlistCount
            ? `${systemCount} · ${formatGameCount(itemCount)}`
            : uiText('扫描后按主机名称显示 .lpl 游戏列表');
    }

    if (!scan.playlists?.length) {
        list.innerHTML = `<div class="playlist-empty">${currentUILanguage === 'en' ? 'No .lpl files found. Choose the RetroArch root or playlists directory.' : '未找到 .lpl 文件，可改选 RetroArch 根目录或 playlists 目录。'}</div>`;
        return;
    }

    const preferredSystem = findPreferredLibrarySystem(groups);
    selectedLibrarySystem = groups.has(selectedLibrarySystem) ? selectedLibrarySystem : preferredSystem;
    renderLibrarySystemTabs(list, groups);
}

function findPreferredLibrarySystem(groups) {
    const selectedPath = document.getElementById('playlist_path').value;
    if (selectedPath) {
        for (const [groupName, items] of groups.entries()) {
            if (items.some(({ playlist }) => playlist.path === selectedPath)) return groupName;
        }
    }
    return '';
}

function selectAllLibrarySystems() {
    if (workbench.operation) return;
    const returning = Boolean(document.getElementById('playlist_path').value);
    selectedLibrarySystem = '';
    invalidateWorkbenchPreview();
    for (const id of ['playlist_path', 'system_name']) document.getElementById(id).value = '';
    renderDeviceScan(currentDeviceScan);
    renderWorkbench();
    if (!returning) return;

    const saved = overviewReturn?.root === currentDeviceScan?.root_path ? overviewReturn : null;
    overviewReturn = null;
    const panel = document.querySelector('.main-panel');
    panel.scrollTop = saved?.scrollTop ?? 0;
    const card = [...document.querySelectorAll('#library-overview .overview-system-card')]
        .find(button => !button.hidden && button.dataset.system === saved?.system);
    (card || document.getElementById('library-all-systems'))
        ?.focus({preventScroll: true});
}

async function browseLibrarySystem(systemName) {
    if (workbench.operation) return;
    const panel = document.querySelector('.main-panel');
    const overview = document.getElementById('library-overview');
    if (!overview.hidden) {
        overviewReturn = {root: currentDeviceScan.root_path, scrollTop: panel.scrollTop, system: systemName};
    }
    selectedLibrarySystem = systemName;
    renderDeviceScan(currentDeviceScan);
    await selectFirstPlaylistForSystem(systemName);
    if (!overview.hidden) return;
    panel.scrollTop = 0;
    document.getElementById('back-to-systems').focus({preventScroll: true});
}

function renderLibrarySystemTabs(container, groups) {
    const tabs = document.createElement('div');
    tabs.className = 'playlist-system-tabs';

    const allButton = document.createElement('button');
    allButton.type = 'button';
    allButton.disabled = Boolean(workbench.operation);
    allButton.id = 'library-all-systems';
    allButton.className = `playlist-system-tab${selectedLibrarySystem === '' ? ' active' : ''}`;
    const allIcon = wbIcon('layout-grid');
    const allName = document.createElement('span'); allName.className = 'system-display-name';
    allName.textContent = workbenchText('全部主机', 'All systems');
    const allCount = document.createElement('span'); allCount.className = 'system-game-count';
    allCount.textContent = groups.size;
    allButton.append(allIcon, allName, allCount);
    allButton.title = workbenchText('全部主机', 'All systems');
    allButton.setAttribute('aria-label', workbenchText('全部主机', 'All systems'));
    allButton.setAttribute('aria-pressed', String(selectedLibrarySystem === ''));
    allButton.onclick = selectAllLibrarySystems;
    tabs.appendChild(allButton);

    groups.forEach((items, groupName) => {
        const tabButton = document.createElement('button');
        tabButton.type = 'button';
        tabButton.disabled = Boolean(workbench.operation);
        tabButton.className = `playlist-system-tab${groupName === selectedLibrarySystem ? ' active' : ''}`;
        const group = document.createElement('div');
        group.className = 'library-system-group';
        const icon = wbIcon(wbSystemIcon(groupName));
        const name = document.createElement('span'); name.className = 'system-display-name';
        name.textContent = getSystemAbbreviation(groupName);
        const count = document.createElement('span'); count.className = 'system-game-count';
        count.textContent = items.reduce((total, item) => total + (Number(item.playlist.item_count) || 0), 0);
        tabButton.append(icon, name, count);
        tabButton.title = groupName;
        tabButton.setAttribute('aria-label', groupName);
        tabButton.setAttribute('aria-pressed', String(groupName === selectedLibrarySystem));
        tabButton.onclick = () => browseLibrarySystem(groupName);
        group.appendChild(tabButton);
        if (groupName === selectedLibrarySystem && (items.length > 1 || !items[0].playlist.valid)) renderSelectedLibraryList(group, groups);
        tabs.appendChild(group);
    });

    container.appendChild(tabs);
}

function renderSelectedLibraryList(container, groups) {
    const items = groups.get(selectedLibrarySystem) || [];
    const caption = document.createElement('div');
    caption.className = 'playlist-list-caption';
    const title = document.createElement('strong');
    title.textContent = getSystemAbbreviation(selectedLibrarySystem);
    title.title = selectedLibrarySystem || title.textContent;
    const count = document.createElement('span');
    const itemCount = items.reduce((sum, item) => sum + (Number(item.playlist.item_count) || 0), 0);
    count.textContent = `${formatGameListCount(items.length)} · ${formatGameCount(itemCount)}`;
    caption.appendChild(title);
    caption.appendChild(count);

    container.appendChild(caption);
    for (const { playlist, index } of items) container.appendChild(buildPlaylistCard(playlist, index));
}

function buildPlaylistCard(playlist, index) {
    const card = document.createElement('button');
    card.type = 'button';
    card.className = `playlist-card${playlist.valid ? '' : ' invalid'}`;
    if (playlist.path === document.getElementById('playlist_path').value) card.classList.add('active');
    card.onclick = () => selectScannedPlaylist(index);

    const body = document.createElement('div');
    const name = document.createElement('div');
    name.className = 'playlist-name';
    name.textContent = playlist.name || playlist.system || uiText('未命名主机');
    name.title = name.textContent;
    const meta = document.createElement('div');
    meta.className = 'playlist-meta';
    const transportLabel = playlist.transport === 'adb'
        ? (currentUILanguage === 'en' ? 'ADB device' : 'ADB 实机')
        : (currentUILanguage === 'en' ? 'Local' : '本地');
    meta.textContent = playlist.valid
        ? `${transportLabel} · ${playlist.db_name || playlist.system || (currentUILanguage === 'en' ? 'No db_name' : '无 db_name')}`
        : `${transportLabel} · ${playlist.error || (currentUILanguage === 'en' ? 'Unreadable' : '无法读取')}`;
    meta.title = meta.textContent;
    body.appendChild(name);
    body.appendChild(meta);

    const count = document.createElement('div');
    count.className = 'playlist-count';
    count.textContent = playlist.valid ? formatItemCount(playlist.item_count) : (currentUILanguage === 'en' ? 'Invalid' : '无效');

    card.appendChild(body);
    card.appendChild(count);
    return card;
}

function setLibraryBrowserVisible(visible) {
    const browser = document.getElementById('library-browser');
    if (browser) browser.hidden = !visible;
}

function setPreviewAreaVisible(visible) {
    const previewArea = document.getElementById('preview-area');
    if (previewArea) previewArea.hidden = !visible;
    document.getElementById('library-browser')?.classList.toggle('has-preview', visible);
}

function updateDeviceDirectoryRows(scan) {
    const dirs = scan?.directories || {};
    setPathText('device-playlists-dir', dirs.playlists || uiText('未检测'));
    setPathText('device-thumbnails-dir', dirs.thumbnails || uiText('未检测'));
    setPathText('device-config-file', dirs.config || uiText('未检测'));
}

function setPathText(id, value) {
    const el = document.getElementById(id);
    el.textContent = value;
    el.title = value;
}

async function selectScannedPlaylist(index) {
    if (workbench.operation) return;
    const playlist = currentDeviceScan?.playlists?.[index];
    if (!playlist) return;
    if (!playlist.valid) {
        showStatus('该游戏列表无法读取，请检查 .lpl JSON 内容', 'error');
        return;
    }

    invalidateWorkbenchPreview();
    document.getElementById('playlist_path').value = playlist.path;
    document.getElementById('system_name').value = playlist.system || '';
    renderWorkbench();
    renderDeviceScan(currentDeviceScan);
    renderWorkbench();
}


function renderLibraryOverview(visible) {
    if (typeof renderWorkbenchOverview === 'function') return renderWorkbenchOverview(visible);
    const panel = document.getElementById('library-overview');
    panel.hidden = !visible;
    panel.replaceChildren();
    if (!visible) return;
    const groups = new Map();
    for (const playlist of currentDeviceScan.playlists) {
        const name = getPlaylistSystemName(playlist);
        groups.set(name, (groups.get(name) || 0) + (Number(playlist.item_count) || 0));
    }
    const intro = document.createElement('div'); intro.className = 'overview-intro';
    const heading = document.createElement('h2');
    heading.textContent = groups.size ? workbenchText('游戏库已就绪', 'Your library is ready') : workbenchText('设备已连接', 'Device connected');
    const description = document.createElement('p');
    description.textContent = groups.size ? workbenchText('选择主机，查看游戏与图片；也可以一键补全全部主机。', 'Choose a system to browse games and artwork, or auto-complete all systems.') : workbenchText('当前存储尚未检测到游戏列表。点击“更新游戏库”，选择游戏目录后扫描。', 'No playlists detected in this storage. Use Update library to choose a game folder and scan.');
    const stats = document.createElement('div'); stats.className = 'overview-stats';
    for (const [value, label] of [[groups.size, workbenchText('个主机', 'systems')],
            [currentDeviceScan.totals?.items || 0, workbenchText('个游戏', 'games')]]) {
        const stat = document.createElement('span');
        const count = document.createElement('strong'); count.textContent = value;
        stat.append(count, document.createTextNode(' ' + label)); stats.appendChild(stat);
    }
    intro.append(heading, description, stats);
    const title = document.createElement('h2'); title.className = 'overview-systems-title';
    title.textContent = workbenchText('按主机浏览', 'Browse by system');
    const grid = document.createElement('div'); grid.className = 'overview-system-grid';
    for (const [name, count] of groups) {
        const card = document.createElement('button'); card.type = 'button'; card.className = 'overview-system-card';
        card.setAttribute('data-input-control', '');
        card.setAttribute('aria-label', workbenchText('浏览 ', 'Browse ') + name);
        const badge = document.createElement('span'); badge.className = 'overview-system-badge';
        badge.textContent = getSystemAbbreviation(name);
        const details = document.createElement('span'); details.className = 'overview-system-details';
        const label = document.createElement('strong'); label.textContent = name.replace(/^[^-]+ - /, ''); label.title = name;
        const total = document.createElement('span'); total.textContent = formatGameCount(count);
        details.append(label, total);
        const arrow = document.createElement('span'); arrow.className = 'overview-system-arrow'; arrow.textContent = '→'; arrow.setAttribute('aria-hidden', 'true');
        card.append(badge, details, arrow);
        card.onclick = () => {
            selectedLibrarySystem = name;
            renderDeviceScan(currentDeviceScan);
            selectFirstPlaylistForSystem(name);
        };
        grid.appendChild(card);
    }
    panel.appendChild(intro);
    if (groups.size) panel.append(title, grid);
    else {
        const action = document.createElement('button'); action.className = 'btn'; action.type = 'button';
        action.textContent = workbenchText('更新游戏库', 'Update game library'); action.onclick = () => openContentScan();
        panel.appendChild(action);
    }
}
