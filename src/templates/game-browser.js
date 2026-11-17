/* Native cover browser and docked inspector; selection never mutates a playlist. */
const gameInspector = {key:'', details:null, error:'', editing:false, draft:'', preview:null, saving:false, status:''};
let visibleGameItems = [];
const gameSize = value => value == null ? workbenchText('未知', 'Unknown') : value < 1024 ? value + ' B'
    : new Intl.NumberFormat(currentUILanguage === 'en' ? 'en' : 'zh', {maximumFractionDigits:1}).format(value / (value >= 1024 ** 3 ? 1024 ** 3 : value >= 1024 ** 2 ? 1024 ** 2 : 1024)) + (value >= 1024 ** 3 ? ' GB' : value >= 1024 ** 2 ? ' MB' : ' KB');
function setGameView(view) {
    gameLibrary.view = view; renderGameLibrary();
}
function inspectGame(index) {
    if (gameInspector.saving) return;
    gameLibrary.activeIndex = index; renderGameLibrary();
}
function toggleGameSelection(index, checked) {
    if (checked) gameLibrary.selection.add(index); else gameLibrary.selection.delete(index);
    document.querySelectorAll('[data-game-select="' + index + '"]').forEach(input => {input.checked = checked;});
    document.querySelector('[data-game-card="' + index + '"]')?.classList.toggle('selected', checked);
    renderGameSelection(visibleGameItems);
}
function renderGameBrowser(items) {
    visibleGameItems = items;
    const switcher = document.getElementById('game-view-switch'); switcher.replaceChildren();
    for (const [view, zh, en, icon] of [['grid','封面视图','Cover view','layout-grid'], ['list','列表视图','List view','list']]) {
        const button = gmButton(zh, en, () => setGameView(view)); button.id = 'game-view-' + view;
        button.className = 'view-switch'; button.replaceChildren(wbIcon(icon)); button.title = workbenchText(zh, en);
        button.setAttribute('aria-label', button.title); button.setAttribute('aria-pressed', String(gameLibrary.view === view)); switcher.append(button);
    }
    const grid = document.getElementById('game-library-grid'); grid.replaceChildren(); grid.hidden = gameLibrary.view !== 'grid';
    grid.classList.toggle('has-selection', Boolean(gameLibrary.selection.size));
    for (const item of items) {
        const card = wbElement('article', 'game-cover-card'); card.dataset.gameCard = item.index;
        card.classList.toggle('selected', gameLibrary.selection.has(item.index)); card.classList.toggle('inspected', gameLibrary.activeIndex === item.index);
        const open = wbElement('button', 'game-card-open'); open.type = 'button'; open.onclick = () => inspectGame(item.index);
        open.setAttribute('aria-label', workbenchText('查看详情：', 'View details: ') + (item.label || item.rom_name));
        open.setAttribute('aria-pressed', String(gameLibrary.activeIndex === item.index));
        const art = wbElement('div', 'game-card-art');
        if (item.image_url) {
            const image = document.createElement('img'); image.src = item.image_url; image.alt = ''; image.loading = 'lazy';
            image.onerror = () => {image.remove(); art.append(wbIcon('photo'), wbElement('span', '', workbenchText('图片读取失败', 'Image unavailable')));}; art.append(image);
        } else {
            art.append(wbIcon('photo'), wbElement('span', '', workbenchText('缺封面', 'No artwork')));
        }
        open.append(art, wbElement('span', 'game-card-name', item.label || item.rom_name)); card.append(open);
        const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.className = 'game-card-select';
        checkbox.dataset.gameSelect = item.index; checkbox.checked = gameLibrary.selection.has(item.index); checkbox.disabled = Boolean(workbench.operation);
        checkbox.setAttribute('aria-label', workbenchText('选择 ', 'Select ') + (item.label || item.rom_name));
        checkbox.onchange = () => toggleGameSelection(item.index, checkbox.checked); card.append(checkbox);
        const menu = wbElement('div', 'game-card-menu'); appendGameManagementActions(menu, item); card.append(menu); grid.append(card);
    }
    renderGameInspector();
}
function inspectorPair(parent, zh, en, value) {
    const row = wbElement('div', 'inspector-pair'); row.append(wbElement('dt', '', workbenchText(zh, en)), wbElement('dd', '', value)); parent.append(row);
}
function inspectorItem() {
    return gameLibrary.data?.items.find(item => item.index === gameLibrary.activeIndex);
}
function renderGameInspector() {
    const pane = document.getElementById('game-inspector');
    const item = inspectorItem(); pane.hidden = !item;
    document.getElementById('game-library').classList.toggle('has-inspector', Boolean(item));
    if (!item) return;
    const key = JSON.stringify([gameLibraryInput()[0], gameLibrary.data.expected, item.index]);
    if (gameInspector.key !== key) {
        Object.assign(gameInspector, {key, details:null, error:'', editing:false, draft:item.label, preview:null, status:''});
        desktopRequest('/api/games/details', {playlist:gameLibraryInput()[0], expected:gameLibrary.data.expected, index:item.index})
            .then(details => {if (gameInspector.key !== key || !inspectorItem()) return; gameInspector.details = details; renderGameInspector();})
            .catch(error => {if (gameInspector.key !== key || !inspectorItem()) return; gameInspector.error = gmError(error); renderGameInspector();});
    }
    const editingFocus = document.activeElement?.id === 'inspector-name' ? [document.activeElement.selectionStart, document.activeElement.selectionEnd] : null;
    pane.replaceChildren(); pane.setAttribute('aria-label', workbenchText('游戏详情', 'Game details'));
    const header = wbElement('header', 'inspector-header'); header.append(wbElement('h2', 'sr-only', workbenchText('游戏详情', 'Game details')));
    const close = gmButton('关闭详情', 'Close details', () => {gameLibrary.activeIndex = null; renderGameLibrary();});
    close.className = 'inspector-close'; close.replaceChildren(wbIcon('x'));
    close.title = workbenchText('关闭详情', 'Close details'); close.setAttribute('aria-label', close.title); close.disabled = gameInspector.saving; header.append(close); pane.append(header);
    const art = wbElement('div', 'inspector-art');
    const emptyArt = () => art.replaceChildren(wbIcon('photo'), wbElement('span', '', workbenchText('缺封面', 'No artwork')));
    if (item.image_url) {const image = document.createElement('img'); image.src = item.image_url; image.alt = item.label; image.onerror = () => {image.remove(); emptyArt();}; art.append(image);} else emptyArt();
    pane.append(art, wbElement('h3', 'inspector-title', item.label || item.rom_name), wbElement('p', 'inspector-filename', (item.rom_name || '').replace(/\.[^./\\]+$/, '')));
    const busy = Boolean(workbench.operation);
    if (gameInspector.editing) {
        const label = wbElement('label', 'inspector-edit-label', workbenchText('显示名称', 'Display name'));
        const input = document.createElement('input'); input.id = 'inspector-name'; input.value = gameInspector.draft; input.maxLength = 300; input.disabled = gameInspector.saving;
        input.oninput = () => {gameInspector.draft = input.value;};
        input.onkeydown = event => {
            if (event.key === 'Enter' && !gameInspector.saving) saveGameName();
            if (event.key === 'Escape' && !gameInspector.saving) {gameInspector.editing = false; renderGameInspector();}
        };
        label.append(input); pane.append(label);
        const controls = wbElement('div', 'inspector-edit-actions');
        const save = gmButton('保存', 'Save', saveGameName, false); save.id = 'inspector-save'; save.disabled = busy;
        const cancel = gmButton('取消', 'Cancel', () => {gameInspector.editing = false; renderGameInspector();}); cancel.disabled = busy; controls.append(save, cancel); pane.append(controls);
    } else {
        const actions = wbElement('div', 'inspector-actions');
        if (gameLibraryInput()[2]) {
            const artwork = gmButton('更换封面', 'Change artwork', () => openArtworkDialog(item)); artwork.id = 'inspector-artwork'; artwork.disabled = busy; actions.append(artwork);
        } else {
            const folder = gmButton('指定图片目录', 'Choose artwork folder', () => openPathSettings('thumbnails_override')); folder.id = 'inspector-artwork-folder'; actions.append(folder);
        }
        const edit = gmButton('编辑名称', 'Edit name', () => {gameInspector.editing = true; gameInspector.draft = item.label; renderGameInspector(); document.getElementById('inspector-name').focus();}); edit.id = 'inspector-edit-name'; edit.disabled = busy; actions.append(edit);
        pane.append(actions);
    }
    const details = gameInspector.details;
    if (details && details.file_status !== 'present') pane.append(wbElement('p', 'inspector-warning', workbenchText('文件未找到或路径尚未映射，请检查设备连接与扫描配置。', 'File missing or path not mapped. Check the connection and scan configuration.')));
    const meta = wbElement('dl', 'inspector-metadata');
    const storage = {local:workbenchText('本地', 'Local'), internal:workbenchText('内部存储', 'Internal storage'), card:workbenchText('存储卡', 'Storage card')}[wbStorageKind(item.rom_path)];
    const core = details?.core_name && details.core_name !== 'DETECT' ? details.core_name : details?.core_path && details.core_path !== 'DETECT' ? details.core_path.replaceAll('\\', '/').split('/').pop() : details ? workbenchText('由 RetroArch 选择', 'Choose in RetroArch') : '…';
    inspectorPair(meta, '主机', 'System', getSystemAbbreviation(gameLibraryInput()[1]));
    inspectorPair(meta, '位置', 'Storage', storage);
    inspectorPair(meta, '大小', 'Size', details ? gameSize(details.size) : '…');
    pane.append(meta);
    const more = wbElement('details', 'inspector-more'); more.id = 'inspector-more';
    more.append(wbElement('summary', '', workbenchText('更多信息', 'More info')));
    const moreMeta = wbElement('dl', 'inspector-metadata');
    inspectorPair(moreMeta, '核心', 'Core', core);
    inspectorPair(moreMeta, '游戏文件', 'Game file', item.rom_path || '—');
    const missing = missingArtworkKinds(item);
    const missingKinds = missing.length ? missing : (item.artwork_status || item.image_url ? [] : ['Named_Boxarts']);
    inspectorPair(moreMeta, '资料状态', 'Artwork status', !missingKinds.length
        ? workbenchText('图片已齐全', 'Artwork complete')
        : workbenchText('缺少：', 'Missing: ') + missingKinds.map(kind => artworkKindLabel(kind)).join(workbenchText('、', ', ')));
    more.append(moreMeta); pane.append(more);
    const footer = wbElement('footer', 'inspector-footer');
    const remove = gmButton('移出列表', 'Remove from playlist', () => openGameRemoval([item.index])); remove.id = 'inspector-remove'; remove.disabled = busy; remove.className = 'btn btn-text';
    remove.title = workbenchText('保留游戏文件、封面和存档', 'Keeps game files, artwork and saves'); footer.append(remove); pane.append(footer);
    const status = wbElement('p', 'inspector-status', gameInspector.error || gameInspector.status); status.id = 'inspector-status'; status.setAttribute('role', 'status'); pane.append(status);
    if (editingFocus) {const input = document.getElementById('inspector-name'); input?.focus(); input?.setSelectionRange(...editingFocus);}
}
async function inspectorJob(route, payload) {
    if (!beginWorkbenchOperation('game-edit')) throw new Error(workbenchText('请等待当前任务完成。', 'Wait for the current task to finish.'));
    gameInspector.saving = true; renderGameInspector();
    try {return await runGameJob(route, payload, job => {gameInspector.status = job.connectionError ? job.message : currentUILanguage === 'en' ? 'Processing…' : job.message; const status = document.getElementById('inspector-status'); if (status) status.textContent = gameInspector.status;});}
    finally {gameInspector.saving = false; endWorkbenchOperation();}
}
async function saveGameName() {
    const item = inspectorItem(); if (!item) return;
    try {
        const preview = await inspectorJob('/api/games/preview', {mode:'edit', playlist:gameLibraryInput()[0], expected:gameLibrary.data.expected, index:item.index, label:gameInspector.draft, thumbnails:gameLibraryInput()[2], system:gameLibraryInput()[1]});
        if (!preview.result.can_apply) {gameInspector.status = workbenchText('名称没有变化。', 'The name has not changed.'); renderGameInspector(); return;}
        const {result} = await inspectorJob('/api/games/apply', {preview_job_id:preview.id});
        if (result.status !== 'applied') throw new Error(result.error || result.status);
        gameInspector.editing = false;
        retryGameLibrary(item.index); refreshWorkbenchOverview();
        showGameLibraryToast(workbenchText('名称已保存，修改前的列表已备份。', 'Name saved. The previous playlist was backed up.'));
    } catch (error) {gameInspector.status = gmError(error); renderGameInspector();}
}
