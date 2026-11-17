/* Desktop management, the native file picker and application startup. */
const desktopDialog = document.getElementById('desktop-dialog');
let desktopPoll = null;
let desktopView = 'library';
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

function desktopButton(parent, text, action, {requiresIdle = false} = {}) {
    const button = desktopElement('button', text, parent);
    button.type = 'button'; button.className = 'btn btn-muted';
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
        button.disabled = Boolean(workbench.operation) || (button.dataset.dataTask === 'true' && desktopDataPending);
        if (workbench.operation) button.title = desktopText('请等待当前操作完成。', 'Wait for the current operation to finish.');
        else button.removeAttribute('title');
    });
}

async function openDesktop(view = 'library') {
    desktopView = view;
    document.getElementById('desktop-message').textContent = '';
    document.querySelectorAll('[data-desktop-view]').forEach(button => {
        button.classList.toggle('active', button.dataset.desktopView === view);
        button.setAttribute('aria-pressed', String(button.dataset.desktopView === view));
    });
    document.getElementById('data-source-settings').hidden = view !== 'data';
    document.getElementById('path-settings').hidden = view !== 'library';
    document.getElementById('preference-settings').hidden = view !== 'preferences';
    document.getElementById('desktop-content').hidden = ['library','preferences'].includes(view);
    document.getElementById('desktop-close').textContent = desktopText(view === 'library' ? '完成' : '关闭', view === 'library' ? 'Done' : 'Close');
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
            document.getElementById('preference-language').value = currentUILanguage;
            document.getElementById('preference-theme').value = currentTheme;
            return;
        }
        if (desktopView === 'library') {
            body.replaceChildren();
            renderWorkbench();
            return;
        }
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
            desktopButton(body, desktopText('检查更新', 'Check updates'), () => desktopDataTask('/api/data/check'), {requiresIdle: true}).dataset.dataTask = 'true';
            desktopButton(body, desktopText('下载并比较', 'Download and compare'), () => desktopDataTask('/api/data/fetch'), {requiresIdle: true}).dataset.dataTask = 'true';
            if (state.can_rollback) desktopButton(body, desktopText('回滚数据源', 'Roll back data'), async () => {
                assertWorkbenchIdle();
                if (!await desktopConfirm(desktopText('恢复上一次名称数据源？人工规则会保留。', 'Restore the previous data source? Manual corrections are preserved.'))) return;
                await desktopRequest('/api/data/rollback', {}); await desktopReloadSource(); await refreshDesktop();
            }, {requiresIdle: true});
            desktopElement('p', desktopText('更新不会自动启用。先检查新增、移除和译名变化，再选择是否启用。', 'Updates are not activated automatically. Review added, removed and renamed entries before activation.'), body);
            for (const pack of state.packs) {
                const entry = desktopElement('div', undefined, body); entry.className = 'desktop-entry';
                desktopElement('strong', `${pack.revision.slice(0, 16)} · ${pack.records} ${desktopText('条', 'records')} · ${pack.untranslated} ${desktopText('未翻译', 'untranslated')}`, entry);
                const packDetails = desktopElement('details', undefined, entry);
                desktopElement('summary', desktopText('数据包路径', 'Pack path'), packDetails);
                desktopElement('p', pack.path, packDetails);
                desktopButton(entry, desktopText('与当前数据比较', 'Compare with active data'), async () => {
                    await desktopDataTask('/api/data/compare', { pack: pack.path });
                }, {requiresIdle: true});
                if (pack.active) desktopElement('span', desktopText('正在使用', 'Active'), entry);
                else desktopButton(entry, desktopText('启用', 'Activate'), async () => {
                    assertWorkbenchIdle();
                    if (!await desktopConfirm(desktopText('启用此数据包并清除当前预览？人工规则会保留。', 'Activate this pack and clear the current preview? Manual corrections are preserved.'))) return;
                    await desktopRequest('/api/data/activate', { pack: pack.path });
                    await desktopReloadSource(); await refreshDesktop();
                }, {requiresIdle: true});
            }
        } else {
            const [state, receiptData] = await Promise.all([desktopRequest('/api/desktop'), desktopRequest('/api/completion/receipts')]);
            if (version !== desktopRenderVersion || !desktopDialog.open) return;
            const expanded = new Set(Array.from(body.querySelectorAll('details[data-task-id][open]'), element => element.dataset.taskId));
            body.replaceChildren();
            desktopElement('h3', desktopText('本次运行的任务', 'Tasks in this session'), body);
            desktopElement('p', desktopText('关闭浏览器不会停止服务。取消在安全步骤边界生效，已完成的结果会保留。', 'Closing the browser does not stop RetroArch Assistant. Cancellation takes effect at safe boundaries and keeps completed work.'), body);
            for (const job of state.jobs) {
                const entry = desktopElement('div', undefined, body); entry.className = 'desktop-entry';
                entry.dataset.jobId = job.id;
                const progress = job.total ? ` · ${job.progress}/${job.total}` : '';
                desktopElement('strong', (job.status === 'completed' && (job.result?.errors?.length || job.result?.download_summary?.total?.failed)
                    ? desktopText('部分完成', 'Partially completed') : desktopJobStatus(job.status)) + progress, entry);
                if (job.result?.applied_count !== undefined) desktopElement('p', desktopText(`已处理 ${job.result.applied_count} 项`, `${job.result.applied_count} items processed`), entry);
                desktopElement('p', job.error || job.message, entry);
                renderTaskDetails(entry, job, expanded.has(job.id));
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
            const receipts = receiptData.receipts || [];
            if (receipts.length) {
                desktopElement('h3', desktopText('最近补全', 'Recent completions'), body);
                for (const receipt of receipts) {
                    const entry = desktopElement('div', undefined, body); entry.className = 'desktop-entry';
                    desktopElement('strong', receipt.label || desktopText('补全', 'Completion'), entry);
                    const counts = receipt.counts || {};
                    const when = receipt.created_at ? new Date(receipt.created_at).toLocaleString() : '';
                    desktopElement('p', `${when} · ${counts.playlists || 0} ${desktopText('个列表', 'playlists')} · ${counts.images || 0} ${desktopText('张图片', 'images')}`, entry);
                    if (receipt.status === 'applied') desktopButton(entry, desktopText('撤销', 'Undo'), () => undoCompletion(receipt.id), {requiresIdle: true});
                    else desktopElement('span', receipt.status === 'partially_undone' ? desktopText('部分撤销', 'Partially undone') : desktopText('已撤销', 'Undone'), entry);
                }
            }
            desktopElement('h3','ROM ZIP 电脑副本',body);
            for(const record of state.rom_storage_operations || []){
                const entry=desktopElement('div',undefined,body);entry.className='desktop-entry';entry.dataset.romStorageOperation=record.id;
                desktopElement('strong',({running:'运行中／中断，请核对',completed:'已完成',failed:'失败',cancelled:'已取消'}[record.status]||record.status)+' · '+record.created_at,entry);
                desktopElement('p','输出目录：'+record.output_directory,entry);
                desktopElement('p','已验证 '+record.results.length+' 个 ZIP；原文件和引用保留，掌机节省空间 0 B',entry);
                for(const result of record.results)desktopElement('p',result.output+' · SHA-256 '+result.sha256,entry);
                if(record.error)desktopElement('p',record.error,entry);
                if(record.results.length)desktopButton(entry,'预览 ZIP 回传／替换',()=>{desktopDialog.close();openRomRelocation({conversion_id:record.id,file_ids:record.results.map(row=>row.id),playlist:record.playlist});});
            }
            desktopElement('h3','目录整理／ZIP 回传与恢复',body);
            for(const record of state.rom_relocations || []){
                const entry=desktopElement('div',undefined,body);entry.className='desktop-entry';entry.dataset.romRelocation=record.id;
                desktopElement('strong',({backing_up:'备份中／中断',completed:'已完成',partial:'部分完成',restoring:'恢复中',restore_pending:'恢复待处理',restored:'已恢复'}[record.status]||record.status)+' · '+record.created_at,entry);
                desktopElement('p',record.playlist+' · '+record.mode,entry);desktopElement('p','电脑备份：'+record.backup_directory,entry);
                desktopElement('p','本次文件净释放：'+storageBytes(record.actual_image_delta_bytes)+'（不含电脑与元数据备份）',entry);
                for(const output of record.restored_retained_outputs||[])desktopElement('p','保留仍有新引用或未能完整检查的输出：'+output.path,entry);
                if(record.error)desktopElement('p',record.error,entry);
                if(record.status!=='restored')desktopButton(entry,'恢复原目录与引用',()=>recoverRomRelocation(record.id,'restore'),{requiresIdle: true});
                if(!['completed','restored'].includes(record.status))desktopButton(entry,'核对后继续整理',()=>recoverRomRelocation(record.id,'resume'),{requiresIdle: true});
                if(record.status==='completed'&&record.mode==='copy')desktopButton(entry,'预览更新引用／移动',()=>{desktopDialog.close();openRomRelocation({operation_id:record.id,file_ids:record.selected_ids,playlist:record.playlist});});
            }
            desktopElement('h3','电脑 CHD 转换',body);
            for(const record of state.chd_operations || []){
                const entry=desktopElement('div',undefined,body);entry.className='desktop-entry';entry.dataset.chdOperation=record.id;
                desktopElement('strong',({running:'运行中／中断，请核对',completed:'已完成',failed:'失败',cancelled:'已取消'}[record.status]||record.status)+' · '+record.created_at,entry);
                desktopElement('p','输出目录：'+record.output_directory,entry);
                desktopElement('p','已验证 '+record.results.length+' 张光盘；原文件保留，启动引用未更新，掌机运行未验收',entry);
                for(const result of record.results)desktopElement('p',result.output+' · SHA-256 '+result.sha256,entry);
                if(record.error)desktopElement('p',record.error,entry);
                if(record.results.length)desktopButton(entry,'预览回传／替换方案',()=>{desktopDialog.close();openChdDeployment(record);});
            }
            desktopElement('h3','CHD 回传与恢复',body);
            for(const record of state.chd_deployments || []){
                const entry=desktopElement('div',undefined,body);entry.className='desktop-entry';entry.dataset.chdDeployment=record.id;
                desktopElement('strong',({backing_up:'备份中／中断',prepared:'已备份',references_verified:'引用已核对',completed:'已完成',partial:'部分完成',restoring:'恢复中／中断',restore_pending:'恢复待处理',restored:'已恢复'}[record.status]||record.status)+' · '+record.created_at,entry);
                desktopElement('p',record.playlist,entry);desktopElement('p','电脑备份：'+record.backup_directory,entry);
                desktopElement('p','模式：'+record.mode+'；执行时核对的镜像净变化：'+storageBytes(record.actual_image_delta_bytes)+'（不含电脑备份与元数据备份）',entry);
                if(record.error)desktopElement('p',record.error,entry);
                desktopElement('p','引用范围：'+record.roots.join('、'),entry);
                for(const output of record.restored_retained_outputs||[])desktopElement('p','恢复时保留仍有引用或未能完整检查的 CHD：'+output.path,entry);
                if(record.status!=='restored')desktopButton(entry,'恢复原镜像与引用',async()=>recoverChdDeployment(record.id,'restore'),{requiresIdle: true});
                if(!['completed','restored'].includes(record.status))desktopButton(entry,'核对后继续',async()=>recoverChdDeployment(record.id,record.status==='restore_pending'||record.status==='restoring'?'restore':'resume'),{requiresIdle: true});
            }
            desktopElement('h3',desktopText('列表与多盘修改记录','Playlist and multi-disc history'),body);
            for(const record of state.m3u_operations || []){
                const entry=desktopElement('div',undefined,body);entry.className='desktop-entry';entry.dataset.m3uOperation=record.id;
                desktopElement('strong',uiText(record.label)+' · '+uiText({prepared:'等待写入',applying:'应用中／中断',applied:'已完成',partial:'部分完成',restoring:'恢复中／中断',restore_pending:'恢复待处理',restored:'已恢复'}[record.status] || record.status),entry);
                desktopElement('p',record.playlist,entry);
                desktopElement('p',record.created_at+' · '+record.id,entry);
                if(record.error)desktopElement('p',record.error,entry);
                if(record.status!=='restored')desktopButton(entry,record.mode.startsWith('game_') ? desktopText('恢复此次列表修改','Restore this playlist change') : '恢复此次多盘修改',async()=>{await recoverM3u(record.id,'restore',record.mode);},{requiresIdle: true});
                if(['partial','applying','prepared'].includes(record.status))desktopButton(entry,'核对后继续操作',async()=>{await recoverM3u(record.id,'resume',record.mode);},{requiresIdle: true});
            }
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
                }, {requiresIdle: true});
            }
            const appDetails = desktopElement('details', undefined, body);
            desktopElement('summary', desktopText('应用数据与日志', 'Application data and logs'), appDetails);
            desktopElement('p', state.data_dir, appDetails);
            desktopButton(appDetails, desktopText('打开数据目录', 'Open data folder'), () => desktopRequest('/api/fs/open', { path: state.data_dir }));
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
    const config = await desktopRequest('/api/config');
    document.getElementById('rom_name_cn_path').value = config.rom_name_cn_path;
    showStatus(desktopText('数据源已切换，请重新预览。', 'Data source changed. Generate a new preview.'), 'success');
}

