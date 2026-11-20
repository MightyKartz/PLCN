/* Desktop management, the native file picker and application startup. */
const desktopDialog = document.getElementById('desktop-dialog');
let desktopPoll = null;
let desktopView = 'preferences';
let desktopRenderVersion = 0;
const desktopText = (zh, en) => currentUILanguage === 'en' ? en : zh;

function desktopConfirm(message, confirmLabel = desktopText('确认', 'Confirm')) {
    return new Promise(resolve => {
        const dialog = document.createElement('dialog');
        dialog.className = 'desktop-confirm app-dialog';
        const text = desktopElement('p', message, dialog);
        text.id = 'desktop-confirm-message';
        dialog.setAttribute('aria-labelledby', text.id);
        let settled = false;
        const finish = value => {
            if (settled) return;
            settled = true; dialog.close(); dialog.remove(); resolve(value);
        };
        const actions = desktopElement('div', undefined, dialog); actions.className = 'desktop-confirm-actions';
        desktopButton(actions, desktopText('取消', 'Cancel'), () => finish(false));
        desktopButton(actions, confirmLabel, () => finish(true)).classList.remove('btn-muted');
        dialog.addEventListener('cancel', event => { event.preventDefault(); finish(false); });
        document.body.appendChild(dialog); dialog.showModal();
    });
}

async function desktopRequest(path, payload, {signal} = {}) {
    const options = payload === undefined ? {} : {
        method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)
    };
    if (signal) options.signal = signal;
    let response = await fetch(path, options);
    // A 403 is rejected before the handler runs. Renew the local session once;
    // never resubmit a request after a network error or an ambiguous write result.
    if (response.status === 403) {
        const bootstrap = await fetch('/');
        if (bootstrap.ok) response = await fetch(path, options);
    }
    if (!response.headers.get('Content-Type')?.includes('application/json')) {
        throw new Error(desktopText('连接已失效，请重新连接后重试。', 'The connection expired. Reconnect and retry.'));
    }
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || String(response.status));
    return data;
}

async function reconnectGameImport() {
    gmField('reconnect').disabled = true;
    try {
        const response = await fetch('/');
        if (!response.ok) throw new Error(desktopText('无法恢复本地连接。', 'Could not restore the local connection.'));
        await desktopRequest('/api/library/sources');
        if (!gameManagement.setup) {
            await openGameImport();
        } else {
            gmInvalidate(); await previewGameImport();
        }
    } catch (error) {gmStatus(gmError(error), true);}
    finally {gmField('reconnect').disabled = false;}
}

function desktopElement(tag, text, parent) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (parent) parent.appendChild(element);
    return element;
}

function desktopButton(parent, text, action, {requiresIdle = false, icon = null} = {}) {
    const button = desktopElement('button', text, parent);
    button.type = 'button'; button.className = 'btn btn-muted';
    button.setAttribute('aria-label', text);
    if (icon) button.prepend(wbIcon(icon));
    if (requiresIdle) {
        button.dataset.requiresIdle = 'true';
        button.disabled = Boolean(workbench.operation);
    }
    button.onclick = async () => {
        button.disabled = true;
        button.dataset.busy = 'true';
        try { await action(); }
        catch (error) { document.getElementById('desktop-message').textContent = error.message; }
        finally {
            delete button.dataset.busy;
            button.disabled = requiresIdle && Boolean(workbench.operation);
        }
    };
    return button;
}

function syncIdleButtons() {
    document.querySelectorAll('#desktop-dialog [data-requires-idle]').forEach(button => {
        if (button.dataset.busy) return;
        button.disabled = Boolean(workbench.operation);
        button.title = workbench.operation ? desktopText('请等待当前操作完成。', 'Wait for the current operation to finish.') : button.getAttribute('aria-label');
    });
}

function openOperationHistory(kind) {
    return openDesktop(kind);
}

