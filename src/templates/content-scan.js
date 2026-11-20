/* Directory imports are reviewed independently from name/artwork repair. */
const contentScan = {setup: null, previewId: null, busy: false, browserPath: '', browserParent: '', imported: null, downloaded: null, revision: 0, openGeneration: 0, coreStatus: null, browsing: false};
const contentField = name => document.getElementById('content-scan-' + name);

async function openContentScan(targetRoot = '') {
    if (workbench.operation) return;
    const root = targetRoot || document.getElementById('retroarch_root').value || libraryHome.data?.sources?.find(s => ['ready','no_library'].includes(s.status) && s.transport === 'mtp')?.path;
    if (!root) { showStatus(uiText('请先连接掌机并打开或指定 RetroArch 目录'), 'error'); return; }
    const request = ++contentScan.openGeneration;
    ++contentHintGeneration; ++contentInfoGeneration; ++contentDirectoryGeneration;
    contentScan.browserPath = ''; contentScan.browsing = false; contentScan.coreStatus = null;
    contentField('settings').open = false;
    contentField('status').textContent = uiText('正在读取扫描配置…');
    contentField('preview').hidden = true; contentField('apply').hidden = true; contentField('complete').hidden = true;
    contentField('android-suggestions').hidden = true;
    contentScan.setup = null; contentScan.previewId = null; contentScan.imported = null; contentScan.downloaded = null;
    document.getElementById('content-core-transfer').disabled = true;
    document.getElementById('content-core-result').textContent = '';
    const dialog = document.getElementById('content-scan-dialog');
    if (!dialog.open) dialog.showModal();
    contentField('fields').disabled = true;
    contentField('start').disabled = true;
    try {
        const setup = await desktopRequest('/api/content/setup?root=' + encodeURIComponent(root));
        if (request !== contentScan.openGeneration) return;
        contentScan.setup = setup;
        contentField('system').replaceChildren(...setup.systems.map(s => new Option(s.name, s.name)));
        const selected = document.getElementById('system_name').value || selectedLibrarySystem || currentDeviceScan?.playlists?.[0]?.system;
        if (setup.systems.some(s => s.name === selected)) contentField('system').value = selected;
        contentField('profile').replaceChildren(new Option(uiText('新建扫描配置'), ''),
            ...setup.profiles.map((p, index) => new Option(p.system + ' · ' + p.directory, String(index))));
        contentField('android-label').hidden = !setup.android;
        contentField('download').hidden = !setup.android;
        contentField('install-state').textContent = setup.android ? uiText('MTP 无法验证应用私有目录，请在 RetroArch 中确认核心已安装。') : uiText('请填写当前设备已安装核心文件的完整路径。');
        contentField('directory').value = ''; contentField('android').value = ''; contentField('dat').value = '';
        contentField('core-path').value = ''; contentField('abi').value = '';
        contentField('recursive').checked = true; contentField('dat-filter').checked = false;
        document.getElementById('content-directory-picker').hidden = true;
        changeContentSystem();
        const profile = setup.profiles.findIndex(p => p.system === contentField('system').value);
        if (profile >= 0) { contentField('profile').value = String(profile); loadContentProfile(); }
        contentField('status').textContent = uiText('首次指定目录、主机与核心；更新成功后会记住配置。');
    } catch (error) { if (request === contentScan.openGeneration) contentField('status').textContent = error.message; }
    finally { if (request === contentScan.openGeneration) { contentField('fields').disabled = !contentScan.setup; contentField('start').disabled = !contentScan.setup; } }
}