async function quitDesktop() {
    if (!await desktopConfirm(desktopText('退出 RetroArch 助手本地服务？正在运行的任务会阻止退出。', 'Stop the RetroArch Assistant service? Active tasks will prevent shutdown.'))) return;
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
    await openDesktop('library');
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
    beginLibraryRead('startup', desktopText('正在读取配置与检测设备…', 'Reading settings and discovering devices…'), '', true);
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

let taskPopoverPoll = null;
let taskPopoverVersion = 0;
async function refreshTaskPopover() {
    const panel = document.getElementById('task-popover');
    if (!panel.matches(':popover-open')) return;
    const version = ++taskPopoverVersion;
    const body = document.getElementById('task-popover-content');
    try {
        const [state, history] = await Promise.all([
            desktopRequest('/api/desktop'), desktopRequest('/api/completion/receipts')
        ]);
        if (version !== taskPopoverVersion || !panel.matches(':popover-open')) return;
        const focusedId = body.contains(document.activeElement) ? document.activeElement.id : '';
        body.replaceChildren();
        const jobs = state.jobs || [];
        const active = jobs.filter(job => ['pending', 'running'].includes(job.status));
        const recent = jobs.filter(job => !['pending', 'running'].includes(job.status)).slice(0, 3);
        for (const job of [...active, ...recent]) {
            const row = desktopElement('article', undefined, body); row.className = 'task-popover-entry';
            desktopElement('strong', desktopText(job.title || '任务', job.title || 'Task'), row);
            const status = {pending:['等待中','Pending'], running:['进行中','Running'], completed:['已完成','Completed'], cancelled:['已取消','Cancelled'], failed:['失败','Failed']}[job.status];
            desktopElement('p', status ? desktopText(...status) : job.status, row);
            desktopElement('p', job.error || job.message || '', row);
            const failures = job.result?.errors?.length || 0;
            const failedImages = job.result?.download_summary?.total?.failed || 0;
            if (failures || failedImages) desktopElement('p', desktopText(`${failures} 个列表失败 · ${failedImages} 张图片失败`, `${failures} playlists failed · ${failedImages} images failed`), row);
            if (['pending', 'running'].includes(job.status)) {
                const progress = desktopElement('progress', undefined, row);
                progress.max = job.total || 1; progress.value = job.progress || 0;
                progress.setAttribute('aria-label', desktopText('任务进度', 'Task progress'));
                const cancel = desktopButton(row, desktopText('取消任务', 'Cancel task'), async () => {
                    try {await desktopRequest('/api/jobs/cancel', {job_id:job.id}); await refreshTaskPopover();}
                    catch (error) {desktopElement('p', error.message, row);}
                });
                cancel.id = 'task-popover-cancel-' + job.id;
            }
        }
        if (!jobs.length) desktopElement('p', desktopText('暂无任务。', 'No tasks yet.'), body);
        const receipts = (history.receipts || []).filter(receipt => receipt.status === 'applied').slice(0, 3);
        if (receipts.length) desktopElement('h3', desktopText('最近补全', 'Recent completions'), body);
        for (const receipt of receipts) {
            const row = desktopElement('article', undefined, body); row.className = 'task-popover-entry';
            desktopElement('strong', receipt.label || desktopText('补全', 'Completion'), row);
            const button = desktopButton(row, desktopText('撤销', 'Undo'), () => {
                panel.hidePopover(); return undoCompletion(receipt.id);
            });
            button.id = 'task-popover-undo-' + receipt.id;
            button.disabled = Boolean(workbench.operation);
        }
        if (focusedId) document.getElementById(focusedId)?.focus({preventScroll:true});
    } catch (error) {
        if (version !== taskPopoverVersion || !panel.matches(':popover-open')) return;
        body.replaceChildren();
        desktopElement('p', desktopText('任务读取失败：', 'Could not read tasks: ') + error.message, body);
        desktopButton(body, desktopText('重试', 'Retry'), refreshTaskPopover);
    }
    if (version === taskPopoverVersion && panel.matches(':popover-open')) {
        clearTimeout(taskPopoverPoll);
        taskPopoverPoll = setTimeout(refreshTaskPopover, 2000);
    }
}
document.getElementById('task-popover').addEventListener('toggle', event => {
    clearTimeout(taskPopoverPoll);
    ++taskPopoverVersion;
    if (event.newState === 'open') refreshTaskPopover();
});
