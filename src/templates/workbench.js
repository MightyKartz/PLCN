/* Real-data library workbench. Artwork and job state are read-only projections. */
const workbenchOverview = {key: '', loadedKey: '', data: null, error: '', scope: 'all', loading: false};
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
    for (const [id,zh,en,icon] of [['library-read-retry','重新读取','Retry','refresh'],['library-read-switch','切换设备','Switch device','device-gamepad']]) wbIconButton(document.getElementById(id), icon, workbenchText(zh,en));
    document.getElementById('library-read-banner-retry').textContent = workbenchText('重试','Retry');
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
function wbIconButton(button, name, label) {
    button.classList.add('dialog-icon-button');
    button.title = label;
    button.setAttribute('aria-label', label);
    button.replaceChildren(wbIcon(name));
}
function wbSystemIcon(system) {
    return ({NES:'console-nes',SNES:'console-snes',GB:'console-gameboy',GBC:'console-gameboy',GBA:'console-gba',SS:'console-saturn',MD:'console-megadrive',PS1:'console-playstation',MAME:'console-arcade',FBNeo:'console-arcade'})[getSystemAbbreviation(system)] || 'device-gamepad';
}
function wbElement(tag, className, text) {
    const el = document.createElement(tag); el.className = className;
    if (text !== undefined) el.textContent = text; return el;
}
function wbSystemName(system) {
    const names = {
        NES:'Nintendo Entertainment System', SNES:'Super Nintendo Entertainment System',
        SS:'Sega Saturn', MD:'Mega Drive', GBA:'Game Boy Advance', GBC:'Game Boy Color',
        GB:'Game Boy', PS1:'PlayStation', FBNeo:'FBNeo', MAME:'MAME'
    };
    return names[getSystemAbbreviation(system)] || system.replace(/^[^-]+ - /, '');
}
// Box art in these libraries spans portrait boxes, square cases and wide GBA packaging.
function wbCoverFrameRatio(system) {
    const ratios = {GBA: 8 / 5, NES: 3 / 4, MD: 3 / 4, FBNEO: 3 / 4,
        GB: 4 / 5, GBC: 4 / 5, SNES: 2 / 3, MAME: 4 / 3};
    return ratios[getSystemAbbreviation(system).toUpperCase()] ?? 1;
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
        const group = groups.get(playlist.system) || {system:playlist.system,count:0,missing:0,nonChineseNames:0,covers:[],locations:new Set()};
        for (const [kind, location] of Object.entries(playlist.locations)) {
            if (scope !== 'all' && scope !== kind) continue;
            group.count += location.count; group.missing += location.missing; group.nonChineseNames += location.non_chinese_names || 0;
            group.covers.push(...location.covers); group.locations.add(kind);
        }
        if (group.count) groups.set(playlist.system, group);
    }
    return [...groups.values()];
}
function libraryOverviewKey(scan) {
    return JSON.stringify([scan.root_path || scan.target_path,
        scan.playlists.filter(playlist => playlist.valid).map(playlist => [playlist.path,
            playlist.revision || [playlist.item_count, playlist.modified_at], playlist.system]),
        scan.directories?.thumbnails || '']);
}

