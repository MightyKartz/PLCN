/* State rules are independent of the DOM so asynchronous UI transitions are testable. */
function repairActionStatus(change, mode = 'both') {
    const unfinished = Object.values(change.artwork || {}).some(image => image.status !== 'exists');
    if ((change.applied || change.match_status === 'applied') && (mode === 'names' || !unfinished)) return 'applied';
    if (change.identity?.requires_review && !change.identity_name_edited) return 'incomplete';
    if (mode !== 'names' && ['not_found','unavailable'].includes(change.artwork_gallery_status) && !change.artwork_source_confirmed) return 'incomplete';
    if (change.artwork_blocked && mode !== 'names') return 'incomplete';
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

// Derived from current evidence and task results, never cached as another source of truth.
function previewArtworkState(change, mode = 'both') {
    if (mode === 'names' || change.cover_download_status === 'skipped-download') return 'not_requested';
    if (change.cover_download_status === 'failed') return change.cover_download_reason === 'not_found' ? 'no_source' : 'failed';
    if ((change.cover_download_status === 'success' || change.thumbnail_exists || change.local_thumbnail_exists || change.cover_exists)
            && Object.values(change.artwork || {}).some(image => image.status !== 'exists')) return 'partial';
    if (change.cover_download_status === 'success') return 'downloaded';
    if (change.thumbnail_exists || change.local_thumbnail_exists || change.cover_exists) return 'exists';
    if (change.artwork_gallery_status === 'unavailable') return 'query_failed';
    if (change.artwork_identity_status === 'unresolved' || change.identity?.state === 'unresolved') return 'unidentified';
    if (change.artwork_gallery_status === 'not_found') return 'no_source';
    if (change.thumbnail_source) return 'available';
    if (change.artwork_candidates?.length) return 'choose_version';
    return 'no_source';
}

function previewIdentityLabel(change) {
    const labels = {
        confirmed_rule: ['人工规则匹配', 'Confirmed rule'], checksum_match: ['校验值匹配', 'Checksum match'],
        database_title: ['数据库名称匹配', 'Database title match'], exact_title: ['精确名称匹配', 'Exact title match'],
        title_family: ['游戏名称已识别', 'Title family identified'], recommended: ['默认推荐', 'Default recommendation'], candidate: ['默认推荐', 'Default recommendation'],
        conflict: ['身份证据冲突', 'Conflicting identity evidence'], unresolved: ['身份未识别', 'Identity not identified']
    };
    if (change.identity_name_edited) return workbenchText('手动指定名称', 'Manually specified title');
    const label = labels[change.identity?.state];
    return label ? workbenchText(...label) : '';
}

function buildRepairPreviewSummary(changes, mode) {
    const counts = {all:changes.length, matched:0, review:0, duplicate:0, ready:0, completed:0, 'missing-cover':0, edited:0,
        renamed:0, downloads:0, selected:0, queryFailed:0, candidates:0};
    for (const change of changes) {
        const info = getMatchInfo(change);
        const actionable = isActionableChange(change);
        if (actionable) counts.matched++;
        if (['review','duplicate'].includes(info.kind)) counts.review++;
        if (['duplicate','ready','completed'].includes(info.kind)) counts[info.kind]++;
        const artwork = previewArtworkState(change, mode);
        if (['partial','choose_version','no_source','unidentified','query_failed','failed'].includes(artwork)) counts['missing-cover']++;
        if (artwork === 'query_failed') counts.queryFailed++;
        if (change.identity?.requires_review && !change.identity_name_edited) counts.candidates++;
        if (isEditedChange(change)) counts.edited++;
        if (actionable && change.enabled !== false) {
            counts.selected++;
            if (mode !== 'artwork' && !currentMatchesWriteName(change)) counts.renamed++;
            if (mode !== 'names' && needsCoverDownload(change, info)) counts.downloads++;
        }
    }
    return counts;
}

function formatPreviewScope(summary, scope) {
    if (scope === 'scan') return workbenchText(
        `新增 ${summary.added.length} 项 · 保留 ${summary.retained} 项 · 跳过 ${summary.skipped} 个文件。此次仅更新列表；名称与图片在更新后单独分析。`,
        `Add ${summary.added.length} entries · Keep ${summary.retained} · Skip ${summary.skipped} files. This plan updates playlists only; analyze names and artwork afterwards.`);
    return workbenchText(
        `本次所选：修改名称 ${summary.renamed} 项 · 补全图片 ${summary.downloads} 项。待处理 ${summary.review} 项，其中身份待核对 ${summary.candidates} 项、图库查询失败 ${summary.queryFailed} 项。保留游戏文件与单项核心。`,
        `Selected: rename ${summary.renamed} · Complete artwork for ${summary.downloads}. ${summary.review} need attention, including ${summary.candidates} identity reviews and ${summary.queryFailed} gallery errors. Keep game files and per-entry cores.`);
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
        canReviewBatch: !busy && Boolean(input.scanned && input.batchDir)
    };
}

