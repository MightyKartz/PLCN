/* Desktop workflow, kept outside the legacy workbench script. */
const desktopDialog = document.getElementById('desktop-dialog');
let desktopPoll = null;
let desktopView = 'data';
let desktopDataJobId = null;
let desktopDataPending = false;
let desktopRenderVersion = 0;
const desktopText = (zh, en) => currentUILanguage === 'en' ? en : zh;

function desktopConfirm(message) {
    return new Promise(resolve => {
        const dialog = document.createElement('dialog');
        dialog.className = 'desktop-confirm';
        const text = desktopElement('p', message, dialog);
        text.id = 'desktop-confirm-message';
        dialog.setAttribute('aria-labelledby', text.id);
        let settled = false;
        const finish = value => {
            if (settled) return;
            settled = true; dialog.close(); dialog.remove(); resolve(value);
        };
        desktopButton(dialog, desktopText('取消', 'Cancel'), () => finish(false));
        desktopButton(dialog, desktopText('确认', 'Confirm'), () => finish(true));
        dialog.addEventListener('cancel', event => { event.preventDefault(); finish(false); });
        document.body.appendChild(dialog); dialog.showModal();
    });
}

async function desktopRequest(path, payload) {
    const response = await fetch(path, payload === undefined ? {} : {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || String(response.status));
    return data;
}

function desktopElement(tag, text, parent) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (parent) parent.appendChild(element);
    return element;
}

function desktopButton(parent, text, action) {
    const button = desktopElement('button', text, parent);
    button.type = 'button'; button.className = 'btn btn-muted';
    button.onclick = async () => {
        button.disabled = true;
        try { await action(); }
        catch (error) { document.getElementById('desktop-message').textContent = error.message; }
        finally { button.disabled = false; }
    };
    return button;
}

async function openDesktop(view = 'data') {
    desktopView = view;
    document.getElementById('tools-menu').open = false;
    document.getElementById('desktop-message').textContent = '';
    document.querySelectorAll('[data-desktop-view]').forEach(button => {
        button.classList.toggle('active', button.dataset.desktopView === view);
        button.setAttribute('aria-pressed', String(button.dataset.desktopView === view));
    });
    document.getElementById('data-source-settings').hidden = view !== 'data';
    if (!desktopDialog.open) desktopDialog.showModal();
    clearTimeout(desktopPoll);
    await refreshDesktop();
}

desktopDialog.addEventListener('close', () => { clearTimeout(desktopPoll); desktopRenderVersion++; });

