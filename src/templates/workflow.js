/* State rules are independent of the DOM so asynchronous UI transitions are testable. */
function repairActionStatus(change, mode = 'both') {
    if (change.applied || change.match_status === 'applied') return 'applied';
    if (!String(change.new_label || '').trim()) return 'incomplete';
    const current = String(change.original_item_label || change.original_label || '').trim();
    const renamed = current !== String(change.new_label).trim();
    if (mode === 'names') return renamed ? 'rename' : 'ready';
    if (!String(change.thumbnail_source || '').trim()) return 'incomplete';
    const artwork = Object.values(change.artwork || {});
    const missing = artwork.length ? artwork.some(image => image.status !== 'exists')
        : !Boolean(change.thumbnail_exists || change.local_thumbnail_exists || change.cover_exists);
    if (mode === 'artwork') return missing ? 'download' : 'ready';
    return renamed ? (missing ? 'matched' : 'rename') : (missing ? 'download' : 'ready');
}

function downloadTaskOutcome(status, summary) {
    const failed = Number(summary?.total?.failed) || 0;
    const cancelled = status === 'cancelled';
    return {failed, cancelled, complete: status === 'completed' && !failed,
        label: cancelled ? '已取消' : failed ? '部分完成' : '完成',
        message: cancelled ? '任务已取消，已完成的结果会保留'
            : failed ? `任务已结束，${failed} 张图片失败，请查看下载明细并重新补图` : '所有操作完成'};
}

function deriveWorkbenchState(input) {
    const busy = Boolean(input.operation);
    const previewValid = input.previewKey !== null && input.previewKey === input.inputKey;
    return {
        busy,
        hasLibrary: Boolean(input.scanned || input.playlist || input.batchDir),
        previewValid,
        libraryView: previewValid ? 'preview' : input.playlist ? 'games' : 'home',
        canPreview: !busy && Boolean(input.playlist && input.system),
        canApply: !busy && previewValid && input.selected > 0 && Boolean(input.playlist)
            && (!input.download || Boolean(input.thumbnails)),
        canBatch: !busy && Boolean(input.batchDir) && (!input.download || Boolean(input.batchThumbnails)),
        steps: [input.scanned || input.playlist ? 'done' : 'current',
            previewValid ? 'done' : input.playlist ? 'current' : 'waiting',
            input.operation === 'apply' ? 'current' : input.applied ? 'done' : 'waiting']
    };
}

const workbench = { operation: null, previewKey: null, applied: false, hasTask: false, jobId: null };