async function openDesktop(view = 'preferences', focusArtworkPath = false) {
    const titles = {
        completion: ['补全记录', 'Completion history'],
        chd: ['CHD 转换与回传记录', 'CHD conversion and transfer history'],
        romStorage: ['目录整理与 ZIP 记录', 'Folder and ZIP history'],
    };
    const historyTitle = titles[view];
    document.getElementById('desktop-title').textContent = historyTitle ? desktopText(...historyTitle) : view === 'library' ? desktopText('目录配置', 'Folder configuration') : desktopText('设置', 'Settings');
    document.getElementById('artwork-directory-settings').hidden = !focusArtworkPath
        && Boolean(currentDeviceScan?.directories?.thumbnails)
        && !document.getElementById('thumbnails_override').value.trim();
    if (desktopView !== view) document.getElementById('desktop-content').replaceChildren();
    desktopView = view;
    document.getElementById('desktop-message').textContent = '';
    document.getElementById('path-settings').hidden = view !== 'library';
    document.getElementById('preference-settings').hidden = view !== 'preferences';
    document.getElementById('desktop-content').hidden = ['library','preferences'].includes(view);
    const closeLabel = desktopText(view === 'library' ? '完成' : '关闭', view === 'library' ? 'Done' : 'Close');
    const closeButton = document.getElementById('desktop-close');
    closeButton.title = closeLabel;
    closeButton.setAttribute('aria-label', closeLabel);
    closeButton.replaceChildren(wbIcon(view === 'library' ? 'circle-check' : 'x'));
    document.querySelector('#desktop-dialog .desktop-footer').hidden = view !== 'preferences';
    if (!desktopDialog.open) desktopDialog.showModal();
    clearTimeout(desktopPoll);
    await refreshDesktop();
}

desktopDialog.addEventListener('close', () => {
    // A queued close from the previous opening must not invalidate the reopened dialog.
    if (desktopDialog.open) return;
    clearTimeout(desktopPoll); desktopRenderVersion++;
});

async function refreshDesktop() {
    if (!desktopDialog.open) return;
    const version = ++desktopRenderVersion;
    const body = document.getElementById('desktop-content');
    try {
        if (desktopView === 'preferences') {
            document.querySelectorAll('#preference-language input').forEach(option => { option.checked = option.value === currentUILanguage; });
            document.querySelectorAll('#preference-theme input').forEach(option => { option.checked = option.value === themePreference; });
            return;
        }
        if (desktopView === 'library') {
            body.replaceChildren();
            renderWorkbench();
            return;
        }
        const state = await desktopRequest('/api/desktop');
        if (version !== desktopRenderVersion || !desktopDialog.open) return;
        const expanded = new Set(Array.from(body.querySelectorAll('details[data-task-id][open]'), element => element.dataset.taskId));
        body.replaceChildren();
        if (desktopView === 'completion') {
            desktopElement('h3', desktopText('本次运行的补全', 'Completions in this session'), body);
            const jobs = state.jobs.filter(job => completionJobIds.has(job.id) || job.result?.download_summary);
            for (const job of jobs) {
                const entry = desktopElement('div', undefined, body); entry.className = 'desktop-entry';
                entry.dataset.jobId = job.id;
                const progress = job.total ? ` · ${job.progress}/${job.total}` + (job.result?.processed_count !== undefined ? desktopText(' 个列表', ' playlists') : '') : '';
                desktopElement('strong', (job.status === 'completed' && (job.result?.errors?.length || job.result?.download_summary?.total?.failed)
                    ? desktopText('部分完成', 'Partially completed') : desktopJobStatus(job.status)) + progress, entry);
                if (job.result?.applied_count !== undefined) desktopElement('p', desktopText(`已处理 ${job.result.applied_count} 个条目`, `${job.result.applied_count} entries processed`), entry);
                desktopElement('p', job.error || job.message, entry);
                renderTaskDetails(entry, job, expanded.has(job.id));
                if (['pending', 'running'].includes(job.status)) {
                    desktopButton(entry, desktopText('取消补全', 'Cancel completion'), async () => {
                        await desktopRequest('/api/jobs/cancel', {job_id: job.id});
                        await refreshDesktop();
                    }, {icon:'square'});
                } else {
                    const result = job.result || {};
                    if (result.revision) desktopElement('p', desktopText('上游版本：', 'Upstream revision: ') + result.revision, entry);
                    if (result.message) desktopElement('p', result.message, entry);
                    for (const warning of result.cleanup_warnings || []) desktopElement('p', warning, entry);
                    if (result.comparison) {
                        const change = result.comparison;
                        desktopElement('p', desktopText(
                            `新增 ${change.added} · 移除 ${change.removed} · 译名变化 ${change.changed} · 未翻译 ${change.untranslated}`,
                            `Added ${change.added} · Removed ${change.removed} · Renamed ${change.changed} · Untranslated ${change.untranslated}`), entry);
                    }
                    const details = result.download_summary?.details || [];
                    const failures = details.filter(row => (row.status === 'failed' || row.reason === 'cancelled') && row.reason !== 'filename_collision');
                    if (failures.length) {
                        desktopElement('p', `${failures.length} ${desktopText('张图片未完成', 'images incomplete')}`, entry);
                        desktopButton(entry, desktopText('重试未完成图片', 'Retry incomplete images'), async () => {
                            await retryCompletionArtwork(job.id);
                        }, {requiresIdle: true, icon:'refresh'});
                    }
                }
            }
            if (!jobs.length) desktopElement('p', desktopText('本次运行暂无补全任务。', 'No completions in this session.'), body);
            clearTimeout(desktopPoll);
            if (jobs.some(job => ['pending', 'running'].includes(job.status))) desktopPoll = setTimeout(refreshDesktop, 2000);
        } else if (desktopView === 'romStorage') {
            if (!state.rom_storage_operations.length)
                desktopElement('p', desktopText('暂无目录整理或 ZIP 记录。', 'No folder or ZIP history yet.'), body);
            desktopElement('h3','ROM ZIP 电脑副本',body);
            for(const record of state.rom_storage_operations || []){
                const entry=desktopElement('div',undefined,body);entry.className='desktop-entry';entry.dataset.romStorageOperation=record.id;
                desktopElement('strong',({running:'运行中／中断，请核对',completed:'已完成',failed:'失败',cancelled:'已取消'}[record.status]||record.status)+' · '+record.created_at,entry);
                desktopElement('p','输出目录：'+record.output_directory,entry);
                desktopElement('p','已验证 '+record.results.length+' 个 ZIP；原文件和引用保留，掌机节省空间 0 B',entry);
                for(const result of record.results)desktopElement('p',result.output+' · SHA-256 '+result.sha256,entry);
                if(record.error)desktopElement('p',record.error,entry);
                if(record.results.length)desktopButton(entry,'预览 ZIP 回传／替换',()=>{desktopDialog.close();closeRomStorage();openRomRelocation({conversion_id:record.id,file_ids:record.results.map(row=>row.id),playlist:record.playlist});},{icon:'eye'});
            }
        } else if (desktopView === 'chd') {
            if (!state.chd_operations.length)
                desktopElement('p', desktopText('暂无 CHD 记录。', 'No CHD history yet.'), body);
            desktopElement('h3','电脑 CHD 转换',body);
            for(const record of state.chd_operations || []){
                const entry=desktopElement('div',undefined,body);entry.className='desktop-entry';entry.dataset.chdOperation=record.id;
                desktopElement('strong',({running:'运行中／中断，请核对',completed:'已完成',failed:'失败',cancelled:'已取消'}[record.status]||record.status)+' · '+record.created_at,entry);
                desktopElement('p','输出目录：'+record.output_directory,entry);
                desktopElement('p','已验证 '+record.results.length+' 张光盘；原文件保留，启动引用未更新，掌机运行未验收',entry);
                for(const result of record.results)desktopElement('p',result.output+' · SHA-256 '+result.sha256,entry);
                if(record.error)desktopElement('p',record.error,entry);
                if(record.results.length)desktopButton(entry,'预览回传／替换方案',()=>{desktopDialog.close();closeStorageOptimization();openChdDeployment(record);},{icon:'eye'});
            }
        }
    } catch (error) { document.getElementById('desktop-message').textContent = error.message; }
    finally { syncIdleButtons(); }
}

