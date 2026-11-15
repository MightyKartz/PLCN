/* Apply confirmation, background task progress and download details. */
let lastAppliedChangeKeys = new Set();
let lastAppliedDownloadEnabled = true;
let lastAppliedWriteNames = true;

let batchRunJobId = null;
let batchRunStage = '';
let batchRunCreatedArtworkDir = false;

function startCompletion() {
    return document.getElementById('playlist_path').value ? previewTask() : runAllSystemsCompletion();
}

function setBatchRunRunning(running) {
    document.getElementById('batch-run-close').hidden = running;
    document.getElementById('batch-run-cancel').hidden = !running;
    document.getElementById('batch-run-progress').hidden = !running;
    document.getElementById('batch-run-tasks').hidden = running;
    document.getElementById('batch-run-done').hidden = running;
}

function watchBatchRunJob(jobId, prefix) {
    const status = document.getElementById('batch-review-status');
    const progress = document.getElementById('batch-run-progress');
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
                status.textContent = prefix + (job.message || '');
                if (job.total) {
                    progress.max = job.total;
                    progress.value = job.progress || 0;
                } else {
                    progress.removeAttribute('value');
                    progress.removeAttribute('max');
                }
            }
        };
        // EventSource reconnects; a transient disconnect must not advance the run.
    });
}

