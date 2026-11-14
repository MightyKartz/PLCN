/* Apply confirmation, background task progress and download details. */
let lastDownloadSummary = null;
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
        showLogPanel('batch');
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
    workbench.hasTask = true;
    renderWorkbench();
    hideApplySummary();
    const applyMessage = options.download_thumbnails ? '正在应用更改并下载封面' : '正在应用更改（跳过下载）';
    showStatus(applyMessage + '...', 'success');
    showLogPanel('single');
    setInlineProgress(45, '应用中', '正在后台处理', options.download_thumbnails ? '当前：写入 playlist 并准备下载' : '当前：写入 playlist，跳过下载');
    document.getElementById('single-log-view').innerHTML = options.download_thumbnails
        ? '正在后台处理，请稍候...<br>并发下载期间日志会持续更新。<br>'
        : '正在后台处理，请稍候...<br>当前已选择跳过缩略图下载。<br>';

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
        setInlineProgress(0, '失败', '应用更改失败', error.message);
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

function showDownloadDetails(keepDrawerState = true) {
    const content = document.getElementById('download-details-content');
    const rows = [
        ['Boxarts（封面）', 'sum-box-ok', 'sum-box-fail', 'sum-box-skip', 'progress-box-count', 'progress-box-percent'],
        ['Snaps（游戏截图）', 'sum-snap-ok', 'sum-snap-fail', 'sum-snap-skip', 'progress-snap-count', 'progress-snap-percent'],
        ['Titles（标题）', 'sum-title-ok', 'sum-title-fail', 'sum-title-skip', 'progress-title-count', 'progress-title-percent'],
        ['总计', 'sum-total-ok', 'sum-total-fail', 'sum-total-skip', null, null]
    ];

    const summaryHtml = rows.map(([label, okId, failId, skipId, countId, percentId]) => {
        const progress = countId ? `${document.getElementById(countId).textContent} ${document.getElementById(percentId).textContent}` : '汇总';
        return `
            <div class="download-row total">
                <strong>${escapeHtml(label)}</strong>
                <span class="ok">${escapeHtml(document.getElementById(okId).textContent)}</span>
                <span class="fail">${escapeHtml(document.getElementById(failId).textContent)}</span>
                <span>${escapeHtml(document.getElementById(skipId).textContent)}</span>
            </div>
            <div class="timeline-value" style="margin: -4px 0 6px 0;">进度：${escapeHtml(progress)}</div>
        `;
    }).join('');

    const details = lastDownloadSummary?.details || [];
    const detailHtml = details.length
        ? `
            <div class="download-detail-list">
                ${details.slice(-80).map(item => {
                    const statusLabel = item.status === 'success' ? '成功' : item.status === 'skipped' ? '跳过' : '失败';
                    const statusClass = item.status === 'failed' ? 'fail' : 'ok';
                    return `
                        <div class="download-detail-item">
                            <span>${escapeHtml(shortThumbnailType(item.type))}</span>
                            <strong>${escapeHtml(item.game || item.source || '-')}</strong>
                            <span class="${statusClass}">${escapeHtml(statusLabel)}</span>
                            <span></span>
                            <span>${escapeHtml(item.message || '')}</span>
                            <span></span>
                        </div>
                    `;
                }).join('')}
            </div>
        `
        : '<div class="timeline-value" style="margin-top: 12px;">暂无下载明细。完成一次应用后会显示真实结果。</div>';

    content.innerHTML = summaryHtml + detailHtml;

    if (keepDrawerState) toggleDetailsDrawer(true);
}

function trackProgress(jobId, mode = 'single') {
    workbench.jobId = jobId;
    workbench.operation = 'apply';
    workbench.hasTask = true;
    renderWorkbench();
    const eventSource = new EventSource(`/api/progress?job_id=${jobId}`);
    const logView = document.getElementById(mode === 'batch' ? 'batch-log-view' : 'single-log-view');
    const detailSummary = document.getElementById('detail-summary-main');

    eventSource.onmessage = function (event) {
        const data = JSON.parse(event.data);

        if (data.error) {
            if (logView) logView.innerHTML += `<span style="color:red">错误: ${escapeHtml(data.error)}</span><br>`;
            if (detailSummary) detailSummary.textContent = `任务失败：${data.error}`;
            setInlineProgress(0, '失败', '任务失败', data.error);
            eventSource.close();
            workbench.jobId = null; endWorkbenchOperation();
            return;
        }

        if (data.total > 0) {
            const percent = Math.round((data.progress / data.total) * 100);
            setInlineProgress(percent, data.status === 'completed' ? '完成' : '处理中', `${data.progress} / ${data.total}`, data.message || '正在处理');
        }

        if (data.message) {
            if (detailSummary) detailSummary.textContent = data.message;
            if (logView) {
                const timestamp = new Date().toLocaleTimeString();
                logView.innerHTML += `[${timestamp}] ${escapeHtml(data.message)}<br>`;
                logView.scrollTop = logView.scrollHeight;
            }
        }

        if (data.status === 'completed' || data.status === 'cancelled') {
            const outcome = downloadTaskOutcome(data.status, data.result?.download_summary);
            const errors = data.result?.errors || [];
            if (errors.length) {
                outcome.complete = false;
                outcome.label = workbenchText('部分完成', 'Partially completed');
                outcome.message = workbenchText(`${errors.length} 个列表处理失败，请查看任务明细`, `${errors.length} playlists failed; see task details`);
                if (logView) for (const error of errors) logView.innerHTML += `<span class="fail">${escapeHtml(error)}</span><br>`;
            }
            if (logView) logView.innerHTML += `<span style="color:${outcome.complete ? '#58d68d' : '#f5b041'}">${escapeHtml(outcome.message)}</span><br>`;
            eventSource.close();
            lastDownloadSummary = data.result?.download_summary || null;
            if (mode === 'single' && data.result) applyCompletedJobToPreview(data.result);
            setDownloadSummary(lastDownloadSummary);
            showDownloadDetails(false);
            document.getElementById('dock-download-count').textContent = outcome.label;
            document.getElementById('repair-summary-inline').textContent = mode === 'single'
                ? getAppliedSummaryText(data.result?.applied_count || 0)
                : uiText('修复完成');
            if (detailSummary) detailSummary.textContent = outcome.message;
            workbench.applied = outcome.complete;
            workbench.jobId = null; endWorkbenchOperation();
            setInlineProgress(outcome.cancelled ? 0 : 100, outcome.label, outcome.message,
                `${data.result?.applied_count || 0} 项名称已写回 · 图片 ${lastDownloadSummary?.total?.success || 0} 成功 / ${outcome.failed} 失败`);
            if (data.status === 'cancelled') {
                setInlineProgress(0, '已取消', '任务已取消', '已完成的结果会保留，可在任务中重试图片');
                showStatus('任务已取消，已完成的结果会保留', 'info');
            } else showStatus(outcome.message, outcome.complete ? 'success' : 'error');
        } else if (data.status === 'failed') {
            if (logView) logView.innerHTML += `<span style="color:red">失败: ${escapeHtml(data.error)}</span><br>`;
            eventSource.close();
            setInlineProgress(0, '失败', '任务失败', data.error || '未知错误');
            if (detailSummary) detailSummary.textContent = `任务失败：${data.error || '未知错误'}`;
            workbench.jobId = null; endWorkbenchOperation();
        }
    };

    eventSource.onerror = function () {
        console.error('EventSource failed for progress tracking.');
        // EventSource reconnects automatically. Keep write controls locked until a terminal event.
        if (detailSummary) detailSummary.textContent = '连接断开，无法追踪进度。';
        setInlineProgress(0, '断开', '进度连接断开', '当前：请稍后刷新任务状态');
        if (logView) logView.innerHTML += `<span style="color:orange">连接断开，无法追踪进度。</span><br>`;
    };
}