function invalidateContentScan() {
    contentScan.revision++;
    wbIconButton(contentField('start'), 'scan', uiText('开始扫描'));
    contentScan.previewId = null; contentScan.imported = null;
    contentField('preview').hidden = true; contentField('apply').hidden = true; contentField('complete').hidden = true;
    renderContentConfiguration();
}
function changeContentSystem() {
    invalidateContentScan();
    const system = contentScan.setup.systems.find(s => s.name === contentField('system').value);
    contentField('core').replaceChildren(...system.cores.map(c => new Option(c.name + (c.id === system.recommended ? uiText(' · 默认推荐') : ''), c.id)));
    contentField('extensions').value = system.extensions;
    const existing = currentDeviceScan?.root_path === contentScan.setup.root ? currentDeviceScan.playlists.find(p => p.valid && p.system === system.name) : null;
    contentField('playlist-name').value = existing ? decodeURIComponent(existing.path.split('/').pop()) : system.name + '.lpl';
    contentField('recommendation').textContent = system.name === 'MAME' ? uiText('MAME 核心必须与 ROM 集及 DAT 版本一致，不自动认定任意版本可用。')
        : system.name === 'Sega - Saturn' ? uiText('Beetle Saturn 是兼容性候选，需在掌机验证性能；缺少 BIOS 时也无法正常运行。')
        : uiText('默认推荐可更换。已有游戏单独设置的核心将保留，不自动升级已安装核心。');
    changeContentCore();
    contentField('android').value = '';
    contentField('android-suggestions').hidden = true;
    return contentScan.configurationTask = loadContentHints();
}
function changeContentCore() {
    invalidateContentScan(); contentScan.downloaded = null;
    document.getElementById('content-core-transfer').disabled = true;
    document.getElementById('content-core-result').textContent = '';
    contentField('extensions').value = contentScan.setup.systems.find(s => s.name === contentField('system').value).extensions;
    loadContentCoreInfo();
    const directory = contentScan.setup.core_directory;
    contentField('core-path').value = directory && directory !== 'default'
        ? directory.replace(/[\\/]$/, '') + '/' + contentField('core').value + '_libretro' + contentScan.setup.core_suffix : '';
    contentScan.generatedCorePath = contentField('core-path').value;
    loadContentCoreStatus();
}
function loadContentProfile() {
    const profile = contentScan.setup.profiles[Number(contentField('profile').value)];
    if (contentField('profile').value === '' || !profile) {
        contentField('directory').value = ''; contentField('dat').value = ''; contentField('abi').value = '';
        changeContentSystem(); return;
    }
    contentField('system').value = profile.system; changeContentSystem();
    for (const [field, key] of [['directory','directory'],['android','android_directory'],['core','core_id'],['core-path','core_path'],['extensions','extensions'],['dat','dat_path'],['playlist-name','playlist_name']]) contentField(field).value = profile[key] || '';
    contentField('abi').value = profile.abi || '';
    contentField('recursive').checked = profile.recursive; contentField('dat-filter').checked = profile.dat_filter;
    invalidateContentScan(); loadContentCoreInfo(); loadContentCoreStatus();
}
function contentDirectoryStorages() {
    if (!contentScan.setup?.android) return [];
    const serial = contentScan.setup.root.split('/')[2];
    const sources = libraryHome.device?.storages || libraryHome.data?.sources || [];
    return sources.filter(source => source.transport === 'mtp' && source.path.split('/')[2] === serial)
        .map(source => ({label: source.label, root: source.path.split('/').slice(0, 4).join('/') + '/'}));
}
let contentDirectoryGeneration = 0;
async function browseContentDirectory(path) {
    const generation = ++contentDirectoryGeneration;
    const setup = contentScan.setup;
    contentScan.browsing = true; invalidateContentScan();
    const target = path || contentField('directory').value || contentScan.setup.browse_root;
    document.getElementById('content-directory-use').disabled = true;
    document.getElementById('content-directory-entries').replaceChildren();
    document.getElementById('content-directory-path').textContent = uiText('正在读取目录…');
    try {
        const data = await desktopRequest('/api/content/directories?path=' + encodeURIComponent(target));
        if (generation !== contentDirectoryGeneration || setup !== contentScan.setup) return;
        contentScan.browsing = false;
        document.getElementById('content-directory-use').disabled = false;
        contentScan.browserPath = data.path; contentScan.browserParent = data.parent;
        const storages = contentDirectoryStorages();
        const select = document.getElementById('content-directory-storage');
        document.getElementById('content-directory-storage-label').hidden = storages.length === 0;
        select.replaceChildren(...storages.map(storage => new Option(storage.label, storage.root)));
        const current = storages.find(storage => data.path === storage.root || data.path.startsWith(storage.root));
        if (current) select.value = current.root;
        const caption = document.getElementById('content-directory-path');
        caption.textContent = current ? current.label + ' / ' + decodeURIComponent(data.path.slice(current.root.length)) : decodeURIComponent(data.path);
        caption.title = data.path;
        const entries = document.getElementById('content-directory-entries'); entries.replaceChildren();
        for (const item of data.directories) {
            const button = document.createElement('button'); button.type = 'button'; button.className = 'btn btn-muted';
            button.textContent = '▸ ' + item.name; button.onclick = () => browseContentDirectory(item.path); entries.appendChild(button);
        }
        document.getElementById('content-directory-picker').hidden = false;
    } catch (error) {
        if (generation !== contentDirectoryGeneration || setup !== contentScan.setup) return;
        contentScan.browsing = false;
        document.getElementById('content-directory-picker').hidden = true;
        contentField('status').textContent = error.message;
    }
}