async function runAllSystemsCompletion(options = {write_names: true, download_thumbnails: true}) {
    if (workbench.operation || !currentDeviceScan?.directories?.playlists) return;
    if (!beginWorkbenchOperation('apply')) return;
    const dialog = document.getElementById('batch-review-dialog');
    const status = document.getElementById('batch-review-status');
    const progress = document.getElementById('batch-run-progress');
    const wrap = dialog.querySelector('.batch-review-table-wrap');
    batchRunStage = '';
    batchRunCreatedArtworkDir = currentDeviceScan?.directories?.thumbnails_exists === false
        && !document.getElementById('thumbnails_override').value.trim();
    document.getElementById('batch-review-rows').replaceChildren();
    document.getElementById('batch-review-title').textContent = workbenchText('一键补全 · 全部主机', 'Auto-complete · All systems');
    status.dataset.state = '';
    status.textContent = workbenchText('第 1 步 / 共 2 步 · 分析（不写入）：', 'Step 1 of 2 · Analyzing (nothing written): ');
    document.getElementById('batch-run-note').textContent = workbenchText('写入前请先退出 RetroArch。修改名称前会自动备份游戏列表。',
        'Quit RetroArch before writing. Playlists are backed up before names change.');
    progress.removeAttribute('value');
    progress.removeAttribute('max');
    wrap.hidden = true;
    setBatchRunRunning(true);
    dialog.showModal();
    let analysis = null;
    try {
        const started = await desktopRequest('/api/batch/preview', {
            batch_dir: currentDeviceScan.directories.playlists,
            thumbnails_dir: getThumbnailsDirectory(),
            rom_name_cn_path: document.getElementById('rom_name_cn_path').value, options,
        });
        batchRunJobId = started.job_id;
        batchRunStage = 'analysis';
        analysis = await watchBatchRunJob(started.job_id,
            workbenchText('第 1 步 / 共 2 步 · 分析（不写入）：', 'Step 1 of 2 · Analyzing (nothing written): '));
        if (!analysis.can_apply) {
            await desktopRequest('/api/batch/discard', {preview_job_id: started.job_id});
            finishBatchRun('completed', analysis, null);
            return;
        }
        const applied = await desktopRequest('/api/batch/apply', {preview_job_id: started.job_id, continue_on_error: true});
        batchRunJobId = applied.job_id;
        batchRunStage = 'apply';
        const applyResult = await watchBatchRunJob(applied.job_id,
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
    }
}

function finishBatchRun(outcome, analysis, applyResult, errorMessage = '') {
    const dialog = document.getElementById('batch-review-dialog');
    const status = document.getElementById('batch-review-status');
    const wrap = dialog.querySelector('.batch-review-table-wrap');
    document.getElementById('batch-review-title').textContent = outcome === 'completed'
        ? workbenchText('补全完成', 'Completed')
        : outcome === 'cancelled' ? workbenchText('补全已取消', 'Cancelled')
        : workbenchText('补全未完成', 'Finished with problems');
    status.dataset.state = outcome === 'completed' ? '' : 'blocked';
    const appliedSystems = new Set((applyResult?.playlists || []).map(item => item.system));
    const applyErrors = {};
    for (const entry of applyResult?.errors || []) {
        const separator = entry.indexOf(': ');
        if (separator > 0) applyErrors[entry.slice(0, separator)] = entry.slice(separator + 2);
    }
    let changedNames = 0, filledArtwork = 0, manual = 0;
    const rows = document.getElementById('batch-review-rows');
    rows.replaceChildren();
    for (const item of analysis?.rows || []) {
        let resultText;
        if (item.error) resultText = item.error;
        else if (appliedSystems.has(item.system)) {
            resultText = workbenchText('已完成', 'Done');
            changedNames += item.names;
            filledArtwork += item.artwork;
        } else if (applyErrors[item.system]) resultText = applyErrors[item.system];
        else if (!item.names && !item.artwork) resultText = workbenchText('无需处理', 'Nothing to do');
        else resultText = workbenchText('未处理', 'Not processed');
        manual += item.review || 0;
        const row = document.createElement('tr');
        for (const value of [item.system, item.names, item.artwork, item.review, resultText]) {
            const cell = document.createElement('td');
            cell.textContent = value;
            row.appendChild(cell);
        }
        rows.appendChild(row);
    }
    wrap.hidden = !rows.children.length;
    const failedImages = Object.values(applyResult?.download_summary?.types || {})
        .reduce((total, stats) => total + (stats.failed || 0), 0);
    const reviewSentence = manual ? workbenchText(` ${manual} 个游戏需手动处理：选择对应主机后在游戏行中补图。`,
        ` ${manual} games need manual work: pick a system and use the game-row artwork dialog.`) : '';
    if (outcome === 'cancelled') {
        status.textContent = analysis
            ? workbenchText('已取消，已完成的部分会保留。', 'Cancelled; completed work is kept.')
            : workbenchText('已取消，未写入任何内容。', 'Cancelled; nothing was written.');
    } else if (outcome === 'failed') {
        status.textContent = errorMessage || workbenchText('处理失败，请查看任务明细。', 'The run failed; see task details.');
    } else if (applyResult) {
        let text = workbenchText(`已修改 ${changedNames} 个名称，为 ${filledArtwork} 个游戏补全图片。`,
            `Renamed ${changedNames} and completed artwork for ${filledArtwork} games.`);
        if (failedImages) text += workbenchText(` ${failedImages} 张图片下载失败，可在任务明细中重试。`,
            ` ${failedImages} images failed; retry them in task details.`);
        text += reviewSentence;
        if (batchRunCreatedArtworkDir && filledArtwork) {
            text += workbenchText(` 图片保存在 ${getThumbnailsDirectory()}。`, ` Artwork saved to ${getThumbnailsDirectory()}.`);
        }
        status.textContent = text;
    } else {
        status.textContent = workbenchText('没有需要自动补全的内容。', 'Nothing needed auto-completion.') + reviewSentence;
    }
    document.getElementById('batch-run-note').textContent = '';
    setBatchRunRunning(false);
    document.getElementById('batch-run-done').focus();
    invalidateWorkbenchPreview();
    if (batchRunCreatedArtworkDir && filledArtwork && currentDeviceScan?.directories) {
        currentDeviceScan.directories.thumbnails_exists = true;
        renderWorkbench();
    }
}

async function cancelBatchRun() {
    const jobId = batchRunJobId;
    if (!jobId) return;
    try {
        await desktopRequest('/api/jobs/cancel', {job_id: jobId});
    } catch (error) {
        showStatus(error.message, 'error');
    }
}

function closeBatchRun() {
    if (workbench.operation) return;
    document.getElementById('batch-review-dialog').close();
}

async function showBatchRunTasks() {
    if (workbench.operation) return;
    document.getElementById('batch-review-dialog').close();
    await openDesktop('tasks');
}

document.getElementById('batch-review-dialog').addEventListener('cancel', event => {
    if (workbench.operation) {
        event.preventDefault();
        cancelBatchRun();
    }
});
document.getElementById('batch-review-dialog').addEventListener('close', () => {
    if (!workbench.operation) document.getElementById('preview-button').focus();
});

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
