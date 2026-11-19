/* Browsing is read-only; management actions use server-owned review plans. */
const gameLibrary = { key: null, controller: null, data: null, error: '', loading: false, limit: 100, filter: 'all', notice: '', selection: new Set(), view: 'grid', activeIndex: null };

function gameLibraryInput() {
    return ['playlist_path', 'system_name'].map(id => document.getElementById(id).value.trim()).concat(getThumbnailsDirectory());
}

function resetGameLibrary() {
    gameLibrary.controller?.abort();
    gameLibrary.selection.clear();
    gameLibrary.activeIndex = null;
    Object.assign(gameLibrary, { key: null, controller: null, data: null, error: '', loading: false, limit: 100, filter: 'all', notice: '' });
}

async function loadGameLibrary(input, key) {
    const controller = new AbortController();
    gameLibrary.controller = controller;
    try {
        const params = new URLSearchParams({ path: input[0], system: input[1], thumbnails: input[2] });
        const data = await desktopRequest('/api/playlist/items?' + params, undefined, {signal: controller.signal});
        if (data.error) throw new Error(data.error);
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

function syncGameLibrary(state) {
    const panel = document.getElementById('game-library');
    const input = gameLibraryInput();
    const visible = Boolean(input[0]) && !state.previewValid
        && !['scan', 'preview', 'apply'].includes(workbench.operation);
    panel.hidden = !visible;
    if (!visible) {
        panel.setAttribute('aria-busy', 'false');
        panel.closest('.main-panel').classList.remove('game-details-page');
        resetGameLibrary();
        return;
    }
    const key = JSON.stringify(input);
    if (key !== gameLibrary.key) {
        resetGameLibrary();
        gameLibrary.key = key;
        gameLibrary.loading = true;
        document.getElementById('game-library-search').value = '';
        loadGameLibrary(input, key);
    }
    const discs = document.getElementById('game-library-discs');
    discs.hidden = !['Sega - Saturn','Sony - PlayStation','SS','PS1'].includes(input[1]);
    discs.disabled = state.busy || gameLibrary.loading;
    const data = gameLibrary.data;
    const name = input[1] ? getSystemAbbreviation(input[1]) : input[0].replaceAll('\\', '/').split('/').pop();
    const title = document.getElementById('workspace-title');
    title.textContent = name;
    if (data && typeof title.append === 'function') {
        title.append(wbElement('span', 'workspace-count', formatGameCount(data.items.length)));
    }
    title.title = input[0];
    renderGameLibrary();
}

function filterGameLibrary() {
    gameLibrary.limit = 100;
    renderGameLibrary();
}

function gameMatchesImageFilter(item, filter) {
    // "Missing" means at least one of the three artwork types is absent, which is
    // exactly when a row can be filled in. Directory setup is a library-level issue.
    if (filter === 'missing') {
        if (!item.artwork_status) return item.image_status === 'missing';
        return !['unconfigured', 'unreadable'].includes(item.image_status) && missingArtworkKinds(item).length > 0;
    }
    return filter === 'problem' ? ['invalid', 'unreadable'].includes(item.image_status)
        || Object.values(item.artwork_status || {}).includes('invalid') : true;
}

const ARTWORK_KIND_LABELS = {Named_Boxarts: ['封面', 'Box art'], Named_Snaps: ['游戏截图', 'Screenshot'], Named_Titles: ['标题图', 'Title screen']};
const ARTWORK_KIND_STATES = {exists: ['已有', 'Present'], invalid: ['损坏', 'Damaged']};

function artworkKindLabel(kind) {
    const [zh, en] = ARTWORK_KIND_LABELS[kind] || [kind, kind];
    return workbenchText(zh, en);
}

function artworkKindState(status) {
    const [zh, en] = ARTWORK_KIND_STATES[status] || ['缺少', 'Missing'];
    return workbenchText(zh, en);
}

function setGameLibraryFilter(filter) {
    gameLibrary.filter = filter;
    gameLibrary.limit = 100;
    gameLibrary.notice = '';
    renderGameLibrary();
}

let gameLibraryToastTimer = null;

function showGameLibraryToast(message) {
    const toast = document.getElementById('game-library-toast');
    if (!toast) return;
    clearTimeout(gameLibraryToastTimer);
    toast.textContent = message;
    toast.hidden = !message;
    if (message) gameLibraryToastTimer = setTimeout(() => { toast.hidden = true; }, 6000);
}

function renderGameLibraryFilters(items) {
    for (const [filter, zh, en] of [['all', '全部', 'All'], ['missing', '图片待补全', 'Missing artwork'], ['problem', '需检查', 'Check']]) {
        const button = document.getElementById('game-library-filter-' + filter);
        const count = items.filter(item => gameMatchesImageFilter(item, filter)).length;
        button.textContent = workbenchText(zh, en) + ' ' + count;
        button.setAttribute('aria-pressed', String(gameLibrary.filter === filter));
        button.disabled = gameLibrary.loading;
        if (filter === 'problem') button.hidden = count === 0 && gameLibrary.filter !== 'problem';
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
    const systemName = gameLibraryInput()[1];
    const systemAbbreviation = systemName ? getSystemAbbreviation(systemName) : '';
    search.placeholder = systemAbbreviation
        ? text(`搜索 ${systemAbbreviation} 游戏`, `Search ${systemAbbreviation} games`)
        : text('搜索游戏或 ROM', 'Search games or ROMs');
    search.setAttribute('aria-label', search.placeholder);
    search.disabled = gameLibrary.loading || !gameLibrary.data;
    const hasImageDirectory = Boolean(gameLibraryInput()[2]);
    document.getElementById('image-directory-notice').hidden = hasImageDirectory;
    document.getElementById('image-directory-message').textContent = text('尚未指定图片目录，设置后可检查和补全游戏图片。', 'Choose an artwork folder to check and fill in game images.');
    document.getElementById('choose-image-directory').textContent = text('指定图片目录', 'Choose artwork folder');
    const status = document.getElementById('game-library-status');
    const retry = document.getElementById('game-library-retry');
    retry.textContent = text('重新读取', 'Retry');
    retry.hidden = !gameLibrary.error;
    const items = (gameLibrary.data?.items || []).filter(item => typeof workbenchOverview === 'undefined'
        || workbenchOverview.scope === 'all' || wbStorageKind(item.rom_path) === workbenchOverview.scope);
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
    if (gameLibrary.notice) {
        showGameLibraryToast(gameLibrary.notice);
        gameLibrary.notice = '';
    }
    const tbody = document.getElementById('game-library-rows');
    tbody.replaceChildren();
    for (const item of filtered.slice(0, gameLibrary.limit)) {
        const row = document.createElement('tr');
        row.dataset.gameRow = item.index;
        row.classList.toggle('selected', gameLibrary.selection.has(item.index));
        const selectCell = document.createElement('td');
        selectCell.className = 'game-select-cell';
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'game-row-select';
        checkbox.dataset.gameSelect = item.index;
        checkbox.checked = gameLibrary.selection.has(item.index);
        checkbox.disabled = Boolean(workbench.operation);
        checkbox.setAttribute('aria-label', text('选择 ', 'Select ') + (item.label || item.rom_name));
        checkbox.onchange = () => toggleGameSelection(item.index, checkbox.checked);
        selectCell.appendChild(checkbox);
        const cover = document.createElement('td');
        const placeholder = document.createElement('span');
        placeholder.className = 'game-image-placeholder';
        const imageStates = {exists: text('加载封面…', 'Loading cover…'), missing: text('缺封面', 'Missing cover'), invalid: text('图片损坏', 'Damaged image'), unreadable: text('图片读取失败', 'Image read failed')};
        placeholder.setAttribute('role', 'img');
        placeholder.appendChild(wbIcon('photo'));
        const setPlaceholderLabel = status => {
            const label = imageStates[status] || imageStates.missing;
            placeholder.title = label;
            placeholder.setAttribute('aria-label', label);
        };
        setPlaceholderLabel(item.image_status);
        cover.appendChild(placeholder);
        if (item.image_url) {
            const image = document.createElement('img');
            image.alt = '';
            placeholder.hidden = true;
            image.loading = 'lazy';
            image.onerror = () => {
                image.hidden = true; placeholder.hidden = false;
                setPlaceholderLabel('unreadable');
                item.image_status = 'unreadable';
                if (item.image_path) desktopRequest('/api/artwork/status', {path: item.image_path}).then(result => {
                    if (!placeholder.isConnected) return;
                    item.image_status = result.status;
                    setPlaceholderLabel(result.status);
                    if (result.status !== 'exists') item.image_url = null;
                    renderGameLibraryFilters(gameLibrary.data?.items || []);
                    if (gameLibrary.filter !== 'all') renderGameLibrary();
                }).catch(() => {});
            };
            image.src = item.image_url;
            cover.appendChild(image);
        }
        const titleCell = document.createElement('td');
        const titleButton = wbElement('button', 'game-name-button', item.label || item.rom_name || text('未命名', 'Unnamed'));
        titleButton.type = 'button';
        titleButton.dataset.gameDetails = item.index;
        titleButton.onclick = () => inspectGame(item.index);
        titleCell.appendChild(titleButton);
        row.append(selectCell, cover, titleCell);
        tbody.appendChild(row);
    }
    document.getElementById('game-library-table').hidden = !filtered.length || gameLibrary.view !== 'list';
    const more = document.getElementById('game-library-more');
    more.hidden = filtered.length <= gameLibrary.limit;
    more.textContent = text('显示更多游戏', 'Show more games');
    ['封面', '游戏名称'].forEach((label, index) => {
        document.getElementById('game-library-heading-' + index).textContent = text(label, ['Cover', 'Game name'][index]);
    });
    renderGameBrowser(filtered.slice(0, gameLibrary.limit));
    renderGameSelection(filtered.slice(0, gameLibrary.limit));
}

function retryGameLibrary(activeIndex = null) {
    const input = gameLibraryInput();
    const key = JSON.stringify(input);
    const filter = key === gameLibrary.key ? gameLibrary.filter : 'all';
    const limit = key === gameLibrary.key ? gameLibrary.limit : 100;
    resetGameLibrary();
    Object.assign(gameLibrary, {key, loading:true, activeIndex, filter, limit});
    loadGameLibrary(input, key);
    renderWorkbench();
}