function chooseContentDirectory() {
    contentField('directory').value = contentScan.browserPath;
    document.getElementById('content-directory-picker').hidden = true; invalidateContentScan();
    contentField('android').value = ''; contentField('android-suggestions').hidden = true;
    return contentScan.configurationTask = loadContentHints(true);
}
function contentPayload() {
    return {root: contentScan.setup.root, abi: contentField('abi').value, directory: contentField('directory').value,
        android_directory: contentField('android').value, system: contentField('system').value,
        core_id: contentField('core').value, core_path: contentField('core-path').value,
        extensions: contentField('extensions').value, playlist_name: contentField('playlist-name').value, recursive: contentField('recursive').checked,
        dat_path: contentField('dat').value, dat_filter: contentField('dat-filter').checked};
}
async function contentJob(path, payload) {
    if (contentScan.busy || !beginWorkbenchOperation('content-scan')) throw new Error(uiText('请等待当前任务完成'));
    contentScan.busy = true;
    contentField('fields').disabled = true; contentField('close').disabled = true;
    for (const name of ['start','apply','complete']) contentField(name).disabled = true;
    try {
        const started = await desktopRequest(path, payload);
        contentScan.jobId = started.job_id;
        contentField('cancel').hidden = !['/api/content/preview','/api/cores/download'].includes(path);
        const result = await new Promise((resolve, reject) => {
            const events = new EventSource('/api/progress?job_id=' + encodeURIComponent(started.job_id));
            events.onmessage = event => {
                const job = JSON.parse(event.data);
                if (job.status === 'completed') { events.close(); resolve(job.result); }
                else if (job.error || ['failed','cancelled'].includes(job.status)) { events.close(); reject(new Error(job.error || uiText('任务已取消'))); }
                else contentField('status').textContent = currentUILanguage==='en'?`Processing… ${job.total?job.progress+' / '+job.total:''}`:job.message||uiText('处理中…');
            };
        });
        return {id: started.job_id, result};
    } finally {
        contentScan.jobId = null; contentField('cancel').hidden = true;
        contentScan.busy = false; contentField('fields').disabled = false; contentField('close').disabled = false;
        for (const name of ['start','apply','complete']) contentField(name).disabled = false;
        endWorkbenchOperation();
    }
}
async function previewContentScan() {
    if (contentScan.busy) return;
    const setup = contentScan.setup;
    let pending;
    do { pending = contentScan.configurationTask; if (pending) await pending; } while (pending !== contentScan.configurationTask);
    if (contentScan.busy || setup !== contentScan.setup) return;
    invalidateContentScan();
    if (contentScan.browsing) { contentField('status').textContent = uiText('正在读取目录，请稍后再开始扫描。'); return; }
    if (contentScan.browserPath && !document.getElementById('content-directory-picker').hidden) {
        if (document.getElementById('content-directory-use').disabled) {
            contentField('status').textContent = uiText('正在读取目录，请稍后再开始扫描。'); return;
        }
        await chooseContentDirectory();
    }
    if (!contentField('directory').value.trim()) {
        focusContentScanField('directory', uiText('请先选择需要扫描的游戏目录。')); return;
    }
    if (contentScan.setup.android && !contentField('android').value.trim()) {
        await loadContentHints();
        if (!contentField('android').value.trim()) {
            focusContentScanField('android', contentField('android-suggestions').hidden
                ? uiText('尚未识别掌机中的实际路径。请在 RetroArch 的“加载内容”中查看这个目录的完整路径后填写。')
                : uiText('已找到现有列表中的建议路径，请核对后点击“使用所选路径”，再开始扫描。'));
            return;
        }
    }
    if (!contentField('core-path').value.trim()) {
        focusContentScanField('core-path', uiText('请确认已安装核心的完整路径；缺少核心时可展开“从官方下载安装”。')); return;
    }
    try {
        ++contentInfoGeneration;
        const payload = contentPayload(); const key = JSON.stringify(payload);
        const {id, result} = await contentJob('/api/content/preview', payload);
        if (key !== JSON.stringify(contentPayload())) throw new Error(uiText('扫描配置已变化，请重新预览'));
        contentScan.previewId = id;
        wbIconButton(contentField('start'), 'refresh', uiText('重新扫描'));
        contentField('summary').textContent = formatPreviewScope(result, 'scan') + result.core_status + '。' + result.note;
        const rows = contentField('rows'); rows.replaceChildren();
        for (const item of result.added) {
            const row = document.createElement('tr');
            for (const text of [item.label,item.path]) { const cell = document.createElement('td'); cell.textContent = text; row.appendChild(cell); }
            rows.appendChild(row);
        }
        contentField('preview').hidden = false; contentField('apply').hidden = !result.can_apply;
        contentField('status').textContent = result.can_apply ? uiText('扫描完成，请核对后确认更新列表。') : uiText('没有新增游戏或配置变化。');
    } catch (error) { contentField('status').textContent = error.message; }
}
async function applyContentScan() {
    if (!contentScan.previewId) return;
    try {
        const {result} = await contentJob('/api/content/apply', {preview_job_id: contentScan.previewId});
        contentScan.previewId = null; contentScan.imported = result; contentField('apply').hidden = true; contentField('complete').hidden = false;
        contentField('status').textContent = workbenchText(`已更新列表，新增 ${result.added} 项、保留 ${result.retained} 项。`,`Playlist updated: ${result.added} added, ${result.retained} retained. `) + (result.warning || '');
    } catch (error) { invalidateContentScan(); contentField('status').textContent = error.message; }
}
async function completeImportedContent() {
    const imported = contentScan.imported;
    if (!imported) return;
    document.getElementById('retroarch_root').value = contentScan.setup.root;
    closeContentScan(); await scanDevice();
    const index = currentDeviceScan?.playlists?.findIndex(p => p.path === imported.playlist_path);
    if (index >= 0) { await selectScannedPlaylist(index); await runDirectCompletion(); }
}
async function downloadContentCore() {
    try {
        const {result} = await contentJob('/api/cores/download', {core_id:contentField('core').value, abi:contentField('abi').value});
        contentScan.downloaded = result;
        document.getElementById('content-core-result').textContent = `${result.message}\n来源：${result.source}\nSHA-256：${result.sha256}\n核心支持格式：${result.extensions}`;
        document.getElementById('content-core-transfer').disabled = false;
        contentField('status').textContent = uiText('核心已下载，尚未安装；可传到掌机后在 RetroArch 中安装。');
    } catch (error) { contentField('status').textContent = error.message; }
}
async function transferContentCore() {
    const downloaded = contentScan.downloaded;
    if (!downloaded) return;
    try {
        const {result} = await contentJob('/api/cores/transfer', {core_id:downloaded.core_id,abi:downloaded.abi,root:contentScan.setup.root});
        document.getElementById('content-core-result').textContent = result.message;
        contentField('status').textContent = uiText('已传输，待 RetroArch 端安装。');
    } catch (error) { contentField('status').textContent = error.message; }
}
function closeContentScan() {
    if (!contentScan.busy) { contentScan.setup = null; ++contentScan.openGeneration; document.getElementById('content-scan-dialog').close(); }
}
document.getElementById('content-scan-dialog').addEventListener('cancel', event => { if (contentScan.busy) event.preventDefault(); });
contentField('fields').addEventListener('input', invalidateContentScan);

