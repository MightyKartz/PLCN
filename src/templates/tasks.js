/* Apply confirmation, background task progress and download details. */
let lastAppliedChangeKeys = new Set();
let lastAppliedDownloadEnabled = true;
let lastAppliedWriteNames = true;

let batchReviewId = null;
let batchReviewJobId = null;

async function openBatchReview() {
    if (workbench.operation) return;
    const dialog = document.getElementById('batch-review-dialog');
    dialog.showModal();
    await refreshBatchReview();
}

async function closeBatchReview() {
    document.getElementById('batch-review-dialog').close();
    try {
        if (batchReviewJobId) await desktopRequest('/api/jobs/cancel', {job_id: batchReviewJobId});
        if (batchReviewId) await desktopRequest('/api/batch/discard', {preview_job_id: batchReviewId});
    } catch (error) {
        showStatus(error.message, 'error');
    } finally {
        batchReviewId = null;
        document.getElementById('batch-review-button').focus();
    }
}

async function refreshBatchReview(control) {
    if (workbench.operation) return;
    const options = {write_names: document.getElementById('batch-write-names').checked,
        download_thumbnails: document.getElementById('batch-download-artwork').checked};
    if (!options.write_names && !options.download_thumbnails) {
        control.checked = true;
        return;
    }
    if (!beginWorkbenchOperation('batch-preview')) return;
    const dialog = document.getElementById('batch-review-dialog');
    const status = document.getElementById('batch-review-status');
    const apply = document.getElementById('batch-review-apply');
    apply.disabled = true;
    document.getElementById('batch-review-rows').replaceChildren();
    const controls = ['batch-write-names', 'batch-download-artwork', 'batch-review-refresh'];
    controls.forEach(id => { document.getElementById(id).disabled = true; });
    status.textContent = workbenchText('正在分析全部主机，不会写入…', 'Analyzing all systems without writing…');
    try {
        if (batchReviewId) await desktopRequest('/api/batch/discard', {preview_job_id: batchReviewId});
        batchReviewId = null;
        const started = await desktopRequest('/api/batch/preview', {
            batch_dir: currentDeviceScan.directories.playlists,
            thumbnails_dir: getThumbnailsDirectory(),
            rom_name_cn_path: document.getElementById('rom_name_cn_path').value, options,
        });
        batchReviewJobId = started.job_id;
        const result = await new Promise((resolve, reject) => {
            const events = new EventSource(`/api/progress?job_id=${started.job_id}`);
            events.onmessage = event => {
                const job = JSON.parse(event.data);
                if (job.status === 'completed') { events.close(); resolve(job.result); }
                else if (job.error || ['failed', 'cancelled'].includes(job.status)) {
                    events.close(); reject(new Error(job.error || workbenchText('分析已取消', 'Analysis cancelled')));
                } else status.textContent = job.message;
            };
            // EventSource reconnects; a transient disconnect must not enable Apply.
        });
        batchReviewId = started.job_id;
        if (!dialog.open) {
            await desktopRequest('/api/batch/discard', {preview_job_id: batchReviewId});
            batchReviewId = null;
            return;
        }
        const rows = document.getElementById('batch-review-rows');
        for (const item of result.rows) {
            const row = document.createElement('tr');
            for (const value of [item.system, item.names, item.artwork, item.error || item.review]) {
                const cell = document.createElement('td'); cell.textContent = value; row.appendChild(cell);
            }
            rows.appendChild(row);
        }
        const count = result.rows.reduce((total, item) => total + item.names + item.artwork, 0);
        status.textContent = result.options.download_thumbnails && !getThumbnailsDirectory()
            ? workbenchText('请先设置图片目录，或取消补全图片后重新分析。', 'Choose an artwork folder, or uncheck artwork to analyze names only.')
            : workbenchText(`共 ${result.rows.length} 个主机 · ${count} 项名称／图片任务，尚未写入。`, `${result.rows.length} systems · ${count} name/artwork actions. Nothing has been written.`);
        apply.disabled = !result.can_apply;
    } catch (error) {
        status.textContent = error.message;
    } finally {
        batchReviewJobId = null;
        controls.forEach(id => { document.getElementById(id).disabled = false; });
        endWorkbenchOperation();
    }
}

