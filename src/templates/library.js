/* Browsing reads the selected file; only previewTask creates repair proposals. */
const gameLibrary = { key: null, controller: null, data: null, error: '', loading: false, limit: 100, filter: 'all', notice: '' };

function gameLibraryInput() {
    return ['playlist_path', 'system_name', 'thumbnails_dir'].map(id => document.getElementById(id).value.trim());
}

function resetGameLibrary() {
    gameLibrary.controller?.abort();
    Object.assign(gameLibrary, { key: null, controller: null, data: null, error: '', loading: false, limit: 100, filter: 'all', notice: '' });
}

async function loadGameLibrary(input, key) {
    const controller = new AbortController();
    gameLibrary.controller = controller;
    try {
        const params = new URLSearchParams({ path: input[0], system: input[1], thumbnails: input[2] });
        const response = await fetch('/api/playlist/items?' + params, { signal: controller.signal });
        const data = await response.json();
        if (!response.ok || data.error) throw new Error(data.error || String(response.status));
        if (gameLibrary.controller !== controller || key !== JSON.stringify(gameLibraryInput())) return;
        gameLibrary.data = data;
    } catch (error) {
        if (gameLibrary.controller !== controller || key !== JSON.stringify(gameLibraryInput())) return;
        if (error.name !== 'AbortError') gameLibrary.error = error.message;
    } finally {
        if (gameLibrary.controller === controller && key === JSON.stringify(gameLibraryInput())) {
            gameLibrary.loading = false;
            renderWorkbench();
        }
    }
}

function syncGameLibrary(state, batch) {
    const panel = document.getElementById('game-library');
    const input = gameLibraryInput();
    const visible = Boolean(input[0]) && !batch && !state.previewValid
        && !['scan', 'preview', 'apply'].includes(workbench.operation);
    panel.hidden = !visible;
    if (!visible) { resetGameLibrary(); return; }
    const key = JSON.stringify(input);
    if (key !== gameLibrary.key) {
        resetGameLibrary();
        gameLibrary.key = key;
        gameLibrary.loading = true;
        document.getElementById('game-library-search').value = '';
        loadGameLibrary(input, key);
    }
    const data = gameLibrary.data;
    const name = input[1] ? getSystemAbbreviation(input[1]) : input[0].replaceAll('\\', '/').split('/').pop();
    document.getElementById('workspace-title').textContent = data
        ? `${name} · ${formatGameCount(data.items.length)}` : name;
    document.getElementById('workspace-title').title = input[0];
    renderGameLibrary();
}

function filterGameLibrary() {
    gameLibrary.limit = 100;
    renderGameLibrary();
}

function gameMatchesImageFilter(item, filter) {
    return filter === 'missing' ? item.image_status === 'missing'
        : filter === 'problem' ? ['invalid', 'unreadable', 'unconfigured'].includes(item.image_status) : true;
}

function setGameLibraryFilter(filter) {
    gameLibrary.filter = filter;
    gameLibrary.limit = 100;
    gameLibrary.notice = '';
    renderGameLibrary();
}

function renderGameLibraryFilters(items) {
    for (const [filter, zh, en] of [['all', '全部', 'All'], ['missing', '缺图', 'Missing'], ['problem', '需检查', 'Check']]) {
        const button = document.getElementById('game-library-filter-' + filter);
        const count = items.filter(item => gameMatchesImageFilter(item, filter)).length;
        button.textContent = workbenchText(zh, en) + ' ' + count;
        button.setAttribute('aria-pressed', String(gameLibrary.filter === filter));
        button.disabled = gameLibrary.loading;
    }
}

