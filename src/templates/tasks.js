/* Apply confirmation, background task progress and download details. */
let lastAppliedChangeKeys = new Set();
let lastAppliedDownloadEnabled = true;
let lastAppliedWriteNames = true;

let batchRunJobId = null;
let batchRunStage = '';
let batchRunCreatedArtworkDir = false;

let actionToastTimer = null;

function showActionToast({message, receiptId = '', details = null}) {
    const toast = document.getElementById('action-toast');
    document.getElementById('action-toast-text').textContent = message;
    const undo = document.getElementById('action-toast-undo');
    undo.hidden = !receiptId;
    undo.disabled = Boolean(workbench.operation);
    undo.onclick = receiptId ? () => undoCompletion(receiptId) : null;
    const view = document.getElementById('action-toast-details');
    view.hidden = !details;
    view.onclick = details || null;
    toast.hidden = false;
    toast.onmouseenter = toast.onfocusin = () => clearTimeout(actionToastTimer);
    toast.onmouseleave = toast.onfocusout = () => armActionToast();
    armActionToast();
}

function armActionToast() {
    clearTimeout(actionToastTimer);
    actionToastTimer = setTimeout(hideActionToast, 10000);
}

function hideActionToast() {
    clearTimeout(actionToastTimer);
    document.getElementById('action-toast').hidden = true;
}

function startCompletion() {
    return document.getElementById('playlist_path').value ? runDirectCompletion() : runAllSystemsCompletion();
}

function refreshAfterCompletion() {
    if (document.getElementById('playlist_path').value) retryGameLibrary();
    else resetGameLibrary();
    refreshWorkbenchOverview();
    renderWorkbench();
    if (desktopDialog.open && desktopView === 'tasks') refreshDesktop();
}

function watchCompletionJob(jobId, prefix = '') {
    return new Promise((resolve, reject) => {
        const events = new EventSource(`/api/progress?job_id=${jobId}`);
        events.onmessage = event => {
            const job = JSON.parse(event.data);
            if (job.status === 'completed') { events.close(); resolve(job.result); }
            else if (job.error || ['failed', 'cancelled'].includes(job.status)) {
                events.close();
                const error = new Error(job.error || workbenchText('任务已取消', 'Task cancelled'));
                error.cancelled = job.status === 'cancelled';
                error.result = job.result;
                reject(error);
            } else {
                workbench.taskMessage = prefix + (job.message || '');
                renderWorkbench();
            }
        };
        // EventSource reconnects; a transient disconnect must not advance the run.
    });
}

async function cancelCompletion() {
    const jobId = batchRunJobId || workbench.jobId;
    if (!jobId) return;
    try {
        await desktopRequest('/api/jobs/cancel', {job_id: jobId});
    } catch (error) {
        showStatus(error.message, 'error');
    }
}

async function undoCompletion(receiptId) {
    if (!beginWorkbenchOperation('apply')) return;
    document.getElementById('action-toast-undo').disabled = true;
    try {
        const started = await desktopRequest('/api/completion/undo', {id: receiptId});
        workbench.jobId = started.job_id;
        renderWorkbench();
        const summary = await watchCompletionJob(started.job_id, workbenchText('正在撤销：', 'Undoing: '));
        const skipped = summary?.skipped?.length || 0;
        showActionToast({message: skipped
            ? workbenchText(`已撤销部分内容，${skipped} 项在补全后被改动，已保留`, `Partially undone; ${skipped} items changed since completion were kept`)
            : workbenchText('已撤销', 'Undone'),
            details: () => openDesktop('tasks')});
    } catch (error) {
        showActionToast({message: workbenchText('撤销失败：', 'Undo failed: ') + error.message});
    } finally {
        workbench.jobId = null;
        invalidateWorkbenchPreview();
        endWorkbenchOperation();
        refreshAfterCompletion();
    }
}

function needsManualReview(change, options) {
    return Boolean(change.identity?.requires_review)
        || (options.download_thumbnails && ['unavailable', 'not_found'].includes(change.artwork_gallery_status))
        || !(change.new_label || '').trim()
        || (options.download_thumbnails && !change.thumbnail_source);
}

