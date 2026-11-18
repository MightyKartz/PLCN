/* Native cover browser and docked inspector; selection never mutates a playlist. */
const gameInspector = {key:'', details:null, error:'', editing:false, draft:'', preview:null, romPlan:null, saving:false, status:''};
let visibleGameItems = [];
const narrowGameDetails = matchMedia('(max-width: 900px)');
let gameDetailsReturnTop = 0;

narrowGameDetails.addEventListener('change', () => {
    if (!document.getElementById('game-library').hidden) renderGameInspector();
});
const gameSize = value => value == null ? workbenchText('未知', 'Unknown') : value < 1024 ? value + ' B'
    : new Intl.NumberFormat(currentUILanguage === 'en' ? 'en' : 'zh', {maximumFractionDigits:1}).format(value / (value >= 1024 ** 3 ? 1024 ** 3 : value >= 1024 ** 2 ? 1024 ** 2 : 1024)) + (value >= 1024 ** 3 ? ' GB' : value >= 1024 ** 2 ? ' MB' : ' KB');
function setGameView(view) {
    gameLibrary.view = view; renderGameLibrary();
}
function inspectGame(index) {
    if (gameInspector.saving || artworkDialogState?.applying || artworkDialogState?.jobId) return;
    if (artworkDialogState?.docked) closeArtworkDialog();
    gameLibrary.activeIndex = index;
    renderGameLibrary();
    if (narrowGameDetails.matches) document.getElementById('inspector-close')?.focus({preventScroll: true});
}
function closeGameDetails() {
    if (gameInspector.saving || artworkDialogState?.applying || artworkDialogState?.jobId) return;
    const index = gameLibrary.activeIndex;
    const panel = document.querySelector('.main-panel');
    const wasDetailPage = panel.classList.contains('game-details-page');
    gameLibrary.activeIndex = null;
    renderGameLibrary();
    if (wasDetailPage) panel.scrollTop = gameDetailsReturnTop;
    const list = document.getElementById(gameLibrary.view === 'grid' ? 'game-library-grid' : 'game-library-table');
    const opener = list.querySelector(`[data-game-details="${index}"]`) || document.getElementById('game-library-search');
    opener.focus({preventScroll: true});
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
    grid.style.setProperty('--game-cover-ratio', wbCoverFrameRatio(gameLibraryInput()[1]));
    grid.classList.toggle('has-selection', Boolean(gameLibrary.selection.size));
    for (const item of items) {
        const card = wbElement('article', 'game-cover-card'); card.dataset.gameCard = item.index;
        card.classList.toggle('selected', gameLibrary.selection.has(item.index)); card.classList.toggle('inspected', gameLibrary.activeIndex === item.index);
        const open = wbElement('button', 'game-card-open'); open.type = 'button'; open.onclick = () => inspectGame(item.index);
        open.dataset.gameDetails = item.index;
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
    const item = inspectorItem();
    const loadingItem = gameLibrary.loading && gameLibrary.activeIndex !== null;
    pane.hidden = !item && !loadingItem;
    const library = document.getElementById('game-library');
    library.classList.toggle('has-inspector', !pane.hidden);
    const panel = library.closest('.main-panel');
    const page = !pane.hidden && narrowGameDetails.matches;
    const entering = page && !panel.classList.contains('game-details-page');
    if (entering) gameDetailsReturnTop = panel.scrollTop;
    panel.classList.toggle('game-details-page', page);
    if (entering) panel.scrollTop = 0;
    if (pane.hidden) return;

    const backFocused = document.activeElement?.id === 'inspector-close';
    const header = wbElement('header', 'inspector-header');
    const closeLabel = page ? workbenchText('返回游戏列表', 'Back to games') : workbenchText('关闭详情', 'Close details');
    const close = gmButton(closeLabel, closeLabel, closeGameDetails);
    close.id = 'inspector-close';
    close.className = 'inspector-close';
    close.title = closeLabel;
    close.setAttribute('aria-label', closeLabel);
    close.disabled = gameInspector.saving;
    if (!page) close.replaceChildren(wbIcon('x'));
    header.append(close);
    if (!item) {
        const status = wbElement('p', 'inspector-status', workbenchText('正在读取游戏详情…', 'Loading game details…'));
        status.setAttribute('role', 'status');
        pane.replaceChildren(header, status);
        if (backFocused) close.focus({preventScroll:true});
        return;
    }
    const key = JSON.stringify([gameLibraryInput()[0], gameLibrary.data.expected, item.index]);
    if (gameInspector.key !== key) {
        Object.assign(gameInspector, {key, details:null, error:'', editing:false, draft:item.label, preview:null, romPlan:null, status:''});
        desktopRequest('/api/games/details', {playlist:gameLibraryInput()[0], expected:gameLibrary.data.expected, index:item.index, system:gameLibraryInput()[1]})
            .then(details => {if (gameInspector.key !== key || !inspectorItem()) return; gameInspector.details = details; renderGameInspector();})
            .catch(error => {if (gameInspector.key !== key || !inspectorItem()) return; gameInspector.error = gmError(error); renderGameInspector();});
    }
    const editingFocus = document.activeElement?.id === 'inspector-name' ? [document.activeElement.selectionStart, document.activeElement.selectionEnd] : null;
    const artworkEditor = artworkDialogState?.docked ? document.getElementById('artwork-dialog') : null;
    if (artworkEditor) artworkEditor.remove();
    pane.replaceChildren(); pane.setAttribute('aria-label', workbenchText('游戏详情', 'Game details'));
    pane.append(header, wbElement('h2', 'inspector-title', item.label || item.rom_name));
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
            const hasCover = item.artwork_status ? item.artwork_status.Named_Boxarts === 'exists' : Boolean(item.image_url);
            const artwork = gmButton(hasCover ? '更换封面' : '补封面', hasCover ? 'Change artwork' : 'Add artwork', () => openArtworkDialog(item));
            artwork.id = 'inspector-artwork'; artwork.disabled = busy; actions.append(artwork);
        } else {
            const folder = gmButton('指定图片目录', 'Choose artwork folder', () => openPathSettings('thumbnails_override')); folder.id = 'inspector-artwork-folder'; actions.append(folder);
        }
        const edit = gmButton('编辑名称', 'Edit name', () => {gameInspector.editing = true; gameInspector.draft = item.label; renderGameInspector(); document.getElementById('inspector-name').focus();}); edit.id = 'inspector-edit-name'; edit.disabled = busy; actions.append(edit);
        pane.append(actions);
    }
    const art = wbElement('div', 'inspector-art');
    const emptyArt = () => art.replaceChildren(wbIcon('photo'), wbElement('span', '', workbenchText('缺封面', 'No artwork')));
    if (item.image_url) {
        const image = document.createElement('img');
        image.alt = '';
        image.onerror = emptyArt;
        image.src = item.image_url;
        art.append(image);
    } else emptyArt();
    pane.append(art);
    if (!gameInspector.editing) {
        const update = gmButton('更新 ROM', 'Update ROM', pickRomUpdate);
        update.id = 'inspector-update-rom';
        update.disabled = busy || !gameInspector.details?.rom_update_supported;
        update.title = gameInspector.details?.rom_update_supported ? workbenchText('备份并替换当前 ROM', 'Back up and replace this ROM') : workbenchText('需要可读取的单文件卡带 ROM（不超过 64 MiB）', 'Requires a readable single-file cartridge ROM (up to 64 MiB)');
        pane.append(update);
    }
    if (gameInspector.romPlan) {
        const preview = wbElement('section','inspector-rom-update');
        preview.append(wbElement('p','',workbenchText('新版文件：','New file: ')+gameInspector.romPlan.source_name),
            wbElement('p','',gameSize(gameInspector.romPlan.old_size)+' → '+gameSize(gameInspector.romPlan.new_size)),
            wbElement('p','',workbenchText('自动备份旧 ROM，保留路径、名称、图片与存档文件。更新前请退出 RetroArch。', 'Back up the old ROM; keep its path, title, artwork and saves. Quit RetroArch before updating.')));
        const apply = gmButton('更新', 'Update', applyRomUpdate, false); apply.id = 'inspector-rom-confirm'; apply.disabled = busy;
        const cancel = gmButton('取消', 'Cancel', () => {gameInspector.romPlan=null; renderGameInspector();}); cancel.disabled = busy;
        preview.append(apply,cancel); pane.append(preview);
    }
    const details = gameInspector.details;
    if (details?.rom_update && details.rom_update.status !== 'restored') {
        const restore = gmButton('恢复旧版 ROM', 'Restore previous ROM', restoreRomUpdate); restore.id='inspector-restore-rom'; restore.disabled=busy; pane.append(restore);
    }
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
    if (artworkEditor) pane.append(artworkEditor);
    if (backFocused) close.focus({preventScroll:true});
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