function renderGameLibrary() {
    const text = workbenchText;
    const panel = document.getElementById('game-library');
    panel.setAttribute('aria-busy', String(gameLibrary.loading));
    panel.setAttribute('aria-label', text('当前游戏列表', 'Current games'));
    const search = document.getElementById('game-library-search');
    search.placeholder = text('搜索游戏或 ROM', 'Search games or ROMs');
    search.setAttribute('aria-label', search.placeholder);
    search.disabled = gameLibrary.loading || !gameLibrary.data;
    const hasImageDirectory = Boolean(gameLibraryInput()[2]);
    document.getElementById('game-library-note').textContent = text('使用“批量整理”预览名称与图片修复建议，或在游戏行中单独补图。', 'Use Organize games to preview name and artwork suggestions, or update an image from its game row.')
        + (hasImageDirectory ? '' : text(' 图片目录可在“路径设置”中指定。', ' Choose an artwork directory in Path settings.'));
    const status = document.getElementById('game-library-status');
    const retry = document.getElementById('game-library-retry');
    retry.textContent = text('重新读取', 'Retry');
    retry.hidden = !gameLibrary.error;
    const items = gameLibrary.data?.items || [];
    renderGameLibraryFilters(items);
    const query = search.value.trim().toLowerCase();
    const filtered = items.filter(item => gameMatchesImageFilter(item, gameLibrary.filter)
        && [item.label, item.rom_name].some(value => value.toLowerCase().includes(query)));
    status.textContent = gameLibrary.loading ? text('正在读取游戏列表…', 'Loading games…')
        : gameLibrary.error ? text('读取失败：', 'Could not read list: ') + gameLibrary.error
        : !items.length ? text('此列表没有游戏。', 'This list has no games.')
        : !filtered.length ? text('没有符合搜索条件的游戏。', 'No games match your search.')
        : query || gameLibrary.filter !== 'all' || filtered.length > gameLibrary.limit
            ? text(`${Math.min(filtered.length, gameLibrary.limit)} / ${items.length} 个游戏`, `${Math.min(filtered.length, gameLibrary.limit)} / ${items.length} games`) : '';
    if (gameLibrary.notice) status.textContent = gameLibrary.notice;
    const tbody = document.getElementById('game-library-rows');
    tbody.replaceChildren();
    for (const item of filtered.slice(0, gameLibrary.limit)) {
        const row = document.createElement('tr');
        const cover = document.createElement('td');
        const placeholder = document.createElement('span');
        placeholder.className = 'game-image-placeholder';
        const imageStates = {exists: text('加载图片…', 'Loading image…'), missing: text('缺少图片', 'Missing image'), invalid: text('图片损坏', 'Damaged image'), unreadable: text('图片读取失败', 'Image read failed')};
        placeholder.textContent = hasImageDirectory ? imageStates[item.image_status] || text('缺少图片', 'Missing image') : text('未设置目录', 'No folder set');
        placeholder.title = item.image_message || '';
        cover.appendChild(placeholder);
        if (item.image_url) {
            const image = document.createElement('img');
            image.alt = item.label || item.rom_name;
            image.loading = 'lazy';
            image.onload = () => { placeholder.hidden = true; };
            image.onerror = () => {
                image.hidden = true; placeholder.hidden = false;
                placeholder.textContent = text('图片读取失败', 'Image read failed');
                item.image_status = 'unreadable';
                if (item.image_path) desktopRequest('/api/artwork/status', {path: item.image_path}).then(result => {
                    if (!placeholder.isConnected) return;
                    item.image_status = result.status;
                    placeholder.textContent = imageStates[result.status] || text('图片读取失败', 'Image read failed');
                    if (result.status !== 'exists') item.image_url = null;
                    renderGameLibraryFilters(gameLibrary.data?.items || []);
                    if (gameLibrary.filter !== 'all') renderGameLibrary();
                }).catch(() => {});
            };
            image.src = item.image_url;
            cover.appendChild(image);
        }
        row.appendChild(cover);
        for (const value of [item.label || text('未命名', 'Unnamed'), item.rom_name || '—']) {
            const cell = document.createElement('td');
            cell.textContent = value;
            cell.title = value === item.rom_name ? item.rom_path : value;
            row.appendChild(cell);
        }
        const actions = document.createElement('td');
        const button = document.createElement('button');
        button.id = 'game-artwork-action-' + item.index;
        button.type = 'button'; button.className = 'btn btn-small btn-muted';
        button.textContent = !hasImageDirectory ? text('设置图片目录', 'Set image folder')
            : item.image_url ? text('更换图片', 'Replace image') : text('补图', 'Add image');
        button.setAttribute('aria-label', button.textContent + ' · ' + (item.label || item.rom_name));
        button.disabled = Boolean(workbench.operation) || !item.label;
        button.onclick = () => openArtworkDialog(item);
        actions.appendChild(button);
        if (item.artwork_result) {
            const result = document.createElement('p'); result.className = 'artwork-row-result';
            result.textContent = item.artwork_result; result.setAttribute('role', 'status');
            if (item.artwork_backup) result.title = text('旧图备份：', 'Previous image backup: ') + item.artwork_backup;
            actions.appendChild(result);
        }
        row.appendChild(actions);
        tbody.appendChild(row);
    }
    document.getElementById('game-library-table').hidden = !filtered.length;
    const more = document.getElementById('game-library-more');
    more.hidden = filtered.length <= gameLibrary.limit;
    more.textContent = text('显示更多游戏', 'Show more games');
    ['图片', '游戏名称', 'ROM 文件名', ''].forEach((label, index) => {
        document.getElementById('game-library-heading-' + index).textContent = text(label, ['Artwork', 'Game name', 'ROM filename', ''][index]);
    });
}

function retryGameLibrary() {
    resetGameLibrary();
    renderWorkbench();
}
