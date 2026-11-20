/* Apply confirmation, background task progress and download details. */
let lastAppliedChangeKeys = new Set();
let lastAppliedDownloadEnabled = true;
let lastAppliedWriteNames = true;

const completionJobIds = new Set();
let batchRunJobId = null;
let batchRunStage = '';
let batchRunCreatedArtworkDir = false;

let actionToastTimer = null;

function showActionToast({message, details = null}) {
    const toast = document.getElementById('action-toast');
    document.getElementById('action-toast-text').textContent = message;
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
    if (desktopDialog.open && desktopView === 'completion') refreshDesktop();
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

async function retryCompletionArtwork(jobId) {
    if (!beginWorkbenchOperation('apply')) return;
    try {
        const started = await desktopRequest('/api/jobs/retry', {job_id: jobId});
        workbench.jobId = started.job_id;
        completionJobIds.add(workbench.jobId);
        await refreshDesktop();
        await watchCompletionJob(started.job_id, workbenchText('正在重试图片：', 'Retrying artwork: '));
    } finally {
        workbench.jobId = null;
        endWorkbenchOperation();
        refreshAfterCompletion();
    }
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
        const verdict = change => change.completion || {};
        // enabled follows the interactive-preview rules; direct completion
        // applies every game the server verdict marks executable.
        const included = prepared.filter(change => verdict(change).rename || verdict(change).artwork);
        // One game counts once, even when a rename applies while its artwork gap stays manual.
        const needsManual = prepared.filter(change => verdict(change).manual).length;
        const openHistory = () => openOperationHistory('completion');
        if (!included.length) {
            showActionToast({message: workbenchText('没有可自动补全的内容', 'Nothing can be completed automatically')
                + (needsManual ? workbenchText(`，${needsManual} 个游戏需手动处理`, `, ${needsManual} games need manual work`) : ''),
                details: needsManual ? () => previewTask(scope) : openHistory});
            return;
        }
        const applyOptions = {...options};
        if (included.every(change => currentMatchesWriteName(change))) applyOptions.write_names = false;
        const started = await desktopRequest('/api/playlist/apply', {
            playlist_path: playlistPath, changes: included.map(change => {
                // A source the gallery could not verify must not reach the downloader.
                return {...change, thumbnail_source: verdict(change).artwork ? change.thumbnail_source : null};
            }),
            thumbnails_dir: thumbnailsDir, options: applyOptions
        });
        workbench.jobId = started.job_id;
        completionJobIds.add(workbench.jobId);
        renderWorkbench();
        const result = await watchCompletionJob(started.job_id, workbenchText('正在补全：', 'Completing: '));
        const appliedCount = result?.applied_count ?? included.length;
        const failedImages = Object.values(result?.download_summary?.types || {})
            .reduce((total, stats) => total + (stats.failed || 0), 0);
        let message = workbenchText(`已补全 ${appliedCount} 个游戏`, `Completed ${appliedCount} ${appliedCount === 1 ? 'game' : 'games'}`);
        if (failedImages) message += workbenchText(`，${failedImages} 张封面下载失败`, `, ${failedImages} images failed`);
        if (result?.memory_warning) message += ' · ' + result.memory_warning;
        if (result?.cleanup_warnings?.length) message += ' · ' + result.cleanup_warnings.join(' · ');
        if (needsManual) message += workbenchText(`，${needsManual} 个游戏需手动处理`, `, ${needsManual} games need manual work`);
        showActionToast({message,
            details: needsManual ? () => previewTask(scope) : openHistory});
    } catch (error) {
        if (error.cancelled) {
            showActionToast({message: workbenchText('已取消，已完成的部分会保留', 'Cancelled; completed work is kept.'),
                details: () => openOperationHistory('completion')});
        } else {
            showActionToast({message: error.message, details: () => openOperationHistory('completion')});
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
        completionJobIds.add(batchRunJobId);
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
        completionJobIds.add(batchRunJobId);
        batchRunStage = 'apply';
        renderWorkbench();
        const applyResult = await watchCompletionJob(applied.job_id,
            workbenchText('第 2 步 / 共 2 步 · 补全：', 'Step 2 of 2 · Applying: '));
        finishBatchRun(applyResult?.cancelled ? 'cancelled' : 'completed', analysis, applyResult);
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
    const openHistory = () => openOperationHistory('completion');
    if (outcome === 'cancelled') {
        const processed = applyResult?.processed_count, total = applyResult?.total_count;
        let message = processed !== undefined && total !== undefined
            ? workbenchText(`已取消，已处理 ${processed}/${total} 个列表；完成的部分会保留。`, `Cancelled; ${processed}/${total} playlist(s) processed and kept.`)
            : processed
                ? workbenchText(`已取消，已处理 ${processed} 个列表；完成的部分会保留。`, `Cancelled; ${processed} playlist(s) processed and kept.`)
                : analysis
                    ? workbenchText('已取消，已完成的部分会保留。', 'Cancelled; completed work is kept.')
                    : workbenchText('已取消，未写入任何内容。', 'Cancelled; nothing was written.');
        if (applyResult?.cleanup_warnings?.length) message += ' · ' + applyResult.cleanup_warnings.join(' · ');
        showActionToast({message, details: openHistory});
    } else if (outcome === 'failed') {
        showActionToast({message: errorMessage || workbenchText('处理失败，请查看补全记录。', 'The run failed; see completion history.'),
            details: openHistory});
    } else if (applyResult) {
        const processed = applyResult.processed_count, total = applyResult.total_count;
        let text = processed !== undefined && total !== undefined
            ? workbenchText(`已完成 ${processed}/${total} 个列表，补全 ${completed} 个游戏`,
                `Finished ${processed}/${total} playlist(s); completed ${completed} ${completed === 1 ? 'game' : 'games'}`)
            : workbenchText(`已补全 ${completed} 个游戏`,
                `Completed ${completed} ${completed === 1 ? 'game' : 'games'}`);
        const failedPlaylists = applyResult.errors?.length || 0;
        if (failedPlaylists) text += workbenchText(`，${failedPlaylists} 个列表处理失败`, `, ${failedPlaylists} playlists failed`);
        if (failedImages) text += workbenchText(`，${failedImages} 张封面下载失败`, `, ${failedImages} images failed`);
        if (manual) text += workbenchText(`，${manual} 个游戏需手动处理`, `, ${manual} games need manual work`);
        if (applyResult.cleanup_warnings?.length) text += ' · ' + applyResult.cleanup_warnings.join(' · ');
        showActionToast({message: text, details: openHistory});
    } else {
        const failedRows = (analysis?.rows || []).filter(row => row.error);
        let message = workbenchText('没有需要自动补全的内容', 'Nothing needed auto-completion')
            + (manual ? workbenchText(`，${manual} 个游戏需手动处理`, `, ${manual} games need manual work`) : '');
        if (failedRows.length) {
            const failures = failedRows.map(row => `${row.system}：${row.error}`).join('；');
            message += workbenchText(`，${failedRows.length} 个列表分析失败：${failures}`,
                `, ${failedRows.length} ${failedRows.length === 1 ? 'playlist' : 'playlists'} failed to analyze: ${failures}`);
        }
        showActionToast({message});
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
        const data = await desktopRequest('/api/playlist/apply', {
            playlist_path: playlistPath,
            changes: includedChanges.map(change => ({ ...change })),
            thumbnails_dir: thumbnailsDir,
            options
        });
        if (data.error) throw new Error(data.error);

        if (data.job_id) {
            rememberAppliedChanges(includedChanges, options);
            trackProgress(data.job_id);
        } else {
            throw new Error(data.error || 'Missing job ID');
        }
    } catch (error) {
        showStatus(workbenchText('应用失败：', 'Apply failed: ') + error.message, 'error');
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
    completionJobIds.add(jobId);
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
                outcome.message = workbenchText(`${errors.length} 个列表处理失败，请在补全记录中查看`, `${errors.length} playlists failed; see completion history`);
            }
            if (mode === 'single' && job.result) applyCompletedJobToPreview(job.result);
            if (job.result?.memory_warning) outcome.message += ' · ' + job.result.memory_warning;
            if (job.result?.cleanup_warnings?.length) outcome.message += ' · ' + job.result.cleanup_warnings.join(' · ');
            const hasWarning = job.result?.memory_warning || job.result?.cleanup_warnings?.length;
            showStatus(outcome.message, outcome.complete ? (hasWarning ? 'info' : 'success') : job.status === 'cancelled' ? 'info' : 'error');
        } else showStatus(job.error || workbenchText('任务失败', 'Task failed'), 'error');
        workbench.jobId = null;
        endWorkbenchOperation();
        if (desktopDialog.open && desktopView === 'completion') refreshDesktop();
    };
    events.onerror = () => {
        // EventSource reconnects automatically; writes stay locked until a terminal event.
        workbench.taskMessage = workbenchText('进度连接断开，正在重连；可在补全记录中查看状态。', 'Progress disconnected; reconnecting. Check completion history for status.');
        renderWorkbench();
    };
}
