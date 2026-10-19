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
    // "Missing" means at least one of the three artwork types is absent, which is
    // exactly when a row can be filled in. A list with no artwork directory, or one
    // whose device could not be read, belongs under "Check" instead.
    if (filter === 'missing') {
        if (!item.artwork_status) return item.image_status === 'missing';
        return !['unconfigured', 'unreadable'].includes(item.image_status) && missingArtworkKinds(item).length > 0;
    }
    return filter === 'problem' ? ['invalid', 'unreadable', 'unconfigured'].includes(item.image_status) : true;
}

const ARTWORK_KIND_LABELS = {Named_Boxarts: ['封面', 'Box art'], Named_Snaps: ['游戏截图', 'Screenshot'], Named_Titles: ['标题图', 'Title screen']};
const ARTWORK_KIND_STATES = {exists: ['已有', 'Present'], invalid: ['损坏', 'Damaged']};
const ARTWORK_KIND_MARKERS = {exists: '✓', invalid: '!', missing: '○'};

function artworkKindLabel(kind) {
    const [zh, en] = ARTWORK_KIND_LABELS[kind] || [kind, kind];
    return workbenchText(zh, en);
}

function artworkKindState(status) {
    const [zh, en] = ARTWORK_KIND_STATES[status] || ['缺少', 'Missing'];
    return workbenchText(zh, en);
}

/* One chip per artwork type so a row shows which of the three images it actually has. */
function renderArtworkKindChips(cell, item) {
    const chips = document.createElement('div');
    chips.className = 'artwork-chips';
    for (const kind of Object.keys(ARTWORK_KIND_LABELS)) {
        const status = item.artwork_status[kind] || 'missing';
        const chip = document.createElement('span');
        chip.className = 'artwork-chip artwork-chip-' + status;
        chip.textContent = ARTWORK_KIND_MARKERS[status] + ' ' + artworkKindLabel(kind);
        chip.title = artworkKindLabel(kind) + ' · ' + artworkKindState(status);
        chips.appendChild(chip);
    }
    cell.appendChild(chips);
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

function missingArtworkKinds(item) {
    if (!item.artwork_status) return [];
    return ['Named_Boxarts', 'Named_Snaps', 'Named_Titles']
        .filter(kind => (item.artwork_status[kind] || 'missing') !== 'exists');
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
        if (item.artwork_status && !['unconfigured', 'unreadable'].includes(item.image_status)) renderArtworkKindChips(cover, item);
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
        const missing = missingArtworkKinds(item).map(kind => artworkKindLabel(kind));
        button.textContent = !hasImageDirectory ? text('设置图片目录', 'Set image folder')
            : item.image_url && !missing.length ? text('更换图片', 'Replace image') : text('补图', 'Add image');
        if (missing.length) button.title = text('缺少：', 'Missing: ') + missing.join(text('、', ', '));
        button.setAttribute('aria-label', button.textContent + (missing.length ? '（' + missing.join(text('、', ', ')) + '）' : '') + ' · ' + (item.label || item.rom_name));
        button.disabled = Boolean(workbench.operation) || !item.label;
        button.onclick = () => openArtworkDialog(item);
        actions.appendChild(button);
        if (hasImageDirectory && !item.image_url) {
            const importButton = document.createElement('button');
            importButton.type = 'button'; importButton.className = 'btn btn-small btn-muted artwork-import-inline';
            importButton.textContent = text('导入图片', 'Import image');
            importButton.setAttribute('aria-label', importButton.textContent + ' · ' + item.label);
            importButton.disabled = Boolean(workbench.operation) || !item.label;
            importButton.onclick = () => openArtworkImport(item);
            actions.appendChild(importButton);
        }
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