const workbench = { operation: null, previewKey: null, taskMessage: '', jobId: null };

function workbenchText(zh, en) { return currentUILanguage === 'en' ? en : zh; }
function workbenchInputKey() {
    return JSON.stringify(['playlist_path', 'system_name', 'rom_name_cn_path']
        .map(id => document.getElementById(id).value.trim()).concat(getThumbnailsDirectory(), getRepairMode()));
}
function workbenchSnapshot() {
    const value = id => document.getElementById(id).value.trim();
    return deriveWorkbenchState({
        ...workbench, inputKey: workbenchInputKey(), scanned: Boolean(currentDeviceScan?.connected),
        playlist: value('playlist_path'), system: value('system_name'), selected: getIncludedChanges().length,
        download: getProcessingOptions().download_thumbnails, thumbnails: getThumbnailsDirectory(),
        batchDir: currentDeviceScan?.directories?.playlists || ''
    });
}
function beginWorkbenchOperation(operation) {
    if (workbench.operation) return false;
    workbench.taskMessage = '';
    workbench.operation = operation;
    renderWorkbench();
    return true;
}
function endWorkbenchOperation() {
    workbench.operation = null;
    workbench.taskMessage = '';
    renderWorkbench();
}
function invalidateWorkbenchPreview() {
    workbench.previewKey = null;
    currentChanges = [];
    currentPreviewFilter = 'all';
    document.getElementById('preview-search').value = '';
    renderPreviewTable([]); updateSummary([]);
    setPreviewAreaVisible(false);
    renderWorkbench();
}
function renderWorkbench() {
    const shell = document.querySelector('.app-shell');
    if (!shell) return;
    const state = workbenchSnapshot();
    document.getElementById('browse-games-button').hidden = !state.previewValid;
    document.getElementById('browse-games-button').disabled = state.busy;
    document.getElementById('browse-games-button').textContent = workbenchText('返回游戏列表', 'Back to games');
    shell.classList.toggle('library-loaded', state.hasLibrary);
    shell.classList.toggle('preview-loaded', state.previewValid);
    const playlistPath = document.getElementById('playlist_path').value;
    const allSystems = !playlistPath;
    document.getElementById('preview-button').disabled = allSystems ? (!state.canReviewBatch || !currentDeviceScan?.playlists?.length) : !state.canPreview;
    document.getElementById('preview-options').hidden = !state.previewValid;
    for (const id of ['option-write-names', 'option-download-artwork']) document.getElementById(id).disabled = state.busy;
    const apply = document.getElementById('apply-button');
    apply.disabled = !state.canApply;
    apply.hidden = !state.previewValid;
    const count = getIncludedChanges().length;
    apply.textContent = workbenchText(`确认应用 ${count} 项`, `Confirm ${count} ${count === 1 ? 'change' : 'changes'}`);
    document.getElementById('apply-summary-panel').hidden = !state.previewValid || state.busy;
    if (state.previewValid && !state.busy) {
        document.getElementById('apply-summary-text').textContent = formatApplySummaryText(
            buildApplySummary(getIncludedChanges(), getProcessingOptions()));
    }
    const showOverview = allSystems && Boolean(currentDeviceScan?.connected) && !state.previewValid && !state.busy;
    renderLibraryOverview(showOverview);
    document.getElementById('workspace-empty').hidden = showOverview || state.previewValid
        || Boolean(playlistPath && workbench.operation !== 'preview');
    document.getElementById('workspace-empty').textContent = workbench.operation === 'preview'
        ? workbenchText('正在分析名称与图片，生成修复建议…', 'Analyzing names and artwork to prepare suggestions…')
        : allSystems && currentDeviceScan?.playlists?.length
            ? workbenchText('点击“一键补全”处理全部主机，或在左侧选择一台主机单独查看和补全。', 'Use Auto-complete for all systems, or pick a system on the left to browse and complete it alone.')
            : uiText('选择左侧列表，然后预览名称与图片变更。');
    const note = document.getElementById('completion-entry-note');
    note.hidden = state.previewValid;
    note.textContent = allSystems && currentDeviceScan?.playlists?.length
        ? workbenchText('自动匹配全部主机的中文名与图片并直接补全，完成后显示结果。', 'Match and apply names and artwork for all systems, then show the result.')
        : workbenchText('自动匹配中文名与图片，预览后确认应用。', 'Match Chinese names and artwork automatically; preview before applying.');
    document.getElementById('preview-button').classList.toggle('btn-ghost', state.previewValid);
    document.getElementById('preview-button').textContent = state.previewValid ? workbenchText('重新预览', 'Refresh preview') : workbenchText('一键补全', 'Auto-complete');
    const selectedSystem = document.getElementById('system_name').value;
    const selectedTitle = !playlistPath ? '' : selectedSystem ? getSystemAbbreviation(selectedSystem) : playlistPath.replaceAll('\\', '/').split('/').pop();
    document.getElementById('workspace-title').textContent = state.previewValid ? `${selectedTitle} · ${uiText('修复预览')}`
        : workbench.operation === 'preview' ? `${selectedTitle} · ${workbenchText('正在分析', 'Analyzing')}`
        : selectedTitle || (currentDeviceScan?.playlists?.length
            ? `${workbenchText('全部主机', 'All systems')} · ${formatGameCount(currentDeviceScan.totals?.items || 0)}`
            : currentDeviceScan?.connected ? workbenchText('设备概览', 'Device overview') : uiText('选择游戏列表'));
    document.getElementById('workspace-title').title = '';
    const libraryRoot = document.getElementById('retroarch_root').value;
    document.getElementById('library-location').textContent = libraryRoot
        ? (libraryRoot.startsWith('mtp://') ? 'MTP · ' : libraryRoot.startsWith('adb://') ? 'ADB · ' : workbenchText('本地 · ', 'Local · ')) + shortPath(libraryRoot)
        : workbenchText('手动选择的列表', 'Manually selected list');
    renderDeviceStorage();
    document.getElementById('library-location').title = document.getElementById('retroarch_root').value;
    document.querySelectorAll('[data-input-control], #scanned-playlists button').forEach(control => {
        control.disabled = state.busy;
    });
    document.getElementById('scan-device-btn').disabled = state.busy || !document.getElementById('retroarch_root').value.trim();
    const images = getThumbnailsDirectory();
    const imagesPending = images && !document.getElementById('thumbnails_override').value.trim()
        && currentDeviceScan?.directories?.thumbnails_exists === false;
    document.getElementById('effective-image-directory').textContent = images
        ? workbenchText('当前图片目录：', 'Current artwork folder: ') + images
            + (imagesPending ? workbenchText('（尚不存在，首次补图时自动创建）', ' (will be created on first use)') : '')
        : workbenchText('未检测到图片目录，请指定目录后补图。', 'No artwork folder detected. Choose a folder to add artwork.');
    document.getElementById('choose-image-directory').disabled = state.busy;
    document.getElementById('preview-search').disabled = state.busy;
    document.getElementById('preview-search').setAttribute('aria-label', uiText('搜索游戏名 / rom 名称'));
    document.getElementById('preview-container').inert = state.busy;
    document.getElementById('workbench-busy-label').textContent = state.busy && workbench.operation !== 'artwork'
        ? workbench.taskMessage || workbenchText('正在处理，请稍候…', 'Working, please wait…') : '';
    document.getElementById('workbench-busy').hidden = !state.busy || workbench.operation === 'artwork';
    document.getElementById('task-status-button').hidden = !workbench.jobId;
    const counts = buildRepairPreviewSummary(currentChanges, getRepairMode());
    document.getElementById('preview-plan-scope').textContent = formatPreviewScope(counts, 'repair');
    document.querySelectorAll('.filter-btn').forEach(button => {
        button.disabled = state.busy;
        button.classList.toggle('active', button.dataset.filter === currentPreviewFilter);
        button.setAttribute('aria-pressed', String(button.dataset.filter === currentPreviewFilter));
        button.querySelector('.filter-count').textContent = counts[button.dataset.filter] || 0;
    });
    syncGameLibrary(state);
    if (typeof renderLibraryHome === 'function') renderLibraryHome();
}

if (typeof module !== 'undefined') module.exports = { deriveWorkbenchState, downloadTaskOutcome, repairActionStatus, previewArtworkState, previewIdentityLabel, buildRepairPreviewSummary, formatPreviewScope };