function androidDirectoryCandidates(items, directory) {
    const relative = decodeURIComponent(directory.split('/').slice(4).join('/')).replace(/\/$/, '');
    if (!relative) return [];
    const suffix = '/' + relative + '/';
    const candidates = new Set();
    for (const item of items) {
        const path = String(item.rom_path || '').replaceAll('\\', '/');
        if (!path.startsWith('/storage/') && !path.startsWith('/sdcard/')) continue;
        const index = path.indexOf(suffix);
        if (index >= 0) candidates.add(path.slice(0, index + suffix.length - 1));
    }
    return [...candidates].sort();
}

function focusContentScanField(name, message) {
    contentField('status').textContent = message;
    const field = contentField(name);
    const settings = field.closest?.('details');
    if (settings) settings.open = true;
    field.setAttribute('aria-invalid', 'true');
    field.scrollIntoView({block:'center'}); field.focus({preventScroll:true});
}

function useContentAndroidPath() {
    const value = contentField('android-candidates').value;
    if (!value) return;
    contentField('android').value = value;
    contentField('android').removeAttribute('aria-invalid');
    invalidateContentScan();
    contentField('status').textContent = uiText('已选择掌机路径。核对后点击“开始扫描”，扫描不会立即写入列表。');
}

let contentHintGeneration = 0;
async function loadContentHints(detectSystem = false) {
    const generation = ++contentHintGeneration;
    const payload = contentPayload();
    const setup = contentScan.setup, revision = contentScan.revision;
    if (!payload.directory) return;
    try {
        const playlists = currentDeviceScan?.root_path === payload.root
            ? currentDeviceScan.playlists.filter(p => p.valid && (detectSystem || p.system === payload.system)) : [];
        const matches = await Promise.all(playlists.map(async playlist => {
            const data = await desktopRequest('/api/playlist/items?' + new URLSearchParams({path:playlist.path, system:playlist.system}));
            return {system:playlist.system, candidates:androidDirectoryCandidates(data.items, payload.directory)};
        }));
        if (generation !== contentHintGeneration || setup !== contentScan.setup || revision !== contentScan.revision || contentScan.busy || payload.directory !== contentField('directory').value) return;
        const systems = [...new Set(matches.filter(match => match.candidates.length).map(match => match.system))];
        if (detectSystem && systems.length === 1 && systems[0] !== payload.system
                && contentScan.setup.systems.some(system => system.name === systems[0])) {
            contentField('system').value = systems[0];
            await changeContentSystem();
            return;
        }
        const result = await desktopRequest('/api/content/hints', payload);
        const candidates = [...new Set(matches.filter(match => match.system === payload.system).flatMap(match => match.candidates))];
        if (generation !== contentHintGeneration || setup !== contentScan.setup || revision !== contentScan.revision || contentScan.busy || payload.directory !== contentField('directory').value || payload.system !== contentField('system').value) return;
        const androidDirectory = result.android_directory || (candidates.length === 1 ? candidates[0] : '');
        if (androidDirectory && !contentField('android').value) {
            contentField('android').value = androidDirectory;
            contentField('android').removeAttribute('aria-invalid');
            contentField('status').textContent = uiText('已从现有配置或游戏列表自动识别掌机目录，可直接开始扫描。');
        }
        contentField('android-candidates').replaceChildren(...candidates.map(value => new Option(value, value)));
        contentField('android-suggestions').hidden = candidates.length === 0 || Boolean(contentField('android').value);
        if (result.core_path && !['','DETECT'].includes(result.core_path)) {
            const selected = contentScan.setup.systems.find(s => s.name === payload.system);
            const core = selected.cores.find(c => result.core_path.split(/[\\/]/).pop().startsWith(c.id + '_libretro'));
            if (core && (!contentField('core-path').value || contentField('core-path').value === contentScan.generatedCorePath)) {
                const changedCore = contentField('core').value !== core.id;
                contentField('core').value = core.id; contentField('core-path').value = result.core_path;
                if (changedCore) loadContentCoreInfo();
            }
        }
        loadContentCoreStatus();
        renderContentConfiguration();
    } catch (error) {
        if (generation === contentHintGeneration && setup === contentScan.setup && revision === contentScan.revision) contentField('status').textContent = uiText('无法从已有列表恢复路径：') + error.message;
    }
}