async function applyBatchReview() {
    if (!batchReviewId || workbench.operation || document.getElementById('batch-review-apply').disabled) return;
    if (!beginWorkbenchOperation('apply')) return;
    document.getElementById('batch-review-apply').disabled = true;
    try {
        const data = await desktopRequest('/api/batch/apply', {preview_job_id: batchReviewId,
            continue_on_error: document.getElementById('batch-option-continue').checked});
        batchReviewId = null;
        document.getElementById('batch-review-dialog').close();
        invalidateWorkbenchPreview();
        trackProgress(data.job_id, 'batch');
    } catch (error) {
        document.getElementById('batch-review-status').textContent = error.message;
        endWorkbenchOperation();
    }
}

document.getElementById('batch-review-dialog').addEventListener('cancel', event => {
    event.preventDefault(); closeBatchReview();
});

async function applyChanges(confirmed = false) {
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

    if (options.download_thumbnails && !thumbnailsDir) {
        showStatus('请选择缩略图目录', 'error');
        return;
    }

    if (!confirmed) {
        showApplySummary(buildApplySummary(includedChanges, options));
        return;
    }

    if (!beginWorkbenchOperation('apply')) return;
    renderWorkbench();
    hideApplySummary();
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
    const summary = {
        selected: changes.length,
        autoRepair: 0,
        ready: 0,
        completed: 0,
        review: 0,
        duplicate: 0,
        downloads: 0,
        skipped: Math.max(0, currentChanges.length - changes.length),
        writeNames: options.write_names !== false,
        downloadEnabled: options.download_thumbnails !== false
    };

    changes.forEach((change) => {
        const info = getMatchInfo(change);
        if (isAutoRepairKind(info.kind)) summary.autoRepair += 1;
        if (info.kind === 'ready') summary.ready += 1;
        if (info.kind === 'completed') summary.completed += 1;
        if (info.kind === 'review') summary.review += 1;
        if (info.kind === 'duplicate') summary.duplicate += 1;
        if (needsCoverDownload(change, info) && summary.downloadEnabled) summary.downloads += 1;
    });

    return summary;
}

function showApplySummary(summary) {
    const panel = document.getElementById('apply-summary-panel');
    document.getElementById('apply-summary-title').textContent = uiText('准备应用修复');
    document.getElementById('apply-summary-text').textContent = formatApplySummaryText(summary);
    panel.hidden = false;
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    document.getElementById('confirm-apply-button').focus();
}

function cancelApplySummary() {
    hideApplySummary();
    document.getElementById('apply-button').focus();
    showStatus(uiText('已取消应用'), 'info');
}

function hideApplySummary() {
    const panel = document.getElementById('apply-summary-panel');
    if (panel) panel.hidden = true;
}

function formatApplySummaryText(summary) {
    if (currentUILanguage === 'en') {
        const downloadText = summary.downloadEnabled
            ? `${summary.downloads} covers will be downloaded`
            : 'downloads skipped';
        return `${summary.selected} selected: ${summary.autoRepair} auto repair, ${summary.ready} no repair needed, ${summary.completed} completed, ${summary.review} need information, ${summary.duplicate} duplicates, ${summary.skipped} skipped. ${downloadText}.`;
    }
    const downloadText = summary.downloadEnabled
        ? `将下载 ${summary.downloads} 个封面`
        : '跳过下载';
    return `${summary.writeNames ? '将写回游戏列表' : '仅补全图片，保留当前名称'}：${summary.selected} 项已选，${summary.autoRepair} 可自动修复，${summary.ready} 无需修复，${summary.completed} 已完成，${summary.review} 待补充信息，${summary.duplicate} 重复项，${summary.skipped} 项跳过。${downloadText}。`;
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
            showStatus(outcome.message, outcome.complete ? 'success' : job.status === 'cancelled' ? 'info' : 'error');
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