async function refreshDesktop() {
    if (!desktopDialog.open) return;
    const version = ++desktopRenderVersion;
    const body = document.getElementById('desktop-content');
    try {
        if (desktopView === 'data') {
            const state = await desktopRequest('/api/data');
            if (version !== desktopRenderVersion || !desktopDialog.open) return;
            body.replaceChildren();
            desktopElement('h3', desktopText('名称数据库', 'Name database'), body);
            desktopElement('strong', state.source_kind === 'bundled' ? desktopText('内置名称库 · 可离线使用', 'Bundled names · available offline') : state.active ? desktopText('已启用数据包 · 可离线使用', 'Active data pack · available offline') : desktopText('自定义名称库', 'Custom name database'), body);
            const sourceDetails = desktopElement('details', undefined, body);
            desktopElement('summary', desktopText('查看来源路径', 'Show source path'), sourceDetails);
            desktopElement('p', state.source, sourceDetails);
            desktopElement('p', state.active ? `${state.active.revision} · ${state.active.created_at}` : desktopText('使用内置或自定义 CSV；可以完全离线使用。', 'Bundled or custom CSV data; available offline.'), body);
            if (desktopDataJobId) await renderDataTask(body, version);
            if (version !== desktopRenderVersion || !desktopDialog.open) return;
            desktopButton(body, desktopText('检查更新', 'Check updates'), () => desktopDataTask('/api/data/check')).disabled = desktopDataPending || Boolean(workbench.operation);
            desktopButton(body, desktopText('下载并比较', 'Download and compare'), () => desktopDataTask('/api/data/fetch')).disabled = desktopDataPending || Boolean(workbench.operation);
            if (state.can_rollback) desktopButton(body, desktopText('回滚数据源', 'Roll back data'), async () => {
                assertWorkbenchIdle();
                if (!await desktopConfirm(desktopText('恢复上一次名称数据源？人工规则会保留。', 'Restore the previous data source? Manual corrections are preserved.'))) return;
                await desktopRequest('/api/data/rollback', {}); await desktopReloadSource(); await refreshDesktop();
            });
            desktopElement('p', desktopText('更新不会自动启用。先检查新增、移除和译名变化，再选择是否启用。', 'Updates are not activated automatically. Review added, removed and renamed entries before activation.'), body);
            for (const pack of state.packs) {
                const entry = desktopElement('div', undefined, body); entry.className = 'desktop-entry';
                desktopElement('strong', `${pack.revision.slice(0, 16)} · ${pack.records} ${desktopText('条', 'records')} · ${pack.untranslated} ${desktopText('未翻译', 'untranslated')}`, entry);
                const packDetails = desktopElement('details', undefined, entry);
                desktopElement('summary', desktopText('数据包路径', 'Pack path'), packDetails);
                desktopElement('p', pack.path, packDetails);
                desktopButton(entry, desktopText('与当前数据比较', 'Compare with active data'), async () => {
                    await desktopDataTask('/api/data/compare', { pack: pack.path });
                });
                if (pack.active) desktopElement('span', desktopText('正在使用', 'Active'), entry);
                else desktopButton(entry, desktopText('启用', 'Activate'), async () => {
                    assertWorkbenchIdle();
                    if (!await desktopConfirm(desktopText('启用此数据包并清除当前预览？人工规则会保留。', 'Activate this pack and clear the current preview? Manual corrections are preserved.'))) return;
                    await desktopRequest('/api/data/activate', { pack: pack.path });
                    await desktopReloadSource(); await refreshDesktop();
                });
            }
        } else {
            const state = await desktopRequest('/api/desktop');
            if (version !== desktopRenderVersion || !desktopDialog.open) return;
            body.replaceChildren();
            if (desktopView === 'history') {
                desktopElement('h3', desktopText('本地列表恢复', 'Restore local playlists'), body);
                desktopElement('p', desktopText('恢复会先检查文件是否变化，并保留恢复前备份。ADB 备份位于设备上，请手动恢复。', 'Restore checks for external changes and backs up the current file. ADB backups remain on the device for manual recovery.'), body);
                if (!state.history.length) desktopElement('p', desktopText('完成一次名称写回后，这里会显示备份记录。', 'Backup history appears after writing playlist names.'), body);
                for (const record of state.history) {
                    const entry = desktopElement('div', undefined, body); entry.className = 'desktop-entry';
                    desktopElement('strong', record.playlist, entry);
                    desktopElement('p', `${record.created_at} · ${record.applied_count} ${desktopText('项', 'items')}`, entry);
                    desktopElement('p', desktopText('备份：', 'Backup: ') + record.backup, entry);
                    if (record.restored_at) desktopElement('span', desktopText('已恢复', 'Restored'), entry);
                    else desktopButton(entry, desktopText('恢复此次修改', 'Restore this change'), async () => {
                        assertWorkbenchIdle();
                        if (!await desktopConfirm(desktopText('恢复此列表到修复前状态？当前文件也会先备份。', 'Restore the playlist to its previous state? The current file will be backed up.'))) return;
                        await desktopRequest('/api/history/restore', { id: record.id });
                        desktopClearPreview(); await refreshDesktop();
                    });
                }
            } else {
                desktopElement('h3', desktopText('本次运行的任务', 'Tasks in this session'), body);
                desktopElement('p', desktopText('关闭浏览器不会停止服务。取消在安全步骤边界生效，已完成的结果会保留。', 'Closing the browser does not stop PLCN. Cancellation takes effect at safe boundaries and keeps completed work.'), body);
                for (const job of state.jobs) {
                    const entry = desktopElement('div', undefined, body); entry.className = 'desktop-entry';
                    const progress = job.total ? ` · ${job.progress}/${job.total}` : '';
                    desktopElement('strong', desktopJobStatus(job.status) + progress, entry);
                    if (job.result?.applied_count !== undefined) desktopElement('p', desktopText(`已处理 ${job.result.applied_count} 项`, `${job.result.applied_count} items processed`), entry);
                    desktopElement('p', job.error || job.message, entry);
                    if (['pending', 'running'].includes(job.status)) desktopButton(entry, desktopText('取消任务', 'Cancel task'), async () => {
                        await desktopRequest('/api/jobs/cancel', { job_id: job.id }); await refreshDesktop();
                    });
                    else {
                        const result = job.result || {};
                        if (result.revision) desktopElement('p', desktopText('上游版本：', 'Upstream revision: ') + result.revision, entry);
                        if (result.message) desktopElement('p', result.message, entry);
                        if (result.comparison) {
                            const change = result.comparison;
                            desktopElement('p', desktopText(
                                `新增 ${change.added} · 移除 ${change.removed} · 译名变化 ${change.changed} · 未翻译 ${change.untranslated}`,
                                `Added ${change.added} · Removed ${change.removed} · Renamed ${change.changed} · Untranslated ${change.untranslated}`), entry);
                        }
                        const details = result.download_summary?.details || [];
                        const failures = details.filter(row => row.status === 'failed' || row.reason === 'cancelled');
                        if (failures.length) {
                            desktopElement('p', `${failures.length} ${desktopText('张图片未完成', 'images incomplete')}`, entry);
                            desktopButton(entry, desktopText('重试未完成图片', 'Retry incomplete images'), async () => {
                                await desktopRequest('/api/jobs/retry', { job_id: job.id }); await refreshDesktop();
                            });
                        }
                    }
                }
                if (!state.jobs.length) desktopElement('p', desktopText('暂无任务。', 'No tasks yet.'), body);
                clearTimeout(desktopPoll);
                if (state.active_jobs) desktopPoll = setTimeout(refreshDesktop, 2000);
            }
            const appDetails = desktopElement('details', undefined, body);
            desktopElement('summary', desktopText('应用数据与日志', 'Application data and logs'), appDetails);
            desktopElement('p', state.data_dir, appDetails);
            desktopButton(appDetails, desktopText('打开数据目录', 'Open data folder'), () => desktopRequest('/api/fs/open', { path: state.data_dir }));
        }
    } catch (error) { document.getElementById('desktop-message').textContent = error.message; }
}

