/* File copies and playlist edits have separate previews. No ROM-delete action. */
const gameManagement = {mode:'import', root:'', sources:[], setup:null, preview:null, job:null, busy:false, generation:0};
const gmField = name => document.getElementById('gm-' + name);
function gmButton(zh, en, action, muted = true) {
    const button = wbElement('button', muted ? 'btn btn-muted' : 'btn', workbenchText(zh, en));
    button.type = 'button'; button.onclick = action; return button;
}
function gmError(error) {
    if (currentUILanguage !== 'en') return error.message;
    const message = uiText(error.message);
    if (!/[\u4e00-\u9fff]/.test(message)) return message;
    const separator = error.message.indexOf('：');
    if (separator >= 0) {
        const prefix = uiText(error.message.slice(0, separator + 1));
        if (!/[\u4e00-\u9fff]/.test(prefix)) return prefix + error.message.slice(separator + 1);
    }
    return 'Could not complete this operation. Check the source, destination and connection, then preview again.';
}
function gmInvalidate() {
    gameManagement.preview = null;
    gmField('apply').hidden = true;
    gmField('results').replaceChildren(wbElement('h3', '', workbenchText('内容预览', 'Preview')), wbElement('p', 'gm-preview-placeholder', workbenchText('选择来源和目标后分析，检查新增游戏、重复文件、空间与冲突。', 'Choose the source and destination, then analyze new games, duplicates, space and conflicts.')));
    gmField('status').textContent = workbenchText('确认来源和目标后，先预览导入内容。', 'Choose the source and destination, then preview the import.');
}
function gmWorkspace(mode) {
    const workspace = document.getElementById('game-management-workspace'); workspace.replaceChildren(); workspace.hidden = false;
    workspace.parentElement.classList.add('managing-games'); gameManagement.open = true;
    const section = wbElement('section', 'game-management-workspace gm-mode-' + mode); section.id = 'gm-dialog';
    section.setAttribute('aria-labelledby', 'gm-title');
    const header = wbElement('header', 'gm-workspace-header');
    const title = wbElement('h2', '', mode === 'import' ? workbenchText('添加游戏', 'Add games') : workbenchText('移出列表', 'Remove from playlist'));
    title.id = 'gm-title'; header.append(title, gmButton('返回游戏库', 'Back to library', closeGameManagement));
    const body = wbElement('div', 'gm-workspace-body');
    const form = wbElement('fieldset', 'gm-fields'); form.id = 'gm-fields';
    const results = wbElement('div', 'gm-results'); results.id = 'gm-results'; results.setAttribute('aria-live', 'polite');
    body.append(form, results);
    const status = wbElement('p', 'gm-workspace-status'); status.id = 'gm-status'; status.setAttribute('role', 'status');
    const footer = wbElement('footer', 'gm-workspace-footer');
    const cancel = gmButton('取消任务', 'Cancel task', async () => {
        if (gameManagement.job) await desktopRequest('/api/jobs/cancel', {job_id:gameManagement.job});
    }); cancel.id = 'gm-cancel'; cancel.hidden = true;
    const preview = gmButton('分析导入内容', 'Analyze import', previewGameImport, false); preview.id = 'gm-preview'; preview.hidden = mode !== 'import';
    const apply = gmButton(mode === 'import' ? '确认导入' : '确认移出列表', mode === 'import' ? 'Import games' : 'Remove entries', applyGameManagement, false);
    apply.id = 'gm-apply'; apply.hidden = true;
    footer.append(status, cancel, preview, apply); section.append(header, body, footer); workspace.append(section);
    title.tabIndex = -1; title.focus(); return form;
}
function closeGameManagement() {
    if (gameManagement.busy) return;
    ++gameManagement.generation; gameManagement.open = false;
    const workspace = document.getElementById('game-management-workspace'); workspace.hidden = true;
    workspace.parentElement.classList.remove('managing-games'); document.getElementById('manual-add-button').focus();
}
function gmInput(form, id, zh, en, value = '') {
    const label = wbElement('label', 'gm-field', workbenchText(zh, en));
    const input = wbElement('input', ''); input.id = 'gm-' + id; input.type = 'text'; input.value = value;
    input.oninput = gmInvalidate; label.append(input); form.append(label); return input;
}
async function openGameImport() {
    if (workbench.operation) return;
    const root = document.getElementById('retroarch_root').value;
    if (!root) { showStatus(workbenchText('请先打开 RetroArch 游戏库。', 'Open a RetroArch library first.'), 'error'); return; }
    const generation = ++gameManagement.generation;
    Object.assign(gameManagement, {mode:'import', root, sources:[], setup:null, preview:null});
    const form = gmWorkspace('import');
    gmField('preview').disabled = true; form.disabled = true;
    gmField('status').textContent = workbenchText('正在读取目标游戏库…', 'Loading the destination library…');
    try {
        const setup = await desktopRequest('/api/content/setup?root=' + encodeURIComponent(root));
        if (generation !== gameManagement.generation) return;
        gameManagement.setup = setup;
        const originPane = wbElement('section', 'gm-origin-pane');
        originPane.append(wbElement('h3', '', workbenchText('从哪里添加', 'Add from')));
        const originCards = wbElement('div', 'gm-source-cards');
        const scanCard = wbElement('button', 'gm-source-card'); scanCard.type = 'button'; scanCard.id = 'gm-source-scan';
        const scanBody = wbElement('span', 'gm-source-card-body');
        scanBody.append(wbElement('strong', '', workbenchText('扫描游戏目录', 'Scan game folders')), wbElement('span', '', workbenchText('找出游戏目录里还没加入列表的游戏', "Find games in your folders that aren't in a playlist yet")));
        scanCard.append(wbIcon('device-gamepad'), scanBody);
        scanCard.onclick = () => { closeGameManagement(); openAutoScan(); };
        const importCard = wbElement('button', 'gm-source-card'); importCard.type = 'button'; importCard.id = 'gm-source-import'; importCard.setAttribute('aria-pressed', 'true');
        const importBody = wbElement('span', 'gm-source-card-body');
        importBody.append(wbElement('strong', '', workbenchText('从电脑导入', 'Import from computer')), wbElement('span', '', workbenchText('复制电脑上的游戏到游戏库', 'Copy games from this computer into the library')));
        const importCheck = wbElement('span', 'gm-source-check'); importCheck.append(wbIcon('circle-check'));
        importCard.append(wbIcon('device-sd-card'), importBody, importCheck);
        originCards.append(scanCard, importCard); originPane.append(originCards); form.append(originPane);
        const sourcePane = wbElement('section', 'gm-source-pane');
        sourcePane.append(wbElement('h3', '', workbenchText('来源', 'Source')), wbElement('p', '', workbenchText('从电脑选取游戏文件或目录，源文件会保留。', 'Choose game files or a folder on your computer. Source files are kept.')));
        const buttons = wbElement('div', 'gm-source-buttons');
        const files = gmButton('选择文件', 'Choose files', () => gmPickSource('files')); files.id = 'gm-pick-files';
        const folder = gmButton('选择目录', 'Choose folder', () => gmPickSource('directory')); folder.id = 'gm-pick-folder'; buttons.append(files, folder);
        const sources = wbElement('div', 'gm-source-summary'); sources.id = 'gm-sources';
        sourcePane.append(buttons, sources);
        const targetPane = wbElement('section', 'gm-target-pane'); targetPane.append(wbElement('h3', '', workbenchText('导入目标', 'Destination')));
        const label = wbElement('label', 'gm-field', workbenchText('主机', 'System'));
        const select = wbElement('select', ''); select.id = 'gm-system';
        select.append(...setup.systems.map(system => new Option(getSystemAbbreviation(system.name) + ' · ' + wbSystemName(system.name), system.name)));
        const selected = document.getElementById('system_name').value;
        if (setup.systems.some(system => system.name === selected)) select.value = selected;
        select.onchange = gmChangeSystem; label.append(select); targetPane.append(label);
        const destination = gmInput(targetPane, 'destination', '复制到目录', 'Copy to folder');
        const browse = gmButton('选择目标目录', 'Choose destination', gmBrowseDestination); browse.id = 'gm-pick-destination'; destination.parentElement.append(browse);
        const android = gmInput(targetPane, 'android', '掌机实际启动目录', 'Android launch folder'); android.parentElement.hidden = !setup.android;
        const advanced = wbElement('details', 'gm-advanced'); advanced.append(wbElement('summary', '', workbenchText('高级设置', 'Advanced settings')));
        gmInput(advanced, 'playlist', '目标列表文件名', 'Playlist filename'); targetPane.append(advanced);
        const browser = wbElement('div', 'gm-directory-browser'); browser.id = 'gm-browser'; browser.hidden = true; targetPane.append(browser);
        targetPane.append(wbElement('p', 'gm-policy', workbenchText('保留原文件名。相同文件复用，冲突文件不覆盖；BIOS 作为依赖复制，不加入游戏列表。', 'Keep original filenames. Reuse identical files and never overwrite conflicts. BIOS files are copied as dependencies, not game entries.')));
        form.append(sourcePane, targetPane);
        form.disabled = false; gmField('preview').disabled = false; gmChangeSystem();
    } catch (error) { if (generation === gameManagement.generation) gmField('status').textContent = gmError(error); }
}
function gmChangeSystem() {
    const system = gmField('system').value;
    const profile = gameManagement.setup.profiles.find(profile => profile.system === system);
    const playlist = currentDeviceScan?.playlists?.find(playlist => playlist.valid && playlist.system === system);
    gmField('destination').value = profile?.directory || gameManagement.root.replace(/\/$/, '') + '/roms/' + getSystemAbbreviation(system);
    gmField('android').value = profile?.android_directory || '';
    gmField('playlist').value = playlist?.path?.replaceAll('\\', '/').split('/').pop() || system + '.lpl';
    gmInvalidate();
}
async function gmPickSource(kind) {
    const generation = gameManagement.generation;
    try {
        const result = await desktopRequest('/api/desktop/pick', {kind});
        if (generation !== gameManagement.generation) return;
        const paths = result.paths || (result.path ? [result.path] : []);
        if (!paths.length) return;
        gameManagement.sources = paths;
        gmField('sources').replaceChildren(...paths.map(path => {const row = wbElement('div', 'gm-source-file'); row.append(wbIcon(kind === 'directory' ? 'layout-grid' : 'device-gamepad'), wbElement('strong', '', path.replaceAll('\\', '/').split('/').pop()), wbElement('small', 'gm-path', path)); return row;})); gmInvalidate();
    } catch (error) { gmField('status').textContent = gmError(error); }
}
async function gmBrowseDestination() {
    if (gameManagement.setup.android) {
        await gmBrowseRemote(gameManagement.root.split('/').slice(0, 4).join('/') + '/'); return;
    }
    try {const result = await desktopRequest('/api/desktop/pick', {kind:'directory', initial:gmField('destination').value});
        if (result.path) {gmField('destination').value = result.path; gmInvalidate();}
    } catch (error) {gmField('status').textContent = gmError(error);}
}
async function gmBrowseRemote(path) {
    const browser = gmField('browser'); browser.hidden = false;
    try {
        const data = await desktopRequest('/api/content/directories?path=' + encodeURIComponent(path));
        browser.replaceChildren(wbElement('p', '', data.path));
        const sources = libraryHome.device?.storages || libraryHome.data?.sources || [];
        for (const storage of sources.filter(source => source.transport === 'mtp' && source.path.split('/')[2] === gameManagement.root.split('/')[2])) {
            browser.append(gmButton(storage.label || '存储', storage.label || 'Storage', () => gmBrowseRemote(storage.path.split('/').slice(0, 4).join('/') + '/')));
        }
        browser.append(gmButton('上级目录', 'Parent folder', () => gmBrowseRemote(data.parent)), gmButton('使用此目录', 'Use this folder', () => {
            gmField('destination').value = data.path; browser.hidden = true; gmInvalidate();
        }, false));
        for (const directory of data.directories) {
            const button = gmButton(directory.name, directory.name, () => gmBrowseRemote(directory.path));
            button.classList.add('gm-directory'); browser.append(button);
        }
    } catch (error) { gmField('status').textContent = gmError(error); }
}
async function runGameJob(route, payload, onProgress) {
        const started = await desktopRequest(route, payload); gameManagement.job = started.job_id;
        const result = await new Promise((resolve, reject) => {
            const events = new EventSource('/api/progress?job_id=' + started.job_id);
            events.onmessage = event => {
                const job = JSON.parse(event.data);
                onProgress(job);
                if (job.status === 'completed') {events.close(); resolve(job.result);}
                else if (job.error || ['failed', 'cancelled'].includes(job.status)) {events.close(); reject(new Error(job.error || workbenchText('任务已取消', 'Task cancelled')));}
            };
            events.onerror = () => {onProgress({connectionError:true, message:workbenchText('进度连接中断，正在重连；任务不会重复提交。', 'Progress disconnected; reconnecting without resubmitting the task.')});};
        });
        return {id:started.job_id, result};
}
async function gmJob(route, payload) {
    if (!beginWorkbenchOperation('game-management')) throw new Error(workbenchText('请等待当前任务完成。', 'Wait for the current task to finish.'));
    gameManagement.busy = true; gmField('fields').disabled = true; gmField('preview').disabled = true; gmField('apply').disabled = true;
    gmField('results').querySelectorAll('button').forEach(button => {button.disabled = true;});
    gmField('dialog').querySelector('header button').disabled = true;
    try {
        gmField('cancel').hidden = false;
        return await runGameJob(route, payload, job => {gmField('status').textContent = job.connectionError ? job.message : currentUILanguage === 'en' ? (job.total ? `Processing… ${job.progress || 0} / ${job.total}` : 'Processing…') : job.message;});
    } finally {
        gameManagement.busy = false; gameManagement.job = null; gmField('cancel').hidden = true;
        gmField('results').querySelectorAll('button').forEach(button => {button.disabled = false;});
        gmField('fields').disabled = false; gmField('preview').disabled = false; gmField('apply').disabled = false;
        gmField('dialog').querySelector('header button').disabled = false; endWorkbenchOperation();
    }
}
async function previewGameImport() {
    gmInvalidate();
    try {
        const {id, result} = await gmJob('/api/games/preview', {mode:'import', root:gameManagement.root, sources:gameManagement.sources,
            destination:gmField('destination').value.trim(), system:gmField('system').value, android_directory:gmField('android').value.trim(), playlist_name:gmField('playlist').value.trim()});
        gameManagement.preview = id;
        const results = gmField('results');
        results.replaceChildren(wbElement('h3', '', workbenchText('内容预览', 'Preview')));
        results.append(wbElement('strong', '', workbenchText(`新增 ${result.added.length} 个条目 · 复用 ${result.duplicates} 个文件 · BIOS ${result.resources} 个`, `${result.added.length} new entries · ${result.duplicates} existing files · ${result.resources} BIOS files`)),
            wbElement('p', '', workbenchText(`需复制 ${gameSize(result.required_bytes)} · 目标可用 ${gameSize(result.free_bytes)}`, `Copy ${gameSize(result.required_bytes)} · Destination free ${gameSize(result.free_bytes)}`)), wbElement('p', 'gm-path', result.playlist));
        for (const file of result.files) {
            const row = wbElement('div', 'gm-result-row');
            row.dataset.state = file.state; row.append(wbIcon('device-gamepad'), wbElement('span', '', file.name), wbElement('small', '', gameSize(file.size) + ' · ' + ({new:workbenchText('复制', 'Copy'), existing:workbenchText('复用', 'Reuse'), conflict:workbenchText('冲突', 'Conflict')}[file.state]))); results.append(row);
        }
        const problem = result.conflicts.length ? workbenchText('同名文件内容不同，请更换目标目录或调整来源。', 'Same-name files contain different data. Choose another destination or change the source.')
            : result.required_bytes > result.free_bytes ? workbenchText('目标空间不足。', 'Not enough destination space.')
            : !result.can_apply ? workbenchText('没有需要导入的新内容。', 'There is nothing new to import.') : workbenchText('预览完成。确认后复制并更新列表。', 'Preview ready. Confirm to copy files and update the playlist.');
        gmField('status').textContent = problem; gmField('apply').hidden = !result.can_apply;
    } catch (error) {gmField('status').textContent = gmError(error);}
}
async function openGameRemoval(indices) {
    if (workbench.operation || !gameLibrary.data?.expected) return;
    ++gameManagement.generation; gameManagement.mode = 'remove'; gameManagement.preview = null;
    const payload = {mode:'remove', playlist:gameLibraryInput()[0], expected:gameLibrary.data.expected, indices};
    const form = gmWorkspace('remove');
    form.append(wbElement('p', '', workbenchText('仅移出以下列表条目。ROM、封面和存档全部保留，可重新扫描加入。合并显示的光盘配套条目会一并移出。', 'Remove only the entries listed below. ROMs, artwork and saves are kept; scan again to re-add them. Companion disc entries grouped under the selected row are removed together.')));
    try {
        const {id, result} = await gmJob('/api/games/preview', payload); gameManagement.preview = id;
        for (const item of result.removed) gmField('results').append(wbElement('strong', 'gm-result-name', item.label || item.path), wbElement('small', 'gm-path', item.path));
        gmField('status').textContent = workbenchText(`将移出 ${result.count} 个列表条目。修改前会保存列表备份。`, `${result.count} playlist entries will be removed. A playlist backup is saved first.`);
        gmField('apply').hidden = false;
    } catch (error) {gmField('status').textContent = gmError(error);}
}
async function applyGameManagement() {
    const preview = gameManagement.preview;
    const previousPlaylist = gameLibraryInput()[0];
    gameManagement.preview = null; gmField('apply').hidden = true;
    try {
        const {result} = await gmJob('/api/games/apply', {preview_job_id:preview});
        if (result.status !== 'applied') throw new Error(result.error || result.status);
        gmField('status').textContent = workbenchText(`完成：新增 ${result.added} 个条目，移出 ${result.removed} 个条目。备份可在设置的恢复记录中查看。`, `Done: ${result.added} entries added, ${result.removed} removed. The backup is available in Settings → recovery history.`);
        gmField('results').replaceChildren(wbElement('p', 'gm-path', result.backup_directory));
        gmField('preview').hidden = true;
        resetGameLibrary(); await scanDevice();
        const selected = currentDeviceScan?.playlists.findIndex(playlist => playlist.path === previousPlaylist);
        if (selected >= 0) await selectScannedPlaylist(selected);
        refreshWorkbenchOverview();
        const done = gmButton('完成', 'Done', closeGameManagement, false); gmField('dialog').querySelector('footer').append(done);
    } catch (error) {
        gmField('status').textContent = gmError(error) + workbenchText('；已复制文件会保留。请重新预览核对后继续，或在设置中查看列表恢复记录。', '; copied files are kept. Preview again to continue, or check playlist recovery history in Settings.');
    }
}
function appendGameSelection(cell, item) {
    const label = wbElement('label', 'game-select-label');
    const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.dataset.gameSelect = item.index; checkbox.checked = gameLibrary.selection.has(item.index);
    checkbox.setAttribute('aria-label', workbenchText('选择 ', 'Select ') + (item.label || item.rom_name));
    checkbox.disabled = Boolean(workbench.operation);
    checkbox.onchange = () => toggleGameSelection(item.index, checkbox.checked);
    const name = wbElement('button', 'game-name-button', cell.textContent); name.type = 'button'; name.onclick = () => inspectGame(item.index); cell.replaceChildren(); label.append(checkbox, name); cell.append(label);
}
function appendGameManagementActions(actions, item) {
    const menu = wbElement('details', 'game-row-menu');
    const summary = wbElement('summary', '', '⋯'); summary.setAttribute('aria-label', workbenchText('管理 ', 'Manage ') + (item.label || item.rom_name));
    const remove = gmButton('移出列表…', 'Remove from playlist…', () => {menu.open = false; openGameRemoval([item.index]);});
    remove.disabled = Boolean(workbench.operation); menu.append(summary, remove); actions.append(menu);
}
function renderGameSelection(visible) {
    const toolbar = document.getElementById('game-selection-toolbar'); toolbar.classList.remove('has-selection'); toolbar.replaceChildren(); toolbar.hidden = !gameLibrary.data?.items.length;
    if (toolbar.hidden) return;
    const all = wbElement('label', 'game-select-label');
    const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.checked = Boolean(visible.length) && visible.every(item => gameLibrary.selection.has(item.index));
    checkbox.indeterminate = !checkbox.checked && visible.some(item => gameLibrary.selection.has(item.index)); checkbox.disabled = Boolean(workbench.operation);
    checkbox.onchange = () => {for (const item of visible) {if (checkbox.checked) gameLibrary.selection.add(item.index); else gameLibrary.selection.delete(item.index);} renderGameLibrary();};
    all.append(checkbox, wbElement('span', '', workbenchText('选择当前页', 'Select visible'))); toolbar.append(all);
    if (!gameLibrary.selection.size) return;
    toolbar.classList.add('has-selection');
    toolbar.append(wbElement('span', '', workbenchText(`已选 ${gameLibrary.selection.size} 项`, `${gameLibrary.selection.size} selected`)));
    const complete = gmButton('补全资料', 'Complete metadata', () => previewTask({entries:gameLibrary.data.items.filter(item => gameLibrary.selection.has(item.index)).map(item => [item.index, item.rom_path])})); complete.id = 'game-selection-complete'; complete.disabled = Boolean(workbench.operation); toolbar.append(complete);
    const remove = gmButton('移出列表…', 'Remove from playlist…', () => openGameRemoval([...gameLibrary.selection])); remove.id = 'game-selection-remove'; remove.disabled = Boolean(workbench.operation); toolbar.append(remove);
    toolbar.append(gmButton('取消选择', 'Clear selection', () => {gameLibrary.selection.clear(); renderGameLibrary();}));
}

document.addEventListener('click', event => {
    if (gameManagement.open && !gameManagement.busy && event.target.closest('#scanned-playlists button, #library-all-systems')) closeGameManagement();
});