function assertWorkbenchIdle() {
    if (workbench.operation) throw new Error(desktopText('请等待当前操作完成。', 'Wait for the current operation to finish.'));
}

function desktopJobStatus(status) {
    const labels = {pending: ['等待中', 'Pending'], running: ['处理中', 'Running'], completed: ['已完成', 'Completed'], failed: ['失败', 'Failed'], cancelled: ['已取消', 'Cancelled']};
    return labels[status] ? desktopText(...labels[status]) : status;
}

function desktopClearPreview() {
    invalidateWorkbenchPreview();
}

async function quitDesktop() {
    if (!await desktopConfirm(desktopText('退出 RetroArch 助手本地服务？正在运行的任务会阻止退出。', 'Stop the RetroArch Assistant service? Active tasks will prevent shutdown.'), desktopText('退出', 'Quit'))) return;
    try {
        await desktopRequest('/api/desktop/shutdown', {});
        document.body.replaceChildren(desktopElement('p', desktopText('RetroArch 助手已退出，可以关闭此页面。', 'RetroArch Assistant has stopped. You may close this page.')));
    } catch (error) { showStatus(error.message, 'error'); }
}

const builtInFilePicker = openFilePicker;
openFilePicker = async function(inputId, directoryMode) {
    const returnFocus = document.activeElement;
    if (!beginWorkbenchOperation('pick')) return;
    showStatus(desktopText('正在打开系统选择器…', 'Opening system picker…'), 'info');
    let selected;
    try {
        selected = await desktopRequest('/api/desktop/pick', { kind: directoryMode ? 'directory' : 'file', initial: document.getElementById(inputId).value });
    } catch (error) {
        endWorkbenchOperation();
        showStatus(desktopText('系统选择器不可用，已切换到内置浏览。', 'System picker unavailable; using the built-in browser.'), 'info');
        builtInFilePicker(inputId, directoryMode, returnFocus);
        return;
    }
    endWorkbenchOperation();
    returnFocus?.focus();
    if (selected.path) { currentTargetInputId = inputId; selectFile(selected.path); }
};