async function runDirectCompletion(scope = null) {
    const selected = scope ? new Map(scope.entries) : null;
    const playlistPath = document.getElementById('playlist_path').value;
    const systemName = document.getElementById('system_name').value;
    const thumbnailsDir = getThumbnailsDirectory();

    if (!playlistPath || !systemName) {
        showActionToast({message: workbenchText('请先选择游戏列表', 'Choose a playlist first')});
        return;
    }
    const options = getProcessingOptions();
    if (options.download_thumbnails && !thumbnailsDir) {
        showActionToast({message: workbenchText('请先指定图片目录', 'Choose an artwork folder first')});
        return;
    }
    if (!beginWorkbenchOperation('apply')) return;
    invalidateWorkbenchPreview();
    const previewKey = workbenchInputKey();
    try {
        if (!await saveConfig('single')) throw new Error(uiText('读取失败'));
        workbench.taskMessage = workbenchText('正在分析可补全的内容…', 'Analyzing what can be completed…');
        renderWorkbench();
        const data = await desktopRequest('/api/playlist/preview', {
            playlist_path: playlistPath, system_name: systemName,
            thumbnails_dir: thumbnailsDir, options
        });
        if (data.error) throw new Error(data.error);
        if (previewKey !== workbenchInputKey()) throw new Error(workbenchText('配置已变化，请重新分析', 'Inputs changed; analyze again'));
        const changes = (data.changes || []).filter(change => !selected || selected.get(change.index) === change.path);
        if (selected && changes.length !== selected.size)
            throw new Error(workbenchText('列表已变化，请重新读取后选择游戏', 'The playlist changed. Reload it before selecting games'));
        const prepared = preparePreviewChanges(changes);
        const included = prepared.filter(change => change.enabled !== false && isActionableChange(change));
        const needsManual = prepared.filter(change => !(change.enabled !== false && isActionableChange(change))
            && needsManualReview(change, options)).length;
        const openTasks = () => openDesktop('tasks');
        if (!included.length) {
            showActionToast({message: workbenchText('没有可自动补全的内容', 'Nothing can be completed automatically')
                + (needsManual ? workbenchText(`，${needsManual} 个游戏需手动处理`, `, ${needsManual} games need manual work`) : ''),
                details: needsManual ? () => previewTask(scope) : openTasks});
            return;
        }
        const applyOptions = {...options};
        if (included.every(change => currentMatchesWriteName(change))) applyOptions.write_names = false;
        const started = await desktopRequest('/api/playlist/apply', {
            playlist_path: playlistPath, changes: included.map(change => ({...change})),
            thumbnails_dir: thumbnailsDir, options: applyOptions
        });
        workbench.jobId = started.job_id;
        renderWorkbench();
        const result = await watchCompletionJob(started.job_id, workbenchText('正在补全：', 'Completing: '));
        const appliedCount = result?.applied_count ?? included.length;
        const failedImages = Object.values(result?.download_summary?.types || {})
            .reduce((total, stats) => total + (stats.failed || 0), 0);
        let message = workbenchText(`已补全 ${appliedCount} 个游戏`, `Completed ${appliedCount} ${appliedCount === 1 ? 'game' : 'games'}`);
        if (failedImages) message += workbenchText(`，${failedImages} 张封面下载失败`, `, ${failedImages} images failed`);
        if (result?.memory_warning) message += ' · ' + result.memory_warning;
        if (needsManual) message += workbenchText(`，${needsManual} 个游戏需手动处理`, `, ${needsManual} games need manual work`);
        showActionToast({message, receiptId: result?.receipt_id || '',
            details: needsManual ? () => previewTask(scope) : openTasks});
    } catch (error) {
        if (error.cancelled) {
            showActionToast({message: workbenchText('已取消，已完成的部分会保留', 'Cancelled; completed work is kept.'),
                receiptId: error.result?.receipt_id || '', details: () => openDesktop('tasks')});
        } else {
            showActionToast({message: error.message, details: () => openDesktop('tasks')});
        }
    } finally {
        workbench.jobId = null;
        endWorkbenchOperation();
        refreshAfterCompletion();
    }
}