let contentInfoGeneration = 0;
async function loadContentCoreInfo() {
    const generation = ++contentInfoGeneration;
    const core = contentField('core').value;
    const setup = contentScan.setup, system = contentField('system').value;
    const field = contentField('extensions'); const original = field.value;
    try {
        const info = await desktopRequest('/api/cores/info?core_id=' + encodeURIComponent(core));
        if (setup !== contentScan.setup || system !== contentField('system').value || contentScan.busy || generation !== contentInfoGeneration || core !== contentField('core').value || field.value !== original) return;
        const allowed = new Set(info.extensions.concat(['zip','7z']));
        const filtered = original.split(/\s+/).filter(ext => allowed.has(ext));
        if (field.value !== filtered.join(' ') && contentScan.previewId) invalidateContentScan();
        field.value = filtered.join(' ');
        document.getElementById('content-core-formats').textContent = uiText('官方核心支持：') + info.extensions.join(' ') + uiText('。压缩包作为单个入口处理。');
    } catch (error) {
        if (generation === contentInfoGeneration && setup === contentScan.setup && system === contentField('system').value) document.getElementById('content-core-formats').textContent = uiText('官方格式信息暂不可读，当前使用主机预设，可手动核对：') + error.message;
    }
}

contentField('directory').addEventListener('change', () => { contentField('android').value = ''; contentField('android-suggestions').hidden = true; contentScan.configurationTask = loadContentHints(true); });