function toggleDetailsDrawer(forceOpen) {
    const drawer = document.getElementById('details-drawer');
    const open = typeof forceOpen === 'boolean' ? forceOpen : !drawer.classList.contains('open');
    drawer.classList.toggle('open', open);
    drawer.setAttribute('aria-hidden', String(!open));
    if (open) showDownloadDetails(false);
}

function showLogPanel(mode) {
    document.getElementById('single-log-container').style.display = mode === 'single' ? 'block' : 'none';
    document.getElementById('batch-log-container').style.display = mode === 'batch' ? 'block' : 'none';
    document.getElementById('log-placeholder').style.display = mode ? 'none' : 'block';
}

function clearLogs() {
    document.getElementById('single-log-view').innerHTML = '';
    document.getElementById('batch-log-view').innerHTML = '';
    showLogPanel(null);
}

function setInlineProgress(percent, label, main, current) {
    const safePercent = Math.max(0, Math.min(100, percent));
    document.getElementById('inline-progress-fill').style.width = safePercent + '%';
    document.getElementById('inline-progress-label').textContent = label;
    document.getElementById('inline-progress-main').textContent = main;
    document.getElementById('inline-progress-current').textContent = current;
}

function setProgressCardTotals(total, completed) {
    const safeTotal = Math.max(0, Number(total) || 0);
    const safeCompleted = Math.max(0, Math.min(safeTotal, Number(completed) || 0));
    const percent = safeTotal ? Math.round((safeCompleted / safeTotal) * 100) : 0;
    ['box', 'snap', 'title'].forEach((key) => {
        document.getElementById(`progress-${key}-count`).textContent = `${safeCompleted} / ${safeTotal}`;
        document.getElementById(`progress-${key}-percent`).textContent = `(${percent}%)`;
    });
}

function setDownloadSummary(summary) {
    const typeMap = [
        ['Named_Boxarts', 'box'],
        ['Named_Snaps', 'snap'],
        ['Named_Titles', 'title']
    ];

    let totalSuccess = 0;
    let totalFailed = 0;
    let totalSkipped = 0;

    typeMap.forEach(([typeName, key]) => {
        const stats = summary?.types?.[typeName] || { success: 0, failed: 0, skipped: 0 };
        const success = Number(stats.success) || 0;
        const failed = Number(stats.failed) || 0;
        const skipped = Number(stats.skipped) || 0;
        const total = success + failed + skipped;
        const completed = success + failed + skipped;
        const percent = total ? Math.round((completed / total) * 100) : 0;

        document.getElementById(`sum-${key}-ok`).textContent = formatDownloadOutcome(success, '成功');
        document.getElementById(`sum-${key}-fail`).textContent = formatDownloadOutcome(failed, '失败');
        document.getElementById(`sum-${key}-skip`).textContent = formatDownloadOutcome(skipped, '跳过');
        document.getElementById(`progress-${key}-count`).textContent = `${completed} / ${total}`;
        document.getElementById(`progress-${key}-percent`).textContent = `(${percent}%)`;

        totalSuccess += success;
        totalFailed += failed;
        totalSkipped += skipped;
    });

    document.getElementById('sum-total-ok').textContent = formatDownloadOutcome(totalSuccess, '成功');
    document.getElementById('sum-total-fail').textContent = formatDownloadOutcome(totalFailed, '失败');
    document.getElementById('sum-total-skip').textContent = formatDownloadOutcome(totalSkipped, '跳过');
}

function formatDownloadOutcome(count, label) {
    return `${count} ${uiText(label)}`;
}
