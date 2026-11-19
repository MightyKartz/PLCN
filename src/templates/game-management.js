/* File copies and playlist edits have separate previews. No ROM-delete action. */
const gameManagement = {mode:'import', root:'', sources:[], sourceKind:'files', setup:null, preview:null, analysisFiles:null, analysisToken:0, reanalyze:false, job:null, busy:false, generation:0};
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
function gmStatus(text, problem = false) {
    const retry = gmField('retry'), reconnect = gmField('reconnect'); if (retry) retry.hidden = !problem; if (reconnect) reconnect.hidden = !problem;
    const status = gmField('status'); status.textContent = text; status.classList.toggle('gm-status-problem', problem);
}
function gmInvalidate() {
    gameManagement.preview = null; gameManagement.analysisFiles = null; gameManagement.analysisToken++;
    const configure = gmField('mapping-config'); if (configure) configure.hidden = true;
    const check = gmField('mapping-confirm'); if (check) check.checked = false;
    const mapping = gmField('mapping-status'); if (mapping) mapping.textContent = workbenchText('路径待分析', 'Path analysis pending');
    gmField('update-existing')?.remove();
    const apply = gmField('apply'); if (apply) {apply.hidden = gameManagement.mode !== 'import'; apply.disabled = true;}
}
let gmAnalyzeTimer = 0;
function gmScheduleAnalyze() {
    if (gameManagement.mode !== 'import' || !gameManagement.sources.length) return;
    gmInvalidate(); gmStatus(workbenchText('正在分析…', 'Analyzing…'));
    clearTimeout(gmAnalyzeTimer); gmAnalyzeTimer = setTimeout(gmAutoAnalyze, 400);
}
function gmAutoAnalyze() {
    if (gameManagement.mode !== 'import' || !gameManagement.sources.length) return;
    if (gameManagement.busy || !gameManagement.setup) return;
    previewGameImport();
}
function gmRenderFiles() {
    const pane = gmField('files'); if (!pane) return;
    pane.replaceChildren();
    const sources = gameManagement.sources;
    gmField('retry').disabled = gameManagement.busy || !sources.length;
    if (!sources.length) {
        gmField('apply').textContent = workbenchText('导入游戏', 'Import games');
        gmStatus(workbenchText('请选择要导入的游戏。', 'Choose games to import.'));
        pane.append(wbElement('h3', '', workbenchText('1 · 选择游戏', '1 · Choose games')));
        const buttons = wbElement('div', 'gm-source-buttons');
        const files = gmButton('选择文件', 'Choose files', () => gmPickSource('files')); files.id = 'gm-pick-files';
        const folder = gmButton('选择目录', 'Choose folder', () => gmPickSource('directory')); folder.id = 'gm-pick-folder';
        buttons.append(files, folder); pane.append(buttons); return;
    }
    const head = wbElement('div', 'gm-section-head');
    const n = sources.length;
    head.append(wbElement('h3', '', gameManagement.sourceKind === 'directory'
        ? workbenchText(`1 · 已选 ${n} 个目录`, `1 · ${n} ${n === 1 ? 'folder' : 'folders'} selected`)
        : workbenchText(`1 · 已选 ${n} 个文件`, `1 · ${n} ${n === 1 ? 'file' : 'files'} selected`)));
    const actions = wbElement('div', 'gm-head-actions');
    const repick = wbElement('button', 'btn btn-text', workbenchText('重新选择', 'Choose again')); repick.type = 'button'; repick.id = 'gm-pick-files'; repick.onclick = () => gmPickSource('files');
    const refolder = wbElement('button', 'btn btn-text', workbenchText('选择目录', 'Choose folder')); refolder.type = 'button'; refolder.id = 'gm-pick-folder'; refolder.onclick = () => gmPickSource('directory');
    actions.append(repick, refolder, gmButton('清空', 'Clear', () => {gameManagement.sources=[]; gmInvalidate(); gmRenderFiles(); gmStatus(workbenchText('请选择要导入的游戏。', 'Choose games to import.'));})); head.append(actions); pane.append(head);
    const list = wbElement('div', 'gm-file-list'); list.id = 'gm-sources';
    const rows = gameManagement.analysisFiles
        ? gameManagement.analysisFiles.map(file => ({name:file.name, size:gameSize(file.size), state:file.state}))
        : sources.map(path => ({name:path.replaceAll('\\', '/').split('/').pop(), path, dir:gameManagement.sourceKind === 'directory'}));
    for (const file of rows.slice(0, 6)) {
        const row = wbElement('div', 'gm-file-row'); if (file.path) row.title = file.path;
        row.append(wbIcon(file.dir ? 'layout-grid' : 'device-gamepad'), wbElement('span', 'gm-file-name', file.name));
        if (file.state === 'existing') row.append(wbElement('span', 'gm-file-tag', workbenchText('已存在', 'Already there')));
        else if (file.state === 'conflict') row.append(wbElement('span', 'gm-file-tag gm-file-conflict', workbenchText('冲突', 'Conflict')));
        if (file.size) row.append(wbElement('span', 'gm-file-size', file.size));
        const source = sources.find(path => path === file.path || path.split('/').pop() === file.name);
        if (source) {const remove = gmButton('移除', 'Remove', () => {gameManagement.sources = sources.filter(path => path !== source); gmInvalidate(); gmRenderFiles(); gmAutoAnalyze();}); remove.className = 'btn btn-text'; remove.setAttribute('aria-label',workbenchText('移除来源：','Remove source: ')+file.name); row.append(remove);}
        list.append(row);
    }
    pane.append(list);
    if (rows.length > 6) {const more = wbElement('details','gm-more-files'); more.append(wbElement('summary','',workbenchText(`共 ${rows.length} 个文件，查看完整列表`, `${rows.length} files · View all`))); for (const file of rows.slice(6)) more.append(wbElement('p','',file.name)); pane.append(more);}

}
function gmRenderDestinationSummary() {
    const summary = gmField('destination-summary'); if (!summary || !gameManagement.setup) return;
    const root = gameManagement.root.replaceAll('\\', '/').replace(/\/+$/, '');
    let destination = gmField('destination').value.trim().replaceAll('\\', '/');
    if (destination.startsWith(root)) destination = destination.slice(root.length) || '/';
    if (!destination) {summary.textContent = workbenchText('请选择游戏复制到的目录', 'Choose where to copy the games'); return;}
    if (destination.startsWith('mtp://')) {
        const storageRoot = destination.split('/').slice(0,4).join('/');
        const storages = libraryHome.device?.storages || libraryHome.data?.sources || [];
        const storage = storages.find(item => item.path?.split('/').slice(0,4).join('/') === storageRoot);
        const folder = decodeURIComponent(destination.split('/').slice(4).join('/'));
        destination = (storage?.label || workbenchText('掌机存储', 'Handheld storage')) + ' → ' + folder;
    }
    summary.textContent = getSystemAbbreviation(gmField('system').value) + ' · ' + destination;
}
function gmWorkspace(mode) {
    const workspace = document.getElementById('game-management-workspace'); workspace.replaceChildren(); workspace.hidden = false;
    workspace.parentElement.classList.add('managing-games'); gameManagement.open = true;
    const section = wbElement('section', 'game-management-workspace gm-mode-' + mode); section.id = 'gm-dialog';
    section.setAttribute('aria-labelledby', 'gm-title');
    const header = wbElement('header', 'gm-workspace-header');
    const title = wbElement('h2', '', mode === 'import' ? workbenchText('添加游戏', 'Add games') : workbenchText('移出列表', 'Remove from playlist'));
    title.id = 'gm-title';
    if (mode === 'import') { const cancel = wbElement('button', 'btn btn-muted'); wbIconButton(cancel, 'x', workbenchText('取消', 'Cancel')); cancel.type = 'button'; cancel.onclick = closeGameManagement; header.append(title, cancel); }
    else header.append(title, gmButton('返回游戏库', 'Back to library', closeGameManagement));
    const body = wbElement('div', 'gm-workspace-body');
    const form = wbElement('fieldset', 'gm-fields'); form.id = 'gm-fields';
    const results = wbElement('div', 'gm-results'); results.id = 'gm-results'; results.setAttribute('aria-live', 'polite'); results.hidden = mode === 'import';
    body.append(form, results);
    const status = wbElement('p', 'gm-workspace-status'); status.id = 'gm-status'; status.setAttribute('role', 'status');
    const footer = wbElement('footer', 'gm-workspace-footer');
    const cancel = gmButton('取消任务', 'Cancel task', async () => {
        if (gameManagement.job) await desktopRequest('/api/jobs/cancel', {job_id:gameManagement.job});
    }); cancel.id = 'gm-cancel'; cancel.hidden = true;
    const apply = gmButton(mode === 'import' ? '确认导入' : '确认移出列表', mode === 'import' ? 'Import games' : 'Remove entries', applyGameManagement, false);
    apply.id = 'gm-apply'; apply.hidden = mode !== 'import'; apply.disabled = true;
    const retry = gmButton('重新分析', 'Analyze again', gmAutoAnalyze); retry.id = 'gm-retry'; retry.disabled = true; retry.hidden = true;
    const reconnect = gmButton('重新连接', 'Reconnect', reconnectGameImport); reconnect.id = 'gm-reconnect'; reconnect.hidden = true;
    footer.append(status, retry, reconnect, cancel, apply); section.append(header, body, footer); workspace.append(section);
    title.tabIndex = -1; title.focus(); return form;
}
function closeGameManagement({returnToLibrary = false} = {}) {
    if (gameManagement.busy) return;
    ++gameManagement.generation; gameManagement.open = false;
    const workspace = document.getElementById('game-management-workspace'); workspace.hidden = true;
    workspace.parentElement.classList.remove('managing-games');
    if (returnToLibrary) closeGameFiles();
    else if (typeof gameFilesView !== 'undefined') gameFilesView?.refresh();
    (document.getElementById('game-files-workspace')?.hidden === false
        ? document.getElementById('game-files-import') : document.getElementById('game-files-button'))?.focus();
}
function gmInput(form, id, zh, en, value = '') {
    const label = wbElement('label', 'gm-field', workbenchText(zh, en));
    const input = wbElement('input', ''); input.id = 'gm-' + id; input.type = 'text'; input.value = value;
    input.oninput = () => {input.removeAttribute('aria-invalid'); gmInvalidate(); if (id === 'destination') {gmField('android').value = ''; gmRenderDestinationSummary();} gmScheduleAnalyze();}; label.append(input); form.append(label); return input;
}
async function openGameImport(destination = '') {
    if (workbench.operation) return;
    const root = document.getElementById('retroarch_root').value;
    if (!root || root.startsWith('adb://')) { showStatus(workbenchText('请先打开 RetroArch 游戏库。', 'Open a RetroArch library first.'), 'error'); return; }
    const generation = ++gameManagement.generation;
    Object.assign(gameManagement, {mode:'import', root, sources:[], setup:null, preview:null, destinationHint:typeof destination === 'string' ? destination : ''});
    const form = gmWorkspace('import');
    form.disabled = true;
    gmField('status').textContent = workbenchText('正在读取目标游戏库…', 'Loading the destination library…');
    try {
        const setup = await desktopRequest('/api/content/setup?root=' + encodeURIComponent(root));
        if (generation !== gameManagement.generation) return;
        gameManagement.setup = setup;
        const sourcePane = wbElement('section', 'gm-source-pane'); sourcePane.id = 'gm-files'; form.append(sourcePane); gmRenderFiles();
        const targetPane = wbElement('section', 'gm-target-pane');
        const destHead = wbElement('div', 'gm-section-head'); destHead.append(wbElement('h3', '', workbenchText('2 · 确认位置', '2 · Confirm location')));
        const fields = wbElement('div', 'gm-destination-fields'); fields.id = 'gm-destination-fields'; fields.hidden = true;
        const change = wbElement('button', 'btn btn-text', workbenchText('更改', 'Change')); change.type = 'button'; change.id = 'gm-change-destination';
        change.setAttribute('aria-expanded', 'false'); change.setAttribute('aria-controls', 'gm-destination-fields');
        change.onclick = () => {fields.hidden = !fields.hidden; change.setAttribute('aria-expanded', String(!fields.hidden));};
        destHead.append(change); targetPane.append(destHead);
        const summary = wbElement('p', 'gm-destination-summary'); summary.id = 'gm-destination-summary'; targetPane.append(summary);
        const mapping = wbElement('p','gm-mapping-status'); mapping.id = 'gm-mapping-status'; mapping.setAttribute('role','status'); targetPane.append(mapping);
        const label = wbElement('label', 'gm-field', workbenchText('主机', 'System'));
        const select = wbElement('select', ''); select.id = 'gm-system';
        select.append(...setup.systems.map(system => new Option(getSystemAbbreviation(system.name) + ' · ' + wbSystemName(system.name), system.name)));
        const selected = document.getElementById('system_name').value;
        if (setup.systems.some(system => system.name === selected)) select.value = selected;
        select.onchange = gmChangeSystem; label.append(select); targetPane.append(label);
        const destination = gmInput(fields, 'destination', '复制到目录', 'Copy to folder');
        if (setup.android) destination.type = 'hidden';
        const browse = gmButton('选择目标目录', 'Choose destination', gmBrowseDestination); browse.id = 'gm-pick-destination'; destination.parentElement.append(browse);
        const android = gmInput(fields, 'android', '掌机实际启动目录', 'Android launch folder'); android.parentElement.hidden = !setup.android;
        const configure = wbElement('section','gm-mapping-config'); configure.id = 'gm-mapping-config'; configure.hidden = true;
        configure.append(wbElement('h4','',workbenchText('配置启动位置', 'Configure launch location')), wbElement('p','',workbenchText('在掌机 RetroArch 中核对存储与完整目录，再保存手动配置。文件和名称选择会保留。', 'Check the storage and full folder in RetroArch on your handheld, then save the manual configuration. Your selection is kept.')));
        const confirmation = wbElement('label','gm-confirm-mapping'); const checked = document.createElement('input'); checked.type = 'checkbox'; checked.id = 'gm-mapping-confirm';
        confirmation.append(checked, document.createTextNode(workbenchText('我已在掌机核对以上位置（手动配置，未验证启动）', 'I checked this location on the handheld (manual configuration; startup unverified)')));
        configure.append(confirmation, gmButton('保存启动位置并分析', 'Save location and analyze', saveGameImportMapping)); fields.append(configure);
        const advanced = wbElement('details', 'gm-advanced'); advanced.append(wbElement('summary', '', workbenchText('高级设置', 'Advanced settings')));
        gmInput(advanced, 'playlist', '目标列表文件名', 'Playlist filename'); fields.append(advanced);
        const browser = wbElement('div', 'gm-directory-browser'); browser.id = 'gm-browser'; browser.hidden = true; fields.append(browser);
        fields.append(wbElement('p', 'gm-policy', workbenchText('保留原文件名。相同文件复用，冲突文件不覆盖；BIOS 作为依赖复制，不加入游戏列表。', 'Keep original filenames. Reuse identical files and never overwrite conflicts. BIOS files are copied as dependencies, not game entries.')));
        const playlistPath = wbElement('p', 'gm-path'); playlistPath.id = 'gm-playlist-path'; advanced.append(playlistPath);
        targetPane.append(fields); form.append(targetPane);
        form.disabled = false; gmField('status').textContent = workbenchText('选择文件或目录后开始分析。', 'Choose files or a folder to start the analysis.'); gmChangeSystem();
    } catch (error) { if (generation === gameManagement.generation) gmField('status').textContent = gmError(error); }
}
function gmChangeSystem() {
    const system = gmField('system').value;
    const destination = gameManagement.destinationHint;
    const profile = [...gameManagement.setup.profiles].reverse().find(profile => profile.system === system && (!destination || profile.directory === destination));
    const playlist = currentDeviceScan?.playlists?.find(playlist => playlist.valid && playlist.system === system);
    gmField('destination').value = destination || profile?.directory || (gameManagement.setup.android ? '' : gameManagement.root.replace(/\/$/, '') + '/roms/' + getSystemAbbreviation(system));
    gmField('android').value = profile?.android_directory || '';
    const filename = playlist?.path?.replaceAll('\\', '/').split('/').pop();
    gmField('playlist').value = playlist?.path?.startsWith('mtp://') ? decodeURIComponent(filename) : filename || system + '.lpl';
    if (profile?.playlist_name) gmField('playlist').value = profile.playlist_name;
    gmInvalidate(); gmRenderDestinationSummary(); gmAutoAnalyze();
}
async function gmPickSource(kind) {
    const generation = gameManagement.generation;
    try {
        const result = await desktopRequest('/api/desktop/pick', {kind});
        if (generation !== gameManagement.generation) return;
        const paths = result.paths || (result.path ? [result.path] : []);
        if (!paths.length) return;
        gameManagement.sources = paths; gameManagement.sourceKind = kind;
        gmInvalidate(); gmRenderFiles(); gmAutoAnalyze();
    } catch (error) { gmStatus(gmError(error), true); }
}
async function gmBrowseDestination() {
    if (gameManagement.setup.android) {
        await gmBrowseRemote(gameManagement.root.split('/').slice(0, 4).join('/') + '/'); return;
    }
    try {const result = await desktopRequest('/api/desktop/pick', {kind:'directory', initial:gmField('destination').value});
        if (result.path) {gmField('destination').value = result.path; gmInvalidate(); gmRenderDestinationSummary(); gmAutoAnalyze();}
    } catch (error) {gmStatus(gmError(error), true);}
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
            gmField('android').value = ''; gmField('destination').value = data.path; browser.hidden = true; gmInvalidate(); gmRenderDestinationSummary(); gmAutoAnalyze();
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
            events.onerror = async () => {
                onProgress({connectionError:true, message:workbenchText('进度连接中断，正在重连；任务不会重复提交。', 'Progress disconnected; reconnecting without resubmitting the task.')});
                try {
                    const state = await desktopRequest('/api/desktop');
                    if (!state.jobs.some(job => job.id === started.job_id)) {
                        events.close(); reject(new Error(workbenchText('服务已重启，原任务结果未知。请检查列表修改记录与目标文件，再重新分析。', 'The service restarted; the task result is unknown. Check playlist history and destination files, then analyze again.')));
                    }
                } catch (error) {onProgress({connectionError:true, message:error.message});}
            };
        });
        return {id:started.job_id, result};
}
async function gmJob(route, payload) {
    if (!beginWorkbenchOperation('game-management')) throw new Error(workbenchText('请等待当前任务完成。', 'Wait for the current task to finish.'));
    gameManagement.busy = true; gmField('retry').disabled = true; gmField('reconnect').disabled = true; gmField('fields').disabled = true; gmField('apply').disabled = true;
    gmField('results').querySelectorAll('button').forEach(button => {button.disabled = true;});
    gmField('dialog').querySelector('header button').disabled = true;
    try {
        gmField('cancel').hidden = false;
        return await runGameJob(route, payload, job => {gmField('status').textContent = job.connectionError ? job.message : currentUILanguage === 'en' ? (job.total ? `Processing… ${job.progress || 0} / ${job.total}` : 'Processing…') : job.message;});
    } finally {
        gameManagement.busy = false; gmField('retry').disabled = false; gmField('reconnect').disabled = false; gameManagement.job = null; gmField('cancel').hidden = true;
        gmField('results').querySelectorAll('button').forEach(button => {button.disabled = false;});
        gmField('fields').disabled = false; gmField('apply').disabled = !gameManagement.preview;
        gmField('dialog').querySelector('header button').disabled = false; endWorkbenchOperation();
        if (gameManagement.mode === 'import' && gameManagement.reanalyze) { gameManagement.reanalyze = false; previewGameImport(); }
    }
}
async function previewGameImport() {
    if (!gameManagement.sources.length) return;
    const generation = gameManagement.generation, token = ++gameManagement.analysisToken;
    gameManagement.preview = null; gameManagement.analysisFiles = null;
    gmField('apply').hidden = false; gmField('apply').disabled = true; gmStatus(workbenchText('正在分析…', 'Analyzing…'));
    try {
        if (gameManagement.setup.android && !gmField('destination').value.trim()) {
            gmField('destination-fields').hidden = false;
            document.getElementById('gm-change-destination').setAttribute('aria-expanded', 'true');
            gmStatus(workbenchText('请选择掌机上的目标目录，再确认实际启动路径。', 'Choose a destination folder on the handheld, then confirm its launch path.'), true);
            gmField('pick-destination').scrollIntoView({block:'center'}); gmField('pick-destination').focus();
            return;
        }
        if (gameManagement.setup.android && !gmField('android').value.trim()) {
            const destination = gmField('destination').value.trim();
            const hints = await desktopRequest('/api/content/hints', {root:gameManagement.root,
                system:gmField('system').value, directory:destination, playlist_name:gmField('playlist').value.trim()});
            if (generation !== gameManagement.generation || token !== gameManagement.analysisToken) return;
            if (!gmField('android').value.trim()) gmField('android').value = hints.android_directory || '';
            if (!gmField('android').value.trim()) {
                gmField('destination-fields').hidden = false;
                gmField('android').parentElement.hidden = false;
                document.getElementById('gm-change-destination').setAttribute('aria-expanded', 'true');
                gmStatus(workbenchText('请填写掌机实际启动目录后才能导入。可在 RetroArch 的“加载内容”中查看完整路径。', 'Enter the Android launch folder before importing. Find its full path under Load Content in RetroArch.'), true);
                gmField('android').setAttribute('aria-invalid', 'true');
                gmField('android').scrollIntoView({block:'center'}); gmField('android').focus({preventScroll:true});
                return;
            }
            gmField('android').removeAttribute('aria-invalid');
        }
        const {id, result} = await gmJob('/api/games/preview', {mode:'import', root:gameManagement.root, sources:gameManagement.sources,
            destination:gmField('destination').value.trim(), system:gmField('system').value, android_directory:gmField('android').value.trim(), playlist_name:gmField('playlist').value.trim()});
        if (generation !== gameManagement.generation || token !== gameManagement.analysisToken) return;
        gameManagement.preview = id; gameManagement.analysisFiles = result.mapping_state === 'unverified' ? null : result.files;
        const mapping = gmField('mapping-status');
        const configure = gmField('mapping-config');
        if (configure) {configure.hidden = result.mapping_state !== 'unverified'; if (!configure.hidden) {gmField('destination-fields').hidden = false; document.getElementById('gm-change-destination').setAttribute('aria-expanded','true');}}
        if (mapping) mapping.textContent = result.mapping_state === 'manual' ? workbenchText('已保存手动配置 · 游戏启动未验证', 'Manual configuration saved · Startup unverified') : result.mapping_state === 'unverified' ? workbenchText('待核对：请在下方配置启动位置后继续。', 'Needs review: configure the launch location below to continue.')
            : result.mapping_state === 'matched' ? workbenchText('与已保存映射一致；实际游戏启动仍需在掌机验证。', 'Matches saved mapping; game startup still requires handheld testing.') : workbenchText('本地文件路径；实际游戏启动尚未验证。', 'Local file paths; game startup is not verified.');
        gmRenderFiles();
        const playlistPath = gmField('playlist-path'); if (playlistPath) playlistPath.textContent = result.playlist;
        if (result.can_apply) {
            gmStatus(workbenchText(`复制 ${result.copy_count} 个文件 · 复用 ${result.duplicates} 个 · 跳过 ${result.skipped} 个 · 需要 ${gameSize(result.required_bytes)} · 可用 ${gameSize(result.free_bytes)}`, `Copy ${result.copy_count} files · Reuse ${result.duplicates} · Skip ${result.skipped} · Needs ${gameSize(result.required_bytes)} · ${gameSize(result.free_bytes)} free`));
            const apply = gmField('apply'); apply.hidden = false; apply.disabled = false;
            apply.textContent = workbenchText(result.added.length ? `导入 ${result.added.length} 个游戏` : `复制 ${result.copy_count} 个文件`, result.added.length ? `Import ${result.added.length} ${result.added.length === 1 ? 'game' : 'games'}` : `Copy ${result.copy_count} files`);
        } else {
            gmStatus(result.mapping_state === 'unverified' ? workbenchText('路径映射待核对，不能导入。', 'Storage mapping needs review; import is blocked.') : result.conflicts.length ? workbenchText('同名文件内容不同，请更换目标目录或调整来源。', 'Same-name files contain different data. Choose another destination or change the source.')
                : result.required_bytes > result.free_bytes ? workbenchText('目标空间不足。', 'Not enough destination space.')
                : result.skipped && !result.files.length ? workbenchText('未发现所选主机支持的游戏，请检查主机和文件格式。', 'No supported games found. Check the selected system and file formats.') : workbenchText('没有需要导入的新内容。', 'There is nothing new to import.'), true);
            gmField('apply').disabled = true;
            gmField('update-existing')?.remove();
            if (result.update_candidate) {
                gmStatus(workbenchText('该游戏已存在，新文件内容不同。可以直接更新 ROM。', 'This game exists and the new file differs. You can update its ROM.'));
                const update=gmButton('更新已有游戏 ROM', 'Update existing ROM',()=>updateImportedRom(result.update_candidate),false);update.id='gm-update-existing';
                gmField('dialog').querySelector('footer').append(update);
            }
        }
    } catch (error) {if (generation === gameManagement.generation && token === gameManagement.analysisToken) gmStatus(gmError(error), true);}
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
        gmField('apply').hidden = false; gmField('apply').disabled = false;
    } catch (error) {gmField('status').textContent = gmError(error);}
}
async function applyGameManagement() {
    const preview = gameManagement.preview;
    const previousPlaylist = gameLibraryInput()[0];
    if (!preview || gameManagement.busy) return;
    gameManagement.preview = null; gmField('apply').disabled = true;
    try {
        const {result} = await gmJob('/api/games/apply', {preview_job_id:preview});
        if (result.status !== 'applied') throw new Error(result.error || result.status);
        const results = gmField('results');
        if (gameManagement.mode === 'import') {
            gmStatus(workbenchText(`新增 ${result.added} 个条目 · 复制 ${result.copied} 个文件 · 复用 ${result.reused} 个 · 跳过 ${result.skipped} 个 · 失败 ${result.failed} 个`, `Added ${result.added} entries · Copied ${result.copied} files · Reused ${result.reused} · Skipped ${result.skipped} · Failed ${result.failed}`));
            const backup = wbElement('details', 'gm-backup'); backup.append(wbElement('summary', '', workbenchText('备份位置', 'Backup location')), wbElement('p', 'gm-path', result.backup_directory));
            results.replaceChildren(wbElement('h3','',workbenchText('3 · 导入结果', '3 · Import result')), wbElement('p','',gmField('destination-summary').textContent), wbElement('p','',workbenchText('文件复制与列表更新已完成；请在掌机验证启动。', 'Files copied and playlist updated; test startup on the handheld.')), backup); results.hidden = false;
            gmField('fields').hidden = true; gmField('apply').hidden = true;

        } else {
            gmStatus(workbenchText(`完成：新增 ${result.added} 个条目，移出 ${result.removed} 个条目。备份可在列表修改记录中查看。`, `Done: ${result.added} entries added, ${result.removed} removed. The backup is available in Playlist history.`));
            results.replaceChildren(wbElement('p', 'gm-path', result.backup_directory));
        }
        const playlistPath = gameManagement.mode === 'import' ? result.playlist_path : previousPlaylist;
        resetGameLibrary();
        await refreshLibraryPlaylists([playlistPath]);
        const selected = currentDeviceScan?.playlists.findIndex(playlist => playlist.path === playlistPath);
        if (selected >= 0) await selectScannedPlaylist(selected);
        const footer = gmField('dialog').querySelector('footer');
        if (gameManagement.mode === 'import') {
            const more = gmButton('继续添加', 'Add more', () => openGameImport(gameManagement.destinationHint)); more.id = 'gm-add-more';
            const complete = gmButton('补全名称与封面', 'Complete names and artwork', () => {closeGameManagement({returnToLibrary:true}); startCompletion();}); complete.id = 'gm-complete-metadata';
            footer.append(more, complete);
        }
        const done = gmButton('查看游戏', 'View games', () => closeGameManagement({returnToLibrary:true}), false); done.id = 'gm-view-games'; footer.append(done);
    } catch (error) {
        gmStatus(gmError(error) + workbenchText('；已复制文件会保留。请点击“重新分析”核对后继续；无法取得结果时先查看任务，避免重复写入。', '; copied files are kept. Use Analyze again to continue; if the result is unknown, check Tasks before writing again.'), true);
    }
}
function renderGameSelection(visible) {
    const toolbar = document.getElementById('game-selection-toolbar'); toolbar.classList.remove('has-selection', 'has-status'); toolbar.replaceChildren();
    const headAll = document.getElementById('game-library-select-all');
    const allChecked = Boolean(visible.length) && visible.every(item => gameLibrary.selection.has(item.index));
    headAll.checked = allChecked;
    headAll.indeterminate = !allChecked && visible.some(item => gameLibrary.selection.has(item.index));
    headAll.disabled = Boolean(workbench.operation) || !visible.length;
    const selectVisible = workbenchText('选择当前显示的游戏', 'Select visible games');
    headAll.title = selectVisible; headAll.setAttribute('aria-label', selectVisible);
    headAll.onchange = () => {for (const item of visible) {if (headAll.checked) gameLibrary.selection.add(item.index); else gameLibrary.selection.delete(item.index);} renderGameLibrary();};
    const hasSelection = Boolean(gameLibrary.selection.size) && Boolean(gameLibrary.data?.items.length);
    const items = (gameLibrary.data?.items || []).filter(item => typeof workbenchOverview === 'undefined'
        || workbenchOverview.scope === 'all' || wbStorageKind(item.rom_path) === workbenchOverview.scope);
    const missingCount = hasSelection ? 0 : items.filter(item => gameMatchesImageFilter(item, 'missing')).length;
    toolbar.hidden = !hasSelection && !missingCount;
    if (toolbar.hidden) return;
    if (!hasSelection) {
        toolbar.classList.add('has-status');
        const complete = gmButton('补全当前列表', 'Complete this list', () => startCompletion());
        complete.id = 'games-complete-button'; complete.disabled = document.getElementById('preview-button').disabled;
        toolbar.append(wbIcon('photo'),
            wbElement('span', 'overview-status-text', workbenchText(`${missingCount} 款游戏的图片待补全`, `${missingCount} ${missingCount === 1 ? 'game' : 'games'} missing artwork`)),
            complete);
        return;
    }
    toolbar.classList.add('has-selection');
    const all = wbElement('label', 'game-select-label');
    const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.checked = allChecked;
    checkbox.indeterminate = headAll.indeterminate; checkbox.disabled = Boolean(workbench.operation);
    checkbox.title = selectVisible; checkbox.setAttribute('aria-label', selectVisible);
    checkbox.onchange = () => {for (const item of visible) {if (checkbox.checked) gameLibrary.selection.add(item.index); else gameLibrary.selection.delete(item.index);} renderGameLibrary();};
    all.append(checkbox, wbElement('span', '', workbenchText('全选', 'Select all'))); toolbar.append(all);
    const count = gameLibrary.selection.size;
    toolbar.append(wbElement('span', '', workbenchText(`已选 ${count} 项`, `${count} selected`)));
    const complete = gmButton(`补全所选 ${count} 项`, `Complete ${count} selected`, () => runDirectCompletion({entries:gameLibrary.data.items.filter(item => gameLibrary.selection.has(item.index)).map(item => [item.index, item.rom_path])}), false); complete.id = 'game-selection-complete'; complete.disabled = Boolean(workbench.operation); toolbar.append(complete);
    toolbar.append(wbElement('span', 'selection-spacer'));
    const menu = wbElement('details', 'action-menu'); menu.id = 'game-selection-actions';
    const summary = wbElement('summary', 'btn btn-muted action-menu-trigger', workbenchText('更多操作', 'More actions'));
    summary.append(wbIcon('chevron-down'));
    const drop = wbElement('div', 'action-menu-list');
    const remove = wbElement('button', 'action-menu-item', workbenchText('移出列表…', 'Remove from playlist…'));
    remove.type = 'button'; remove.id = 'game-selection-remove'; remove.disabled = Boolean(workbench.operation);
    remove.onclick = () => {menu.open = false; openGameRemoval([...gameLibrary.selection]);};
    drop.append(remove); menu.append(summary, drop); toolbar.append(menu);
    const clear = wbElement('button', 'btn btn-muted dialog-icon-button');
    wbIconButton(clear, 'x', workbenchText('取消选择', 'Clear selection'));
    clear.id = 'game-selection-clear'; clear.type = 'button';
    clear.onclick = () => {gameLibrary.selection.clear(); renderGameLibrary();};
    toolbar.append(clear);
}

document.addEventListener('click', event => {
    if (gameManagement.open && !gameManagement.busy && event.target.closest('#scanned-playlists button, #library-all-systems')) closeGameManagement();
    document.querySelectorAll('.action-menu[open]').forEach(menu => {if (!menu.contains(event.target)) menu.open = false;});
});
document.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || !gameLibrary.selection.size || workbench.operation) return;
    if (document.querySelector('dialog[open]') || event.target.closest?.('input, textarea, select')) return;
    gameLibrary.selection.clear();
    renderGameLibrary();
});

async function saveGameImportMapping() {
    if (!gmField('mapping-confirm').checked) {gmStatus(workbenchText('请先在掌机核对并勾选确认。', 'Check the location on your handheld and tick the confirmation first.'), true); return;}
    try {
        const {result} = await gmJob('/api/games/mapping', {mode:'import', confirmed:true, root:gameManagement.root, sources:gameManagement.sources,
            destination:gmField('destination').value.trim(), system:gmField('system').value,
            android_directory:gmField('android').value.trim(), playlist_name:gmField('playlist').value.trim()});
        gameManagement.setup.profiles = result.profiles;
        gmInvalidate(); await previewGameImport();
    } catch (error) {gmStatus(gmError(error), true);}
}