function assertWorkbenchIdle() {
    if (workbench.operation) throw new Error(desktopText('请等待当前操作完成。', 'Wait for the current operation to finish.'));
}

function desktopJobStatus(status) {
    const labels = {pending: ['等待中', 'Pending'], running: ['处理中', 'Running'], completed: ['已完成', 'Completed'], failed: ['失败', 'Failed'], cancelled: ['已取消', 'Cancelled']};
    return labels[status] ? desktopText(...labels[status]) : status;
}

async function renderDataTask(body, version) {
    const state = await desktopRequest('/api/desktop');
    if (version !== desktopRenderVersion || !desktopDialog.open) return;
    const job = state.jobs.find(job => job.id === desktopDataJobId);
    desktopDataPending = job && ['pending', 'running'].includes(job.status);
    if (!job) return;
    const entry = desktopElement('section', undefined, body); entry.className = 'desktop-entry';
    entry.setAttribute('aria-live', 'polite');
    desktopElement('strong', desktopJobStatus(job.status), entry);
    desktopElement('p', job.error || job.message, entry);
    const result = job.result || {};
    if (result.revision) desktopElement('p', desktopText('上游版本：', 'Upstream revision: ') + result.revision.slice(0, 12), entry);
    if (result.comparison) {
        const c = result.comparison;
        desktopElement('p', desktopText(`新增 ${c.added} · 移除 ${c.removed} · 译名变化 ${c.changed} · 未翻译 ${c.untranslated}`, `Added ${c.added} · Removed ${c.removed} · Renamed ${c.changed} · Untranslated ${c.untranslated}`), entry);
    }
    clearTimeout(desktopPoll);
    if (['pending', 'running'].includes(job.status)) {
        desktopButton(entry, desktopText('取消任务', 'Cancel task'), async () => {
            await desktopRequest('/api/jobs/cancel', {job_id: job.id}); await refreshDesktop();
        });
        desktopPoll = setTimeout(refreshDesktop, 2000);
    }
}

async function desktopDataTask(route, payload = {}) {
    assertWorkbenchIdle();
    if (desktopDataPending) return;
    desktopDataPending = true;
    try {
        const data = await desktopRequest(route, payload);
        desktopDataJobId = data.job_id;
        await openDesktop('data');
    } catch (error) { desktopDataPending = false; throw error; }
}

function desktopClearPreview() {
    invalidateWorkbenchPreview();
}

async function desktopReloadSource() {
    desktopClearPreview();
    const selectedSystem = document.getElementById('system_name').value;
    const config = await desktopRequest('/api/config');
    for (const id of ['rom_name_cn_path', 'batch_rom_name_cn_path']) document.getElementById(id).value = config.rom_name_cn_path;
    await loadSystems();
    if (selectedSystem) { ensureSystemOption(selectedSystem); document.getElementById('system_name').value = selectedSystem; }
    await loadStats();
    showStatus(desktopText('数据源已切换，请重新预览。', 'Data source changed. Generate a new preview.'), 'success');
}

async function quitDesktop() {
    if (!await desktopConfirm(desktopText('退出 PLCN 本地服务？正在运行的任务会阻止退出。', 'Stop the PLCN service? Active tasks will prevent shutdown.'))) return;
    try {
        await desktopRequest('/api/desktop/shutdown', {});
        document.body.replaceChildren(desktopElement('p', desktopText('PLCN 已退出，可以关闭此页面。', 'PLCN has stopped. You may close this page.')));
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

function setRepairMode() {
    hideApplySummary();
    if (currentChanges.length) {
        desktopClearPreview();
        showStatus(desktopText('操作类型已改变，请重新预览。', 'Operation changed. Generate a new preview.'), 'info');
    }
    renderWorkbench();
}

function openPathSettings() {
    document.getElementById('tools-menu').open = false;
    document.getElementById('path-settings').showModal();
    renderWorkbench();
}

async function initializeDesktop() {
    renderWorkbench();
    await refreshLibrarySources();
}
initializeDisplayPreferences();
loadSystems().then(loadConfig).then(initializeDesktop);