async function runAllSystemsCompletion(options = {write_names: true, download_thumbnails: true}) {
    if (workbench.operation || !currentDeviceScan?.directories?.playlists) return;
    if (!beginWorkbenchOperation('apply')) return;
    batchRunStage = '';
    batchRunCreatedArtworkDir = currentDeviceScan?.directories?.thumbnails_exists === false
        && !document.getElementById('thumbnails_override').value.trim();
    let analysis = null;
    try {
        const started = await desktopRequest('/api/batch/preview', {
            batch_dir: currentDeviceScan.directories.playlists,
            thumbnails_dir: getThumbnailsDirectory(),
            rom_name_cn_path: document.getElementById('rom_name_cn_path').value, options,
        });
        batchRunJobId = started.job_id;
        batchRunStage = 'analysis';
        renderWorkbench();
        analysis = await watchCompletionJob(started.job_id,
            workbenchText('第 1 步 / 共 2 步 · 分析（不写入）：', 'Step 1 of 2 · Analyzing (nothing written): '));
        if (!analysis.can_apply) {
            await desktopRequest('/api/batch/discard', {preview_job_id: started.job_id});
            finishBatchRun('completed', analysis, null);
            return;
        }
        const applied = await desktopRequest('/api/batch/apply', {preview_job_id: started.job_id, continue_on_error: true});
        batchRunJobId = applied.job_id;
        batchRunStage = 'apply';
        renderWorkbench();
        const applyResult = await watchCompletionJob(applied.job_id,
            workbenchText('第 2 步 / 共 2 步 · 补全：', 'Step 2 of 2 · Applying: '));
        finishBatchRun('completed', analysis, applyResult);
    } catch (error) {
        if (batchRunStage === 'analysis' && batchRunJobId) {
            try { await desktopRequest('/api/batch/discard', {preview_job_id: batchRunJobId}); } catch (discardError) {}
        }
        finishBatchRun(error.cancelled ? 'cancelled' : 'failed', analysis,
            batchRunStage === 'apply' ? error.result || null : null, error.message);
    } finally {
        batchRunJobId = null;
        batchRunStage = '';
        endWorkbenchOperation();
        refreshAfterCompletion();
    }
}

function finishBatchRun(outcome, analysis, applyResult, errorMessage = '') {
    invalidateWorkbenchPreview();
    const appliedSystems = new Set((applyResult?.playlists || []).map(item => item.system));
    let filledArtwork = 0, manual = 0;
    for (const item of analysis?.rows || []) {
        if (!item.error && appliedSystems.has(item.system)) filledArtwork += item.artwork;
        manual += item.review || 0;
    }
    const completed = applyResult?.applied_count
        ?? (applyResult?.playlists || []).reduce((total, item) => total + (item.applied_count || 0), 0);
    const failedImages = Object.values(applyResult?.download_summary?.types || {})
        .reduce((total, stats) => total + (stats.failed || 0), 0);
    const openTasks = () => openDesktop('tasks');
    if (outcome === 'cancelled') {
        showActionToast({message: analysis
            ? workbenchText('已取消，已完成的部分会保留。', 'Cancelled; completed work is kept.')
            : workbenchText('已取消，未写入任何内容。', 'Cancelled; nothing was written.'),
            receiptId: applyResult?.receipt_id || '', details: openTasks});
    } else if (outcome === 'failed') {
        showActionToast({message: errorMessage || workbenchText('处理失败，请查看任务明细。', 'The run failed; see task details.'),
            details: openTasks});
    } else if (applyResult) {
        let text = workbenchText(`已补全 ${completed} 个游戏`,
            `Completed ${completed} ${completed === 1 ? 'game' : 'games'}`);
        if (failedImages) text += workbenchText(`，${failedImages} 张封面下载失败`, `, ${failedImages} images failed`);
        if (manual) text += workbenchText(`，${manual} 个游戏需手动处理`, `, ${manual} games need manual work`);
        showActionToast({message: text, receiptId: applyResult.receipt_id || '', details: openTasks});
    } else {
        showActionToast({message: workbenchText('没有需要自动补全的内容', 'Nothing needed auto-completion')
            + (manual ? workbenchText(`，${manual} 个游戏需手动处理`, `, ${manual} games need manual work`) : '')});
    }
    if (batchRunCreatedArtworkDir && filledArtwork && currentDeviceScan?.directories) {
        currentDeviceScan.directories.thumbnails_exists = true;
        renderWorkbench();
    }
}