async function loadWorkbenchOverview(key, root) {
    workbenchOverview.loading = true;
    beginLibraryRead('overview', workbenchText('正在统计游戏并获取封面信息…','Reading game counts and artwork information…'), root);
    try {
        const previous = workbenchOverview.loadedKey && JSON.parse(workbenchOverview.loadedKey);
        let data;
        if (previous && previous[0] === root) {
            const [, rows, thumbnails] = JSON.parse(key);
            const revisions = new Map(previous[1].map(row => [row[0], JSON.stringify(row)]));
            const cached = new Map(workbenchOverview.data.playlists.map(row => [row.path, row]));
            const playlists = await Promise.all(rows.map(async row => {
                const [path] = row;
                if (previous[2] === thumbnails && revisions.get(path) === JSON.stringify(row) && cached.has(path))
                    return cached.get(path);
                const query = new URLSearchParams({path, thumbnails});
                return (await desktopRequest('/api/library/playlist-summary?' + query)).overview;
            }));
            data = {playlists};
        } else {
            data = await desktopRequest('/api/library/overview?root=' + encodeURIComponent(root));
        }
        if (workbenchOverview.key !== key) return;
        workbenchOverview.data = data; workbenchOverview.loadedKey = key; workbenchOverview.error = '';
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
    workbenchOverview.key = workbenchOverview.loadedKey = '';
    renderWorkbench();
}
// Reuse decoded images when the surrounding overview is redrawn for the same library read.
const overviewFans = new WeakMap();

function renderPlatformFan(group, data) {
    const candidates = new Map();
    for (const cover of group.covers) {
        const path = cover.url.split('&v=')[0];
        if (!candidates.has(path)) candidates.set(path, cover);
        if (candidates.size === 5) break;
    }
    const covers = [...candidates.values()];
    const key = JSON.stringify([group.system, covers.map(cover => cover.url)]);
    if (data && !overviewFans.has(data)) overviewFans.set(data, new Map());
    const cache = data && overviewFans.get(data);
    if (cache?.has(key)) return cache.get(key);

    const art = wbElement('div', 'platform-art');
    art.setAttribute('aria-hidden', 'true');
    const fan = wbElement('div', 'platform-fan');
    art.append(fan);
    cache?.set(key, art);

    const preferredRatio = wbCoverFrameRatio(group.system);
    const height = Math.min(160, 146 / Math.sqrt(preferredRatio));
    function showCovers(selected) {
        const arranged = selected.length === 1 ? [null, selected[0], null] : [selected[0], selected[1], selected[2]];
        const widths = arranged.map(cover => height * (cover?.ratio ?? preferredRatio));
        const [left, center, right] = widths;
        const offsets = [
            -(left + center) / 2 + Math.min(left, center) * 0.2,
            0,
            (right + center) / 2 - Math.min(right, center) * 0.2,
        ];
        const width = 2 * (Math.max(...widths.map((value, index) => Math.abs(offsets[index]) + value / 2)) + 20);
        const fanHeight = height + 30;
        fan.style.setProperty('--fan-width', width + 'px');
        fan.style.setProperty('--fan-ratio', width / fanHeight);
        fan.style.setProperty('--cover-height', height / fanHeight * 100 + '%');
        fan.replaceChildren(...arranged.map((cover, index) => {
            const slot = wbElement('span', 'platform-cover');
            slot.style.setProperty('--cover-width', widths[index] / width * 100 + '%');
            slot.style.setProperty('--cover-center', (0.5 + offsets[index] / width) * 100 + '%');
            if (cover) {
                slot.title = cover.label;
                slot.append(cover.image);
            } else {
                slot.classList.add('is-empty');
            }
            return slot;
        }));
    }

    showCovers([]);
    if (covers.length) {
        const images = covers.map((cover, index) => new Promise(resolve => {
            const image = document.createElement('img');
            image.alt = '';
            image.loading = 'lazy';
            image.className = 'platform-cover-probe';
            image.onload = () => {
                image.remove();
                image.classList.remove('platform-cover-probe');
                resolve({label: cover.label, image, ratio: image.naturalWidth / image.naturalHeight, index});
            };
            image.onerror = () => {
                image.remove();
                resolve(null);
            };
            image.src = cover.url;
            art.append(image);
        }));
        Promise.all(images).then(loaded => {
            const distance = cover => Math.abs(Math.log(cover.ratio / preferredRatio));
            const chosen = loaded.filter(Boolean)
                .sort((a, b) => distance(a) - distance(b))
                .slice(0, 3)
                .sort((a, b) => a.index - b.index);
            showCovers(chosen);
        });
    }
    return art;
}

function renderWorkbenchOverview(visible) {
    const panel = document.getElementById('library-overview'); panel.hidden = !visible;
    if (!visible) return;
    const root = currentDeviceScan.root_path || currentDeviceScan.target_path;
    const key = libraryOverviewKey(currentDeviceScan);
    if (key !== workbenchOverview.key && !workbench.operation) {
        const rootChanged = workbenchOverview.key && JSON.parse(workbenchOverview.key)[0] !== root;
        workbenchOverview.key = key;
        if (rootChanged) {
            workbenchOverview.data = null;
            workbenchOverview.loadedKey = '';
        }
        workbenchOverview.error = '';
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
    const nonChineseNames = actual ? groups.reduce((n,g)=>n+g.nonChineseNames,0) : 0;
    if (missing > 0 || nonChineseNames > 0) {
        const bar = wbElement('div','overview-status'); bar.id = 'overview-status';
        const complete = wbElement('button','btn btn-muted',workbenchText('一键补全','Complete all'));
        wbIconButton(complete, 'circle-check', complete.textContent);
        complete.type='button'; complete.id='overview-complete-button'; complete.onclick=()=>startCompletion();
        complete.title = workbenchText('自动补全中文名与封面；补全后仍提示的项目需手动处理','Auto-fills Chinese names and boxart; anything still flagged afterwards needs manual attention');
        complete.disabled=document.getElementById('preview-button').disabled;
        bar.append(wbIcon('photo'),wbElement('span','overview-status-text',[missing ? workbenchText(`${missing} 个游戏缺少封面`,`${missing} games missing cover`) : '', nonChineseNames ? workbenchText(`${nonChineseNames} 个游戏尚未使用中文名`,`${nonChineseNames} games without Chinese names`) : ''].filter(Boolean).join(' · ')),complete);
        panel.append(bar);
    }
    const grid = wbElement('div','overview-system-grid workbench-cards');
    const showLocations=workbenchOverview.scope==='all'&&new Set(groups.flatMap(group=>[...group.locations])).size>1;
    for (const group of groups) {
        const displayName = wbSystemName(group.system);
        const abbreviation = getSystemAbbreviation(group.system);
        const count = formatGameCount(group.count);
        const card = wbElement('button', 'overview-system-card');
        card.type = 'button';
        card.disabled = Boolean(workbench.operation);
        card.dataset.system = group.system;
        card.setAttribute('aria-label', `${displayName} · ${count}`);
        const badge = wbElement('span', 'overview-system-badge', abbreviation);
        badge.setAttribute('aria-hidden', 'true');
        const heading = wbElement('div', 'platform-heading');
        const details = wbElement('div', 'overview-system-details');
        details.append(wbElement('strong', '', displayName), wbElement('span', '', count));
        if (showLocations) {
            const locations = wbElement('div', 'platform-locations');
            for (const location of group.locations) locations.append(wbElement('span', '', workbenchText(
                ({internal:'内部存储',card:'存储卡',local:'本地目录'})[location],
                ({internal:'Internal',card:'SD card',local:'Local'})[location])));
            details.append(locations);
        }
        const arrow = wbElement('span', 'overview-system-arrow', '›');
        arrow.setAttribute('aria-hidden', 'true');
        heading.append(badge, details, arrow);
        card.append(heading, renderPlatformFan(group, actual));
        card.onclick = () => browseLibrarySystem(group.system);
        grid.append(card);
    }
    if (groups.length) panel.append(grid);
    if (workbenchOverview.error || !groups.length) {
        const note=wbElement('p','overview-note');note.id='overview-note';
        note.textContent=workbenchOverview.error ? workbenchText('资料读取失败：','Could not read artwork: ')+workbenchOverview.error : workbenchText('还没有游戏。打开「游戏文件」开始。','No games yet. Open Game files to start.');
        panel.append(note);
    }
    if (workbenchOverview.error) {const retry=wbElement('button','btn btn-muted',workbenchText('重新读取','Retry'));retry.onclick=refreshWorkbenchOverview;panel.append(retry);}
}
function renderWorkbenchChrome(state) {
    const localLibrary = currentDeviceScan?.transport === 'local';
    const scanButton = document.getElementById('manual-scan-button');
    const scanLabel = localLibrary ? workbenchText('扫描新增游戏', 'Scan for new games')
        : workbenchText('扫描掌机游戏', 'Scan handheld games');
    scanButton.title = scanLabel;
    scanButton.setAttribute('aria-label', scanLabel);
    for (const [selector,zh,en] of [
        ['.tools-menu summary','工具','Tools'],['#device-switch-button','切换设备','Switch device']]) {
        const button=document.querySelector(selector);
        if(button?.lastChild?.nodeType===3)button.lastChild.textContent=workbenchText(zh,en);
    }
    document.getElementById('workbench-device').setAttribute('aria-label',workbenchText('设备详情','Device details'));
    document.getElementById('workbench-device').title=workbenchText('查看设备详情与切换游戏库','Device details and switch library');
    document.getElementById('workbench-device').textContent=!currentDeviceScan?.connected ? workbenchText('设备与游戏库','Device & library') : currentDeviceScan.transport==='local' ? workbenchText('本地游戏库','Local library') : currentDeviceScan.device?.model?.replaceAll('_',' ') || workbenchText('当前掌机','Handheld');
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
    document.getElementById('game-files-button').hidden=state.previewValid;
    document.getElementById('manual-scan-button').hidden=state.previewValid;
    if(workbenchOverview.data){
        const groups=workbenchGroups(workbenchOverview.data,workbenchOverview.scope);
        document.querySelectorAll('.playlist-system-tab').forEach(button=>{
            const count=button.querySelector('.system-game-count');
            if(count)count.textContent=button.id==='library-all-systems'?groups.length:groups.find(g=>g.system===button.title)?.count||0;
        });
    }
}
document.addEventListener('DOMContentLoaded',()=>{document.querySelectorAll('[data-ui-icon]').forEach(el=>el.replaceWith(wbIcon(el.dataset.uiIcon)));});

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
        for (const row of result.rows) {
            const article = wbElement('label', 'auto-scan-result');
            const input = document.createElement('input');
            input.type = 'checkbox';
            input.value = row.target;
            input.checked = row.added > 0;
            input.disabled = !row.added;
            const details = wbElement('div', '');
            details.append(
                wbElement('strong', '', wbSystemName(row.system)),
                wbElement('small', '', row.target.split(/[\\/]/).pop()),
                wbElement('small', '', workbenchText(`新增 ${row.added} · 已有 ${row.retained} · 跳过 ${row.skipped}`, `New ${row.added} · Existing ${row.retained} · Skipped ${row.skipped}`))
            );
            article.append(input, details);
            rows.append(article);
        }
        for(const row of result.unclassified){const article=wbElement('div','auto-scan-result');const details=wbElement('div','');details.append(wbElement('strong','',uiText('待配置')),wbElement('small','',row.directory),wbElement('small','',uiText(row.reason)));article.append(details);rows.append(article);}
        const count=result.rows.reduce((n,r)=>n+r.added,0);document.getElementById('auto-scan-status').textContent=workbenchText(`扫描完成：${count} 个新游戏，${result.unclassified.length} 个目录待配置。未配置核心的列表由 RetroArch 选择核心；已有核心设置保留。`,`Scan complete: ${count} new games; ${result.unclassified.length} folders need setup. RetroArch selects unassigned cores; existing core settings are preserved.`);
        document.getElementById('auto-scan-apply').hidden=!count;
    }catch(error){document.getElementById('auto-scan-status').textContent=error.message;}
}
async function applyAutoScan(){
    const targets=[...document.querySelectorAll('#auto-scan-results input:checked')].map(input=>input.value);
    if (!targets.length) {
        document.getElementById('auto-scan-status').textContent = workbenchText('请选择至少一个有新增游戏的列表。', 'Choose at least one playlist with new games.');
        return;
    }
    const complete=document.getElementById('auto-scan-complete').checked;
    try{const {result}=await autoScanJob('/api/content/auto-apply',{preview_job_id:autoScanState.previewId,targets});autoScanState.previewId=null;document.getElementById('auto-scan-apply').hidden=true;
        document.getElementById('auto-scan-status').textContent=workbenchText(`已导入 ${result.added} 个游戏。原始游戏文件保持不变。`,`Imported ${result.added} games. Original game files are unchanged.`);
        await refreshLibraryPlaylists(result.playlists.map(playlist => playlist.playlist_path));
        if(complete){closeAutoScan();await runAllSystemsCompletion();}
    }catch(error){autoScanState.previewId=null;document.getElementById('auto-scan-apply').hidden=true;document.getElementById('auto-scan-status').textContent=error.message+workbenchText('；已完成的导入会保留，请重新扫描核对。','; completed imports are kept. Scan again to review.');}
}
document.addEventListener('DOMContentLoaded',()=>{
    document.getElementById('auto-scan-dialog').addEventListener('cancel',event=>{if(autoScanState.busy)event.preventDefault();else ++autoScanState.generation;});
    document.getElementById('library-read-dialog').addEventListener('cancel',event=>{event.preventDefault();if(!libraryRead.owner)leaveLibraryRead();});
});
if (typeof module !== 'undefined') module.exports = {workbenchGroups,wbStorageKind,workbenchOverview,loadWorkbenchOverview,libraryRead,beginLibraryRead,finishLibraryRead};

async function cancelAutoScan(){
    if(!autoScanState.job)return;
    try{await desktopRequest('/api/jobs/cancel',{job_id:autoScanState.job});document.getElementById('auto-scan-status').textContent=uiText('正在取消，已完成的结果会保留。');}
    catch(error){document.getElementById('auto-scan-status').textContent=uiText('取消请求未送达：')+error.message;}
}
