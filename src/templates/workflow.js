/* State rules are independent of the DOM so asynchronous UI transitions are testable. */
function deriveWorkbenchState(input) {
    const busy = Boolean(input.operation);
    const previewValid = input.previewKey !== null && input.previewKey === input.inputKey;
    return {
        busy,
        hasLibrary: Boolean(input.scanned || input.playlist || input.batchDir),
        previewValid,
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
    document.querySelector('.workflow-strip').hidden = batch;
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
    document.getElementById('workspace-empty').hidden = state.previewValid || batch;
    document.getElementById('workspace-empty').textContent = document.getElementById('playlist_path').value
        ? workbenchText('已选择列表，点击“预览变更”检查名称与图片。', 'List selected. Preview the name and artwork changes.')
        : uiText('选择左侧列表，然后预览名称与图片变更。');
    document.getElementById('preview-button').classList.toggle('btn-ghost', state.previewValid);
    document.getElementById('preview-button').textContent = state.previewValid ? workbenchText('重新预览', 'Refresh preview') : uiText('预览变更');
    document.getElementById('workspace-title').textContent = batch ? uiText('全部游戏列表')
        : (state.previewValid ? uiText('修复预览') : uiText('选择游戏列表'));
    document.getElementById('library-location').textContent = shortPath(document.getElementById('retroarch_root').value) || workbenchText('手动选择的列表', 'Manually selected list');
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
    document.getElementById('workbench-busy').textContent = state.busy
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
}

if (typeof module !== 'undefined') module.exports = { deriveWorkbenchState };