async function openPathSettings(focusId = 'retroarch_root') {
    await openDesktop('library', focusId === 'thumbnails_override');
    document.getElementById(focusId).focus();
}

async function closeDesktopSettings() {
    if (desktopView === 'library' && !workbench.operation) await applyPathSettings();
    else desktopDialog.close();
}

async function initializeDesktop() {
    renderWorkbench();
    await refreshLibrarySources();
}
initializeDisplayPreferences();
async function startDesktop() {
    beginLibraryRead('startup', desktopText('正在读取配置与检测设备…', 'Reading settings and discovering devices…'), '', false);
    await loadConfig();
    await initializeDesktop();
    finishLibraryRead('startup', libraryHome.error);
}
startDesktop().catch(error => finishLibraryRead('startup', error.message));

function renderTaskDetails(parent, job, expanded) {
    const result = job.result || {};
    const details = desktopElement('details', undefined, parent);
    details.dataset.taskId = job.id;
    details.open = expanded;
    desktopElement('summary', desktopText('任务明细', 'Task details'), details);
    if (job.messages?.length) {
        desktopElement('h4', desktopText('最近的处理记录', 'Recent activity'), details);
        const log = desktopElement('ol', undefined, details); log.className = 'task-log';
        for (const message of job.messages) desktopElement('li', message, log);
    }
    if (result.errors?.length) {
        const errors = desktopElement('ul', undefined, details); errors.className = 'task-errors';
        for (const error of result.errors) desktopElement('li', error, errors);
    }
    const summary = result.download_summary;
    if (summary) {
        desktopElement('h4', desktopText('图片处理汇总', 'Artwork summary'), details);
        const table = desktopElement('table', undefined, details); table.className = 'task-result-table';
        const heading = desktopElement('tr', undefined, table);
        for (const text of [desktopText('类型', 'Type'), desktopText('成功', 'Succeeded'), desktopText('失败', 'Failed'), desktopText('跳过', 'Skipped')]) desktopElement('th', text, heading);
        for (const [kind, name] of Object.entries(ARTWORK_KIND_LABELS)) {
            const row = desktopElement('tr', undefined, table);
            desktopElement('td', desktopText(...name), row);
            for (const key of ['success', 'failed', 'skipped']) desktopElement('td', summary.types?.[kind]?.[key] || 0, row);
        }
        const images = summary.details || [];
        const failures = images.filter(image => image.status === 'failed' || image.reason === 'cancelled');
        const visible = failures.length ? failures : images.slice(-200);
        if (visible.length) {
            desktopElement('h4', failures.length ? desktopText('未完成的图片', 'Incomplete images')
                : desktopText(`图片明细（最近 ${visible.length} / ${images.length} 条）`, `Image details (latest ${visible.length} / ${images.length})`), details);
            const list = desktopElement('ul', undefined, details); list.className = 'task-receipts';
            for (const image of visible) {
                const label = artworkKindLabel(image.type);
                const status = {success: ['成功', 'Succeeded'], failed: ['失败', 'Failed'], skipped: ['跳过', 'Skipped']}[image.status];
                desktopElement('li', [image.game || image.source, label, status ? desktopText(...status) : '', image.message].filter(Boolean).join(' · '), list);
            }
        }
    }
    for (const playlist of result.playlists || [result]) {
        const records = [...(playlist.apply?.skipped || []), ...(playlist.download_summary?.writeback?.failed || [])];
        if (records.length) {
            desktopElement('h4', desktopText('未应用的名称变更', 'Name changes not applied'), details);
            const list = desktopElement('ul', undefined, details); list.className = 'task-errors';
            for (const record of records) desktopElement('li', [playlist.system, record.new_label || record.old_label || record.path,
                record.reason === 'stale_proposal' ? desktopText('列表已变化，请重新预览', 'Playlist changed; preview again') : record.reason].filter(Boolean).join(' · '), list);
        }
    }
}