function workbenchText(zh, en) { return currentUILanguage === 'en' ? en : zh; }
function workbenchInputKey() {
    return JSON.stringify(['playlist_path', 'system_name', 'thumbnails_dir', 'rom_name_cn_path', 'repair-mode']
        .map(id => document.getElementById(id).value.trim()));
}
function workbenchSnapshot() {
    const value = id => document.getElementById(id).value.trim();
    return deriveWorkbenchState({
        ...workbench, inputKey: workbenchInputKey(), scanned: Boolean(currentDeviceScan?.playlists?.length),
        playlist: value('playlist_path'), system: value('system_name'), selected: getIncludedChanges().length,
        download: value('repair-mode') !== 'names', thumbnails: value('thumbnails_dir'),
        batchDir: value('batch_dir'), batchThumbnails: value('batch_thumbnails_dir')
    });
}
function beginWorkbenchOperation(operation) {
    if (workbench.operation) return false;
    workbench.operation = operation;
    renderWorkbench();
    return true;
}
function endWorkbenchOperation() {
    workbench.operation = null;
    renderWorkbench();
}
function invalidateWorkbenchPreview() {
    workbench.previewKey = null;
    workbench.applied = false;
    if (workbench.operation !== 'apply') workbench.hasTask = false;
    currentChanges = [];
    currentPreviewFilter = 'all';
    document.getElementById('preview-search').value = '';
    selectedChangeIndex = -1;
    hideApplySummary(); clearInspector(); renderPreviewTable([]); updateSummary([]);
    setPreviewAreaVisible(false);
    renderWorkbench();
}
function renderWorkbench() {
    const shell = document.querySelector('.app-shell');
    if (!shell) return;
    const state = workbenchSnapshot();
    const batch = document.getElementById('batch-tab').classList.contains('active');
    document.querySelector('.workflow-strip').hidden = batch || (!state.previewValid && !['preview', 'apply'].includes(workbench.operation));
    document.getElementById('browse-games-button').hidden = batch || !state.previewValid;
    document.getElementById('browse-games-button').disabled = state.busy;
    document.getElementById('browse-games-button').textContent = workbenchText('返回游戏列表', 'Back to games');
    document.querySelector('#organize-menu > summary').textContent = workbenchText('批量整理', 'Organize games');
    if (workbench.operation === 'preview') document.getElementById('organize-menu').open = false;
    shell.classList.toggle('library-loaded', state.hasLibrary);
    shell.classList.toggle('preview-loaded', state.previewValid && !batch);
    shell.classList.toggle('task-visible', workbench.hasTask);
    document.getElementById('preview-button').disabled = !state.canPreview;
    document.getElementById('preview-button').hidden = batch;
    const apply = document.getElementById('apply-button');
    apply.disabled = !state.canApply;
    apply.hidden = batch || !state.previewValid;
    const count = getIncludedChanges().length;
    apply.textContent = workbenchText(`应用 ${count} 项变更`, `Apply ${count} ${count === 1 ? 'change' : 'changes'}`);
    document.getElementById('confirm-apply-button').disabled = !state.canApply;
    document.getElementById('batch-start-button').hidden = !batch;
    document.getElementById('batch-start-button').disabled = !state.canBatch;
    document.getElementById('batch-explanation').hidden = !batch;
    document.getElementById('workspace-empty').hidden = state.previewValid || batch
        || Boolean(document.getElementById('playlist_path').value && workbench.operation !== 'preview');
    document.getElementById('workspace-empty').textContent = workbench.operation === 'preview'
        ? workbenchText('正在分析名称与图片，生成修复建议…', 'Analyzing names and artwork to prepare suggestions…')
        : uiText('选择左侧列表，然后预览名称与图片变更。');
    document.getElementById('preview-button').classList.toggle('btn-ghost', state.previewValid);
    document.getElementById('preview-button').textContent = state.previewValid ? workbenchText('重新预览', 'Refresh preview') : uiText('预览变更');
    const playlistPath = document.getElementById('playlist_path').value;
    const selectedSystem = document.getElementById('system_name').value;
    const selectedTitle = !playlistPath ? '' : selectedSystem ? getSystemAbbreviation(selectedSystem) : playlistPath.replaceAll('\\', '/').split('/').pop();
    document.getElementById('workspace-title').textContent = batch ? uiText('全部游戏列表')
        : state.previewValid ? `${selectedTitle} · ${uiText('修复预览')}`
        : workbench.operation === 'preview' ? `${selectedTitle} · ${workbenchText('正在分析', 'Analyzing')}`
        : selectedTitle || uiText('选择游戏列表');
    document.getElementById('workspace-title').title = '';
    const libraryRoot = document.getElementById('retroarch_root').value;
    document.getElementById('library-location').textContent = libraryRoot
        ? (libraryRoot.startsWith('adb://') ? 'ADB · ' : workbenchText('本地 · ', 'Local · ')) + shortPath(libraryRoot)
        : workbenchText('手动选择的列表', 'Manually selected list');
    document.getElementById('library-location').title = document.getElementById('retroarch_root').value;
    document.querySelectorAll('[data-workflow-step]').forEach((step, index) => {
        step.dataset.state = state.steps[index];
        if (state.steps[index] === 'current') step.setAttribute('aria-current', 'step');
        else step.removeAttribute('aria-current');
        step.querySelector('.flow-state').textContent = state.steps[index] === 'done' ? uiText('已完成')
            : state.steps[index] === 'current' ? uiText('当前') : uiText('等待');
    });
    document.querySelectorAll('[data-input-control], .mode-switch button, #scanned-playlists button').forEach(control => {
        control.disabled = state.busy;
    });
    document.getElementById('scan-device-btn').disabled = state.busy || !document.getElementById('retroarch_root').value.trim();
    document.getElementById('preview-search').disabled = state.busy;
    document.getElementById('preview-search').setAttribute('aria-label', uiText('搜索游戏名 / rom 名称'));
    document.querySelector('.workflow-strip').setAttribute('aria-label', uiText('修复流程'));
    document.getElementById('preview-container').inert = state.busy;
    document.getElementById('inspector-panel').inert = state.busy;
    document.getElementById('workbench-busy').textContent = state.busy && workbench.operation !== 'artwork'
        ? workbenchText('正在处理，请稍候…', 'Working, please wait…') : '';
    const counts = {all: currentChanges.length, matched: 0, review: 0, duplicate: 0, ready: 0, completed: 0, 'missing-cover': 0, edited: 0};
    for (const change of currentChanges) {
        const info = getMatchInfo(change);
        if (isActionableChange(change)) counts.matched++;
        if (['review', 'duplicate'].includes(info.kind)) counts.review++;
        if (['duplicate', 'ready', 'completed'].includes(info.kind)) counts[info.kind]++;
        if (!change.thumbnail_source) counts['missing-cover']++;
        if (isEditedChange(change)) counts.edited++;
    }
    document.querySelectorAll('.filter-btn').forEach(button => {
        button.disabled = state.busy;
        button.classList.toggle('active', button.dataset.filter === currentPreviewFilter);
        button.setAttribute('aria-pressed', String(button.dataset.filter === currentPreviewFilter));
        button.querySelector('.filter-count').textContent = counts[button.dataset.filter] || 0;
    });
    syncGameLibrary(state, batch);
    if (typeof renderLibraryHome === 'function') renderLibraryHome();
}

if (typeof module !== 'undefined') module.exports = { deriveWorkbenchState, downloadTaskOutcome, repairActionStatus };
