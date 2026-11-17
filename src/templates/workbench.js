/* Real-data library workbench. Artwork and job state are read-only projections. */
const workbenchOverview = {key: '', data: null, error: '', scope: 'all', loading: false, job: null, receipt: '', activeJobs: 0, taskError: false};
const libraryRead = {owner:'', stage:'', root:'', readyRoot:'', blocking:false, error:'', retry:'', focus:null};
function beginLibraryRead(owner, stage, root = '', blocking = libraryRead.readyRoot !== root) {
    Object.assign(libraryRead, {owner, stage, root, blocking, error:'', retry:owner});
    renderLibraryRead();
}
function finishLibraryRead(owner, error = '') {
    if (libraryRead.owner !== owner) return;
    libraryRead.owner = ''; libraryRead.error = error;
    if (!error && owner === 'overview') libraryRead.readyRoot = libraryRead.root;
    renderLibraryRead();
}
function renderLibraryRead() {
    const dialog = document.getElementById('library-read-dialog');
    const active = Boolean(libraryRead.owner || libraryRead.error);
    const failed = Boolean(libraryRead.error);
    const title = workbenchText(failed ? '游戏库读取失败' : '正在读取游戏库', failed ? 'Could not load library' : 'Loading your library');
    const message = failed ? libraryRead.error : libraryRead.stage;
    document.getElementById('library-read-title').textContent = title;
    document.getElementById('library-read-message').textContent = message;
    document.getElementById('library-read-spinner').hidden = failed;
    document.getElementById('library-read-actions').hidden = !failed;
    document.getElementById('library-read-note').textContent = workbenchText(failed ? '检查掌机连接后重试，或选择其他游戏库。' : '首次读取掌机可能需要一些时间，请保持连接。', failed ? 'Check the connection and retry, or choose another library.' : 'The first read may take a moment. Keep your device connected.');
    for (const [id,zh,en] of [['library-read-retry','重新读取','Retry'],['library-read-switch','切换设备','Switch device'],['library-read-banner-retry','重试','Retry']]) document.getElementById(id).textContent = workbenchText(zh,en);
    if (active && libraryRead.blocking) {
        if (!dialog.open) {libraryRead.focus = document.activeElement; dialog.showModal();}
        if (failed) document.getElementById('library-read-retry').focus();
    } else if (dialog.open) {
        dialog.close();
        if (libraryRead.focus?.isConnected) libraryRead.focus.focus();
    }
    document.getElementById('library-read-banner').hidden = !active || libraryRead.blocking;
    document.querySelector('#library-read-banner .library-read-spinner').hidden = failed;
    document.getElementById('library-read-banner-message').textContent = message;
    document.getElementById('library-read-banner-retry').hidden = !failed;
    document.querySelector('.app-shell').setAttribute('aria-busy', String(Boolean(libraryRead.owner)));
}
function retryLibraryRead() {
    if (libraryRead.retry === 'startup') return startDesktop();
    if (libraryRead.retry === 'overview') return refreshWorkbenchOverview();
    return scanDevice(false);
}
function leaveLibraryRead() {
    libraryRead.owner = ''; libraryRead.error = ''; renderLibraryRead(); showLibraryHome();
}
function wbIcon(name) {
    const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    icon.classList.add('icon'); icon.setAttribute('aria-hidden', 'true');
    const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
    use.setAttribute('href', '/assets/workbench-icons.svg#' + name); icon.append(use); return icon;
}
function wbSystemIcon(system) {
    return ({NES:'console-nes',SNES:'console-snes',GB:'console-gameboy',GBC:'console-gameboy',GBA:'console-gba',SS:'console-saturn',MD:'console-megadrive',PS1:'console-playstation',MAME:'console-arcade',FBNeo:'console-arcade'})[getSystemAbbreviation(system)] || 'device-gamepad';
}
function wbElement(tag, className, text) {
    const el = document.createElement(tag); el.className = className;
    if (text !== undefined) el.textContent = text; return el;
}
function wbSystemName(system) {
    const names = {NES:'红白机',SS:'土星',SNES:'超级任天堂',MD:'Mega Drive',GBA:'Game Boy Advance',GBC:'Game Boy Color',GB:'Game Boy',PS1:'PlayStation',FBNeo:'FBNeo',MAME:'MAME'};
    const abbr = getSystemAbbreviation(system);
    return currentUILanguage === 'en' ? system.replace(/^[^-]+ - /, '') : names[abbr] || system.replace(/^[^-]+ - /, '');
}
function wbStorageKind(path) {
    return /^\/(?:storage\/(?:emulated|self)|sdcard)\//.test(path) ? 'internal' : path.startsWith('/storage/') ? 'card' : 'local';
}
function setStorageScope(scope) {
    workbenchOverview.scope = scope;
    renderWorkbenchOverview(!document.getElementById('library-overview').hidden);
    if (gameLibrary.data) renderGameLibrary();
    renderWorkbenchChrome(workbenchSnapshot());
}
function workbenchGroups(data, scope) {
    const groups = new Map();
    for (const playlist of data.playlists) {
        const group = groups.get(playlist.system) || {system:playlist.system,count:0,missing:0,covers:[],locations:new Set()};
        for (const [kind, location] of Object.entries(playlist.locations)) {
            if (scope !== 'all' && scope !== kind) continue;
            group.count += location.count; group.missing += location.missing;
            group.covers.push(...location.covers); group.locations.add(kind);
        }
        if (group.count) groups.set(playlist.system, group);
    }
    return [...groups.values()];
}
async function loadWorkbenchOverview(key, root) {
    workbenchOverview.loading = true;
    beginLibraryRead('overview', workbenchText('正在统计游戏并获取封面信息…','Reading game counts and artwork information…'), root);
    try {
        const data = await desktopRequest('/api/library/overview?root=' + encodeURIComponent(root));
        if (workbenchOverview.key !== key) return;
        workbenchOverview.data = data; workbenchOverview.error = '';
    } catch (error) {
        if (workbenchOverview.key === key) workbenchOverview.error = error.message;
    } finally {
        if (workbenchOverview.key === key) {
            workbenchOverview.loading = false;
            finishLibraryRead('overview', workbenchOverview.error);
            renderWorkbenchOverview(!document.getElementById('library-overview').hidden);
            renderWorkbenchChrome(workbenchSnapshot());
        }
    }
}
function refreshWorkbenchOverview() {
    workbenchOverview.key = '';
    renderWorkbench();
}
function renderWorkbenchOverview(visible) {
    const panel = document.getElementById('library-overview'); panel.hidden = !visible;
    if (!visible) return;
    const root = currentDeviceScan.root_path || currentDeviceScan.target_path;
    const key = JSON.stringify([root, currentDeviceScan.playlists.map(p => [p.path,p.item_count,p.modified_at])]);
    if (key !== workbenchOverview.key) {
        const rootChanged = workbenchOverview.key && JSON.parse(workbenchOverview.key)[0] !== root;
        workbenchOverview.key = key; if (rootChanged) workbenchOverview.data = null; workbenchOverview.error = '';
        loadWorkbenchOverview(key, root);
    }
    panel.replaceChildren();
    const actual = workbenchOverview.data;
    const groups = actual ? workbenchGroups(actual, workbenchOverview.scope) : [...new Set(currentDeviceScan.playlists.map(p => p.system))].map(system => ({system,count:currentDeviceScan.playlists.filter(p => p.system === system).reduce((n,p)=>n+p.item_count,0),covers:[],locations:new Set()}));
    const total = actual ? groups.reduce((n,g)=>n+g.count,0) : currentDeviceScan.totals?.items || 0;
    const missing = actual ? groups.reduce((n,g)=>n+g.missing,0) : 0;
    const subtitle = wbElement('p','overview-subtitle',workbenchText(`${total} 个游戏 · ${groups.length} 个主机`,`${total} games · ${groups.length} systems`));
    if (autoScanState.plan?.unclassified.length) subtitle.textContent += workbenchText(` · ${autoScanState.plan.unclassified.length} 项待分类`,` · ${autoScanState.plan.unclassified.length} unclassified`);
    panel.append(subtitle);
    if (missing > 0) {
        const bar = wbElement('div','overview-status'); bar.id = 'overview-status';
        const complete = wbElement('button','btn btn-muted',workbenchText('一键补全','Complete all'));
        complete.type='button'; complete.id='overview-complete-button'; complete.onclick=()=>startCompletion();
        complete.disabled=document.getElementById('preview-button').disabled;
        bar.append(wbIcon('photo'),wbElement('span','overview-status-text',workbenchText(`${missing} 个游戏缺少封面`,`${missing} games missing artwork`)),complete);
        panel.append(bar);
    }
    const toolbar = wbElement('div','overview-toolbar'); toolbar.append(wbElement('h2','',workbenchText('主机','Systems')));
    panel.append(toolbar);
    const grid = wbElement('div','overview-system-grid workbench-cards');
    const showLocations=workbenchOverview.scope==='all'&&new Set(groups.flatMap(group=>[...group.locations])).size>1;
    for (const group of groups) {
        const card = wbElement('button','overview-system-card'); card.type = 'button';
        card.title = group.system;
        card.setAttribute('aria-label',workbenchText('浏览 ','Browse ') + group.system);
        const art = wbElement('div','platform-art');
        for (const cover of group.covers.slice(0,3)) {
            const image = document.createElement('img'); image.src = cover.url; image.alt = cover.label; image.loading='lazy'; image.onerror=()=>image.remove(); art.append(image);
        }
        if (!group.covers.length) {art.classList.add('art-empty'); art.append(wbIcon('device-gamepad'),wbElement('span','',workbenchOverview.loading ? workbenchText('正在读取封面','Loading covers') : workbenchText('暂无封面','No artwork yet')));}
        const details=wbElement('div','overview-system-details'); const heading=wbElement('div','platform-heading'); heading.append(wbElement('strong','',getSystemAbbreviation(group.system)));
        details.append(heading,wbElement('span','',formatGameCount(group.count)));
        const locations=wbElement('div','platform-locations');
        for (const location of group.locations) locations.append(wbElement('span','',workbenchText(({internal:'内部存储',card:'存储卡',local:'本地目录'})[location],({internal:'Internal',card:'SD card',local:'Local'})[location])));
        if(showLocations)details.append(locations);card.append(art,details);
        card.onclick=async()=>{selectedLibrarySystem=group.system;renderDeviceScan(currentDeviceScan);await selectFirstPlaylistForSystem(group.system);};grid.append(card);
    }
    panel.append(grid);
    if (workbenchOverview.error || !groups.length) {
        const note=wbElement('p','overview-note');note.id='overview-note';
        note.textContent=workbenchOverview.error ? workbenchText('资料读取失败：','Could not read artwork: ')+workbenchOverview.error : workbenchText('还没有游戏。点击「添加游戏」开始。','No games yet. Choose Add games to start.');
        panel.append(note);
    }
    if (workbenchOverview.error) {const retry=wbElement('button','btn btn-muted',workbenchText('重新读取','Retry'));retry.onclick=refreshWorkbenchOverview;panel.append(retry);}
}
function renderWorkbenchChrome(state) {
    for (const [selector,zh,en] of [
        ['#manual-add-button','＋ 添加游戏','＋ Add games'],
        ['.tools-menu summary','工具','Tools'],['#device-switch-button','切换设备','Switch device']]) {
        const button=document.querySelector(selector);
        if(button?.lastChild?.nodeType===3)button.lastChild.textContent=workbenchText(zh,en);
    }
    document.getElementById('workbench-device').setAttribute('aria-label',workbenchText('设备详情','Device details'));
    document.getElementById('workbench-device').title=workbenchText('查看设备详情与切换游戏库','Device details and switch library');
    renderWorkbenchTaskBadge();
    document.getElementById('workbench-device').textContent=!currentDeviceScan?.connected ? workbenchText('设备与游戏库','Device & library') : currentDeviceScan.transport==='local' ? workbenchText('本地游戏库','Local library') : workbenchText('当前掌机','Handheld');
    const connection=document.getElementById('workbench-connection');connection.textContent=currentDeviceScan?.connected ? workbenchText('已连接','Connected') : workbenchText('未连接','Disconnected');connection.classList.toggle('connected',Boolean(currentDeviceScan?.connected));
    const hasDevicePaths=workbenchOverview.data?.playlists.some(p=>p.locations.internal||p.locations.card);
    document.getElementById('storage-scope').hidden=!currentDeviceScan?.connected || (currentDeviceScan.transport==='local'&&!hasDevicePaths);
    document.querySelectorAll('[data-scope]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.scope===workbenchOverview.scope)));
    document.getElementById('completion-entry-note').classList.add('sr-only');
    if (!state.previewValid) document.getElementById('preview-button').textContent=workbenchOverview.scope==='all'
        ?workbenchText('补全名称与封面','Complete names & artwork')
        :document.getElementById('playlist_path').value?workbenchText('补全整个列表','Complete entire playlist'):workbenchText('补全全部存储','Complete all storage');
    document.getElementById('preview-button').title=workbenchText('补全当前列表；未选择主机时补全全部存储中的列表','Complete the selected playlist, or all storage locations when no system is selected');
    if (!document.getElementById('playlist_path').value && currentDeviceScan?.connected) document.getElementById('workspace-title').textContent=workbenchText('游戏库','Game library');
    document.getElementById('manual-add-button').hidden=state.previewValid;
    if(workbenchOverview.data){
        const groups=workbenchGroups(workbenchOverview.data,workbenchOverview.scope);
        document.querySelectorAll('.playlist-system-tab').forEach(button=>{
            const count=button.querySelector('.system-game-count');
            if(count)count.textContent=button.id==='library-all-systems'?groups.reduce((n,g)=>n+g.count,0):groups.find(g=>g.system===button.title)?.count||0;
        });
    }
}
function renderWorkbenchTaskBadge() {
    const job=workbenchOverview.job;
    const failed=job?.status==='failed'||job?.partial;
    const count=workbenchOverview.activeJobs;
    const button=document.getElementById('task-center-button'),badge=document.getElementById('task-center-badge');
    badge.hidden=workbenchOverview.taskError||(!count&&!failed);badge.textContent=count?String(count):'';badge.classList.toggle('task-failed',!count&&Boolean(failed));
    const label=workbenchOverview.taskError?workbenchText('任务状态暂不可用，点击查看详情','Task status unavailable; open details'):count?workbenchText(`任务中心：${count} 个任务进行中`,`Task center: ${count} active tasks`):failed?workbenchText('任务中心：最近任务需要处理','Task center: latest task needs attention'):workbenchText('任务中心','Task center');
    button.title=label;button.setAttribute('aria-label',label);
}
async function pollWorkbenchTask() {
    try {
        const data=await desktopRequest('/api/jobs/status');const job=data.job;
        workbenchOverview.job=job||null;workbenchOverview.activeJobs=data.active_count;workbenchOverview.taskError=false;
        if(job&&!['pending','running'].includes(job.status)){
            const receipt=job.id+job.status;
            if(workbenchOverview.receipt!==receipt){const previous=workbenchOverview.receipt;workbenchOverview.receipt=receipt;if(previous&&!libraryRead.owner&&!libraryRead.error)refreshWorkbenchOverview();}
        }
    }catch(error){workbenchOverview.taskError=true;}
    renderWorkbenchTaskBadge();
    setTimeout(pollWorkbenchTask,3000);
}
document.addEventListener('DOMContentLoaded',()=>{document.querySelectorAll('[data-ui-icon]').forEach(el=>el.replaceWith(wbIcon(el.dataset.uiIcon)));pollWorkbenchTask();});

const autoScanState={busy:false,job:null,previewId:null,plan:null,root:'',generation:0};
async function openAutoScan(){
    if(workbench.operation)return;
    const root=document.getElementById('retroarch_root').value;
    if(!root){showStatus(uiText('请先打开一个游戏库'),'error');return;}
    const generation=++autoScanState.generation;autoScanState.root=root;autoScanState.previewId=null;autoScanState.plan=null;
    document.getElementById('auto-scan-results').replaceChildren();document.getElementById('auto-scan-apply').hidden=true;
    document.getElementById('auto-scan-status').textContent=uiText('选择需要扫描的存储。扫描只读取目录，确认后才生成游戏列表。');
    const roots=document.getElementById('auto-scan-roots');roots.replaceChildren();document.getElementById('auto-scan-start').disabled=true;
    document.getElementById('auto-scan-dialog').showModal();
    try{
        const data=await desktopRequest('/api/library/sources');if(generation!==autoScanState.generation)return;
        const serial=root.startsWith('mtp://')?root.split('/')[2]:null;
        const sources=serial?data.sources.filter(s=>s.transport==='mtp'&&s.path.split('/')[2]===serial):[{path:root.replace(/[\\/][^\\/]+[\\/]?$/,''),label:uiText('本地游戏目录（游戏库同级）')}];
        const unique=new Set();
        for(const source of sources){const path=serial?source.path.split('/').slice(0,4).join('/')+'/':source.path;if(unique.has(path))continue;unique.add(path);
            const label=wbElement('label','auto-scan-root');const input=document.createElement('input');input.type='checkbox';input.value=path;input.checked=true;input.onchange=()=>{autoScanState.previewId=null;document.getElementById('auto-scan-apply').hidden=true;};label.append(input,wbElement('span','',source.label||uiText('设备存储')));roots.append(label);
        }
        if(!sources.length)throw new Error(uiText('没有可扫描的存储，请确认掌机已选择文件传输。'));
        document.getElementById('auto-scan-start').disabled=false;
    }catch(error){document.getElementById('auto-scan-status').textContent=error.message;}
}
function closeAutoScan(){if(autoScanState.busy)return;++autoScanState.generation;document.getElementById('auto-scan-dialog').close();}
async function autoScanJob(route,payload){
    if(!beginWorkbenchOperation('auto-scan'))throw new Error(uiText('请等待当前任务完成'));autoScanState.busy=true;
    document.getElementById('auto-scan-start').disabled=true;document.getElementById('auto-scan-apply').disabled=true;
    document.querySelectorAll('#auto-scan-roots input, #auto-scan-results input').forEach(input=>input.disabled=true);
    try{
        const started=await desktopRequest(route,payload);autoScanState.job=started.job_id;document.getElementById('auto-scan-cancel').hidden=false;
        const result=await new Promise((resolve,reject)=>{const events=new EventSource('/api/progress?job_id='+started.job_id);events.onmessage=e=>{const job=JSON.parse(e.data);document.getElementById('auto-scan-status').textContent=currentUILanguage==='en'?`Analyzing… ${job.total?job.progress+' / '+job.total:''}`:job.message||uiText('正在分析…');if(job.status==='completed'){events.close();resolve(job.result);}else if(job.error||['failed','cancelled'].includes(job.status)){events.close();reject(new Error(job.error||uiText('任务已取消')));}};events.onerror=()=>{document.getElementById('auto-scan-status').textContent=uiText('进度连接中断，正在重连；任务不会重复提交。');};});
        return {id:started.job_id,result};
    }finally{document.getElementById('auto-scan-cancel').hidden=true;autoScanState.busy=false;autoScanState.job=null;document.getElementById('auto-scan-start').disabled=false;document.getElementById('auto-scan-apply').disabled=false;document.querySelectorAll('#auto-scan-roots input, #auto-scan-results input').forEach(input=>input.disabled=false);endWorkbenchOperation();}
}
async function previewAutoScan(){
    const sources=[...document.querySelectorAll('#auto-scan-roots input:checked')].map(input=>input.value);
    autoScanState.previewId=null;autoScanState.plan=null;document.getElementById('auto-scan-results').replaceChildren();document.getElementById('auto-scan-apply').hidden=true;
    try{
        const {id,result}=await autoScanJob('/api/content/auto-preview',{root:autoScanState.root,sources});autoScanState.previewId=id;autoScanState.plan=result;
        const rows=document.getElementById('auto-scan-results');
        for(const row of result.rows){const article=wbElement('label','auto-scan-result');const input=document.createElement('input');input.type='checkbox';input.dataset.system=row.system;input.checked=row.added>0;input.disabled=!row.added;
            const details=wbElement('div','');details.append(wbElement('strong','',wbSystemName(row.system)),wbElement('small','',workbenchText(`新增 ${row.added} · 已有 ${row.retained} · 跳过 ${row.skipped}`,`New ${row.added} · Existing ${row.retained} · Skipped ${row.skipped}`)));article.append(input,details);rows.append(article);}
        for(const row of result.unclassified){const article=wbElement('div','auto-scan-result');const details=wbElement('div','');details.append(wbElement('strong','',uiText('待配置')),wbElement('small','',row.directory),wbElement('small','',uiText(row.reason)));article.append(details);rows.append(article);}
        const count=result.rows.reduce((n,r)=>n+r.added,0);document.getElementById('auto-scan-status').textContent=workbenchText(`扫描完成：${count} 个新游戏，${result.unclassified.length} 个目录待配置。未配置核心的列表由 RetroArch 选择核心；已有核心设置保留。`,`Scan complete: ${count} new games; ${result.unclassified.length} folders need setup. RetroArch selects unassigned cores; existing core settings are preserved.`);
        document.getElementById('auto-scan-apply').hidden=!count;
    }catch(error){document.getElementById('auto-scan-status').textContent=error.message;}
}
async function applyAutoScan(){
    const systems=[...document.querySelectorAll('#auto-scan-results input:checked')].map(input=>input.dataset.system);
    if(!systems.length){document.getElementById('auto-scan-status').textContent=uiText('请选择至少一个有新增游戏的主机。');return;}
    const complete=document.getElementById('auto-scan-complete').checked;
    try{const {result}=await autoScanJob('/api/content/auto-apply',{preview_job_id:autoScanState.previewId,systems});autoScanState.previewId=null;document.getElementById('auto-scan-apply').hidden=true;
        document.getElementById('auto-scan-status').textContent=workbenchText(`已导入 ${result.added} 个游戏。原始游戏文件保持不变。`,`Imported ${result.added} games. Original game files are unchanged.`);
        await scanDevice();refreshWorkbenchOverview();
        if(complete){closeAutoScan();await runAllSystemsCompletion();}
    }catch(error){autoScanState.previewId=null;document.getElementById('auto-scan-apply').hidden=true;document.getElementById('auto-scan-status').textContent=error.message+workbenchText('；已完成的导入会保留，请重新扫描核对。','; completed imports are kept. Scan again to review.');}
}
document.addEventListener('DOMContentLoaded',()=>{
    document.getElementById('auto-scan-dialog').addEventListener('cancel',event=>{if(autoScanState.busy)event.preventDefault();else ++autoScanState.generation;});
    document.getElementById('library-read-dialog').addEventListener('cancel',event=>{event.preventDefault();if(!libraryRead.owner)leaveLibraryRead();});
});
if (typeof module !== 'undefined') module.exports = {workbenchGroups,wbStorageKind,workbenchOverview,loadWorkbenchOverview,libraryRead,beginLibraryRead,finishLibraryRead,renderWorkbenchTaskBadge};

async function cancelAutoScan(){
    if(!autoScanState.job)return;
    try{await desktopRequest('/api/jobs/cancel',{job_id:autoScanState.job});document.getElementById('auto-scan-status').textContent=uiText('正在取消，已完成的结果会保留。');}
    catch(error){document.getElementById('auto-scan-status').textContent=uiText('取消请求未送达：')+error.message;}
}