contentField('abi').addEventListener('change', () => { contentScan.downloaded = null; document.getElementById('content-core-transfer').disabled = true; document.getElementById('content-core-result').textContent = ''; });

async function cancelContentScan() { if (contentScan.jobId) { try { await desktopRequest('/api/jobs/cancel', {job_id: contentScan.jobId}); contentField('status').textContent = uiText('正在取消，等待当前读取完成…'); } catch (error) { contentField('status').textContent = error.message; } } }

contentField('fields').addEventListener('input', event => { event.target.removeAttribute('aria-invalid'); });


function contentCoreStatusKey() {
    return JSON.stringify([contentScan.setup?.root, contentField('core').value, contentField('core-path').value]);
}

function renderContentConfiguration() {
    if (!contentScan.setup) return;
    const text = (name, value) => { document.getElementById('content-config-' + name).textContent = value; };
    text('system', contentField('system').value);
    text('core', contentField('core').selectedOptions[0]?.textContent || uiText('待选择核心'));
    const storages = contentDirectoryStorages();
    const directory = contentField('directory').value;
    const storage = storages.find(value => directory.startsWith(value.root));
    text('source', storage ? storage.label + ' / ' + decodeURIComponent(directory.slice(storage.root.length)) : directory || uiText('未选择目录'));
    const root = contentScan.setup.root;
    const targetStorage = storages.find(value => root.startsWith(value.root));
    text('target', targetStorage ? targetStorage.label + ' / ' + decodeURIComponent(root.slice(targetStorage.root.length)) : root);
    const status = contentScan.coreStatus?.key === contentCoreStatusKey() ? contentScan.coreStatus : null;
    text('core-state', uiText(status?.message || '核心状态尚未检查'));
    text('core-detail', uiText(status?.detail || '指定核心路径后检查安装状态。'));
    document.getElementById('content-config-core-state').dataset.state = status?.state || 'unconfigured';
}

let contentCoreStatusGeneration = 0;
async function loadContentCoreStatus() {
    if (!contentScan.setup) return;
    const generation = ++contentCoreStatusGeneration;
    const setup = contentScan.setup, key = contentCoreStatusKey();
    renderContentConfiguration();
    try {
        const result = await desktopRequest('/api/content/core-status', {root:setup.root, core_path:contentField('core-path').value});
        if (generation !== contentCoreStatusGeneration || setup !== contentScan.setup || key !== contentCoreStatusKey()) return;
        contentScan.coreStatus = {...result, key};
        contentField('install-state').textContent = result.detail;
        renderContentConfiguration();
        if (['missing','unconfigured'].includes(result.state)) contentField('settings').open = true;
    } catch (error) {
        if (generation !== contentCoreStatusGeneration || setup !== contentScan.setup || key !== contentCoreStatusKey()) return;
        contentScan.coreStatus = {key, state:'unknown', message:uiText('核心状态检查失败'), detail:error.message};
        renderContentConfiguration();
    }
}

contentField('core-path').addEventListener('change', loadContentCoreStatus);
contentField('fields').addEventListener('input', renderContentConfiguration);
document.getElementById('content-scan-dialog').addEventListener('close', () => {
    if (!document.getElementById('content-scan-dialog').open) { contentScan.setup = null; ++contentScan.openGeneration; }
});