async function pickRomUpdate() {
    const item = inspectorItem(); if (!item || workbench.operation) return;
    const key = gameInspector.key;
    try {
        if (!beginWorkbenchOperation('rom-picker')) return;
        let picked;
        try {picked=await desktopRequest('/api/desktop/pick',{kind:'rom'});}
        finally {endWorkbenchOperation();}
        if (!picked.path || gameInspector.key !== key) return;
        await prepareRomUpdate({playlist:gameLibraryInput()[0],expected:gameLibrary.data.expected,index:item.index,system:gameLibraryInput()[1],source:picked.path});
    } catch (error) {gameInspector.status=gmError(error);}
    renderGameInspector();
}
async function applyRomUpdate() {
    const item=inspectorItem(), plan=gameInspector.romPlan; if (!item || !plan || workbench.operation) return;
    gameInspector.romPlan=null;
    try {
        const {result}=await inspectorJob('/api/games/apply',{preview_job_id:plan.id});
        if (result.status !== 'applied') {if (gameInspector.details) gameInspector.details.rom_update={id:result.operation_id,status:result.restored?'restored':'restore_pending'}; throw new Error((result.error || workbenchText('更新失败','Update failed'))+(result.restored ? workbenchText('；旧版已恢复','; previous ROM restored') : workbenchText('；可在此处恢复旧版','; restore the previous ROM here')));}
        gameInspector.key=''; retryGameLibrary(item.index);
        showGameLibraryToast(workbenchText('ROM 已更新，旧版已备份。','ROM updated; previous version backed up.'));
    } catch (error) {gameInspector.status=gmError(error); renderGameInspector();}
}
async function restoreRomUpdate() {
    const item=inspectorItem(), record=gameInspector.details?.rom_update; if (!item || !record || workbench.operation) return;
    try {
        await inspectorJob('/api/m3u/recover',{id:record.id,action:'restore'});
        gameInspector.key='';retryGameLibrary(item.index);showGameLibraryToast(workbenchText('已恢复旧版 ROM。','Previous ROM restored.'));
    } catch (error) {gameInspector.status=gmError(error);renderGameInspector();}
}

async function prepareRomUpdate(payload) {
    gameInspector.romPlan=null; gameInspector.status='';
    const preview=await inspectorJob('/api/games/preview',{...payload,mode:'rom_update'});
    if (!preview.result.can_apply) gameInspector.status=workbenchText('文件内容相同，无需更新。','The file is identical; no update needed.');
    else gameInspector.romPlan={...preview.result,id:preview.id};
    renderGameInspector();
}
async function updateImportedRom(candidate) {
    if (workbench.operation) return;
    closeGameManagement();
    try {
        const index=currentDeviceScan.playlists.findIndex(row=>row.path===candidate.playlist);
        if (index<0) throw new Error(workbenchText('请先重新读取游戏库。','Reload the library first.'));
        await selectScannedPlaylist(index);
        if (gameLibrary.loading || !gameLibrary.data) {const input=gameLibraryInput(); await loadGameLibrary(input,JSON.stringify(input));}
        if (gameLibrary.data?.expected!==candidate.expected) throw new Error(workbenchText('列表已变化，请重新选择游戏。','The playlist changed; select the game again.'));
        inspectGame(candidate.index);await prepareRomUpdate(candidate);
    } catch (error) {showGameLibraryToast(gmError(error));}
}