async function applyChanges() {
    if (!workbenchSnapshot().canApply) return;
    const playlistPath = document.getElementById('playlist_path').value;
    const thumbnailsDir = getThumbnailsDirectory();

    if (!currentChanges.length) {
        showStatus('请先生成预览，再应用更改', 'error');
        return;
    }

    const includedChanges = getIncludedChanges();
    if (!includedChanges.length) {
        showStatus(
            currentUILanguage === 'en'
                ? 'No actionable fixes selected.'
                : '没有可应用的修复项，请先补齐中文名或封面源',
            'error'
        );
        return;
    }

    const options = getProcessingOptions();
    if (includedChanges.every(change => currentMatchesWriteName(change))) options.write_names = false;

    if (options.download_thumbnails && !thumbnailsDir) {
        showStatus('请选择缩略图目录', 'error');
        return;
    }

    if (!beginWorkbenchOperation('apply')) return;
    renderWorkbench();
    const applyMessage = options.download_thumbnails ? '正在应用更改并下载封面' : '正在应用更改（跳过下载）';
    showStatus(applyMessage + '...', 'success');

    try {
        const response = await fetch('/api/playlist/apply', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                playlist_path: playlistPath,
                changes: includedChanges.map(change => ({ ...change })),
                thumbnails_dir: thumbnailsDir,
                options
            })
        });

        const data = await response.json();
        if (data.error) throw new Error(data.error);

        if (data.job_id) {
            rememberAppliedChanges(includedChanges, options);
            trackProgress(data.job_id);
        } else {
            throw new Error(data.error || 'Missing job ID');
        }
    } catch (error) {
        alert('Error: ' + error.message);
        endWorkbenchOperation();
    }
}

function buildApplySummary(changes, options) {
    const writeNames = options.write_names !== false;
    const downloadEnabled = options.download_thumbnails !== false;
    return {
        selected: changes.length,
        renamed: writeNames ? changes.filter(change => String(change.new_label || '').trim()
            !== String(change.original_item_label || change.original_label || '').trim()).length : 0,
        downloads: downloadEnabled ? changes.filter(change => needsCoverDownload(change)).length : 0,
        skipped: Math.max(0, currentChanges.length - changes.length),
        writeNames,
        downloadEnabled
    };
}

function formatApplySummaryText(summary) {
    const parts = currentUILanguage === 'en'
        ? [`${summary.selected} selected`, summary.writeNames ? `Rename ${summary.renamed}` : 'Keep current names',
            summary.downloadEnabled ? `Complete artwork for ${summary.downloads} games` : 'Skip artwork']
        : [`已选 ${summary.selected} 项`, summary.writeNames ? `修改名称 ${summary.renamed} 项` : '保留当前名称',
            summary.downloadEnabled ? `为 ${summary.downloads} 个游戏补全图片` : '跳过补图'];
    if (summary.skipped) parts.push(currentUILanguage === 'en' ? `${summary.skipped} skipped` : `跳过 ${summary.skipped} 项`);
    return parts.join(' · ');
}

function trackProgress(jobId, mode = 'single') {
    workbench.jobId = jobId;
    workbench.operation = 'apply';
    renderWorkbench();
    const events = new EventSource(`/api/progress?job_id=${jobId}`);
    events.onmessage = event => {
        const job = JSON.parse(event.data);
        const terminal = ['completed', 'cancelled', 'failed'].includes(job.status);
        if (!terminal && !job.error) {
            workbench.taskMessage = (job.total ? `${job.progress} / ${job.total} · ` : '') + job.message;
            renderWorkbench();
            return;
        }
        events.close();
        if (job.status === 'completed' || job.status === 'cancelled') {
            const outcome = downloadTaskOutcome(job.status, job.result?.download_summary);
            const errors = job.result?.errors || [];
            if (errors.length) {
                outcome.complete = false;
                outcome.message = workbenchText(`${errors.length} 个列表处理失败，请在任务中查看`, `${errors.length} playlists failed; see Tasks`);
            }
            if (mode === 'single' && job.result) applyCompletedJobToPreview(job.result);
            if (job.result?.memory_warning) outcome.message += ' · ' + job.result.memory_warning;
            showStatus(outcome.message, outcome.complete ? (job.result?.memory_warning ? 'info' : 'success') : job.status === 'cancelled' ? 'info' : 'error');
        } else showStatus(job.error || workbenchText('任务失败', 'Task failed'), 'error');
        workbench.jobId = null;
        endWorkbenchOperation();
        if (desktopDialog.open && desktopView === 'tasks') refreshDesktop();
    };
    events.onerror = () => {
        // EventSource reconnects automatically; writes stay locked until a terminal event.
        workbench.taskMessage = workbenchText('进度连接断开，正在重连；可在任务中查看状态。', 'Progress disconnected; reconnecting. Check Tasks for status.');
        renderWorkbench();
    };
}
