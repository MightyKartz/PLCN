/* Read-only optical groups. Persistent game identities and files are never merged here. */
const discInspection = {generation:0, controller:null, data:null, key:null, limit:100};
function discInspectionKey() { return JSON.stringify(gameLibraryInput().slice(0,2)); }

async function openDiscInspection() {
    if (workbench.operation) return;
    const [path,system] = gameLibraryInput();
    if (!path) return;
    const generation = ++discInspection.generation, key = discInspectionKey();
    const controller = new AbortController();
    Object.assign(discInspection, {controller, data:null, key, limit:100});
    const dialog = document.getElementById('disc-inspection-dialog');
    document.getElementById('disc-inspection-search').value = '';
    document.getElementById('disc-inspection-filter').value = 'all';
    document.getElementById('disc-inspection-groups').replaceChildren();
    document.getElementById('disc-inspection-summary').textContent = workbenchText('正在检查当前目录内的列表及 M3U/CUE 引用…', 'Checking playlists and M3U/CUE references in this directory…');
    document.getElementById('disc-inspection-coverage').textContent = '';
    document.getElementById('disc-inspection-more').hidden = true;
    dialog.showModal();
    beginWorkbenchOperation('disc-inspection');
    try {
        const data = await desktopRequest('/api/playlist/discs?' + new URLSearchParams({path,system}), undefined, {signal:controller.signal});
        if (data.error) throw new Error(data.error);
        if (generation !== discInspection.generation || key !== discInspectionKey()) return;
        discInspection.data = data;
        renderDiscInspection();
    } catch (error) {
        if (generation !== discInspection.generation || key !== discInspectionKey() || error.name === 'AbortError') return;
        document.getElementById('disc-inspection-summary').textContent = workbenchText('检查失败：', 'Inspection failed: ') + error.message;
    } finally {
        if (generation === discInspection.generation) {
            discInspection.controller = null;
            endWorkbenchOperation();
        }
    }
}

function closeDiscInspection() {
    discInspection.controller?.abort();
    discInspection.controller = null; discInspection.generation++;
    if (workbench.operation === 'disc-inspection') endWorkbenchOperation();
    const dialog = document.getElementById('disc-inspection-dialog');
    if (dialog.open) dialog.close();
}

function discGroupMatches(group, files, query, filter) {
    if (filter === 'attention' && !group.issues.length) return false;
    if (filter === 'm3u' && group.kind !== 'm3u') return false;
    if (filter === 'candidate' && group.kind !== 'disc_set') return false;
    return !query || [group.label,...group.files.map(id=>files.get(id).path)].some(value=>value.toLowerCase().includes(query));
}

function renderDiscInspection() {
    const data = discInspection.data;
    if (!data || discInspection.key !== discInspectionKey()) return;
    const summary = data.summary;
    document.getElementById('disc-inspection-summary').textContent = workbenchText(
        `分组视图 ${summary.groups} 组 · ${summary.discs} 张光盘 · ${summary.files} 个关联文件 · 原列表 ${summary.entries} 个入口 · 候选 ${summary.candidates} 组 · ${summary.attention} 组有提醒`,
        `${summary.groups} groups · ${summary.discs} discs · ${summary.files} linked files · ${summary.entries} original entries · ${summary.candidates} candidates · ${summary.attention} groups have notices`);
    const coverage = document.getElementById('disc-inspection-coverage');
    coverage.textContent = workbenchText(`已读当前目录内 ${data.coverage.playlists} 个列表，未递归其他列表目录。`, `Read ${data.coverage.playlists} playlists in this directory; other directories are not included. `)
        + data.coverage.directory;
    for (const error of data.coverage.errors) {
        const line = document.createElement('p'); line.className = 'disc-issue';
        line.textContent = error.path + ' · ' + error.message; coverage.appendChild(line);
    }
    const files = new Map(data.files.map(file=>[file.id,file]));
    const query = document.getElementById('disc-inspection-search').value.trim().toLowerCase();
    const filter = document.getElementById('disc-inspection-filter').value;
    const groups = data.groups.filter(group=>discGroupMatches(group,files,query,filter));
    const container = document.getElementById('disc-inspection-groups'); container.replaceChildren();
    for (const group of groups.slice(0,discInspection.limit)) {
        const details = document.createElement('details'); details.className = 'disc-group';
        const title = document.createElement('summary');
        const label = document.createElement('strong'); label.textContent = group.label; title.appendChild(label);
        const state = document.createElement('span'); state.className = 'disc-group-state'; state.dataset.state = group.status;
        state.textContent = workbenchText(
            {configured:'已有 M3U',candidate:'候选组 · 未合并',attention:'需检查',single:'独立入口'}[group.status],
            {configured:'Existing M3U',candidate:'Candidate · Not merged',attention:'Needs attention',single:'Single entry'}[group.status]);
        title.appendChild(state);
        const count = document.createElement('span'); count.textContent = workbenchText(`${group.discs.length} 盘 · ${group.files.length} 文件`, `${group.discs.length} discs · ${group.files.length} files`); title.appendChild(count);
        details.appendChild(title);
        details.addEventListener('toggle',()=>{
            if (!details.open || details.children.length > 1) return;
            details.appendChild(buildDiscGroupDetails(group,files,data));
        });
        container.appendChild(details);
    }
    if (!groups.length) container.textContent = workbenchText('没有符合条件的游戏组。', 'No matching groups.');
    document.getElementById('disc-inspection-more').hidden = groups.length <= discInspection.limit;
}

function buildDiscGroupDetails(group, files, data) {
    const body = document.createElement('div'); body.className = 'disc-group-body';
    const note = document.createElement('p');
    note.textContent = group.kind === 'm3u' ? workbenchText('以下按现有 M3U 的引用顺序展示，不重排文件。', 'Shown in the existing M3U order; no files are reordered.')
        : group.kind === 'disc_set' ? workbenchText('依据同目录的明确盘号、游戏文件名和版本标记提出分组；尚未创建 M3U，原列表入口保持不变。', 'Suggested from explicit disc numbers, filenames and matching version tags in the same directory; no M3U has been created and existing entries are unchanged.')
        : workbenchText('保留现有独立入口。', 'The existing launch entry is retained.');
    body.appendChild(note);
    if (group.discs.length >= 2) {
        const action=document.createElement('button');action.type='button';action.className='btn btn-muted';wbIconButton(action,'eye',workbenchText('预览 M3U 方案','Preview M3U plan'));
        action.onclick=()=>openM3uEditor(group,files);body.appendChild(action);
    }
    if (!group.total_known && group.discs.length) {
        const unknown = document.createElement('p'); unknown.className = 'disc-coverage';
        unknown.textContent = workbenchText('未声明总盘数；只能检查已知盘号的缺口，不能证明末尾无缺盘。', 'Total disc count is unknown; only gaps in known numbers can be checked.'); body.appendChild(unknown);
    }
    if (group.issues.length) {
        const issues = document.createElement('ul'); issues.className = 'disc-issues';
        for (const issue of group.issues) { const li=document.createElement('li');li.textContent=[issue.message,issue.path,...(issue.related_paths || [])].filter(Boolean).join(' · ');issues.appendChild(li); }
        body.appendChild(issues);
    }
    const list = document.createElement('ol'); list.className = 'disc-members';
    for (const id of group.discs) {
        const file = files.get(id), li = document.createElement('li');
        const heading = document.createElement('strong');
        heading.textContent = workbenchText(`盘号 ${file.disc.number ?? '未知'} · `, `Disc ${file.disc.number ?? 'unknown'} · `) + file.format.toUpperCase() + ' · ' + discFileStatus(file);
        li.appendChild(heading);
        const path = document.createElement('p');path.className='disc-file-path';path.textContent=file.path;li.appendChild(path);
        const active = file.playlist_references.find(entry=>entry.playlist===data.playlist_path);
        const current = active || group.disc_records?.[id];
        if (current) {
            const label = document.createElement('p'); label.textContent=workbenchText('原入口：','Original entry: ')+current.label;li.appendChild(label);
            const core = document.createElement('p');core.className='disc-coverage';core.textContent=workbenchText('保留核心：','Keep core: ')+current.core_path;li.appendChild(core);
            for (const [kind,source] of Object.entries(current.artwork_sources || {})) {
                const saved = document.createElement('p');saved.textContent=artworkKindLabel(kind)+workbenchText('已保存图片源：',' saved artwork source: ')+source;li.appendChild(saved);
            }
            const image = active ? gameLibrary.data?.items.find(item=>item.index===current.index) : null;
            if (image?.image_url) { const img=document.createElement('img');img.src=image.image_url;img.alt=current.label;img.className='disc-artwork';li.appendChild(img); }
        }
        list.appendChild(li);
    }
    body.appendChild(list);
    const graph = document.createElement('details');
    const title = document.createElement('summary');title.textContent=workbenchText('全部文件与引用（含音轨）','All files and references (including tracks)');graph.appendChild(title);
    const nodes = document.createElement('ul');nodes.className='disc-files';
    for (const id of group.files) {
        const file=files.get(id), item=document.createElement('li');
        const path=document.createElement('p');path.className='disc-file-path';path.textContent=file.path+' · '+discFileStatus(file);item.appendChild(path);
        for (const entry of file.playlist_references) { const ref=document.createElement('p');ref.textContent=workbenchText('列表引用：','Playlist reference: ')+entry.playlist+' #'+(entry.index+1)+' · '+entry.label+' · '+entry.launch_path;item.appendChild(ref); }
        for (const edge of data.references.filter(edge=>edge.target===id)) { const ref=document.createElement('p');ref.textContent=files.get(edge.source).path+' · '+workbenchText(`第 ${edge.line} 行`,`line ${edge.line}`);item.appendChild(ref); }
        nodes.appendChild(item);
    }
    graph.appendChild(nodes);body.appendChild(graph);
    return body;
}

function discFileStatus(file) {
    const labels = {present:['文件存在','File present'],missing:['文件缺失','File missing'],unmapped:['尚未检查','Not checked'],unchecked:['尚未检查','Not checked'],unreadable:['读取失败','Read failed'],invalid:['无效文件','Invalid file']};
    const state = workbenchText(...labels[file.status]);
    return state + (file.size === null ? '' : ' · ' + (file.size < 1024 * 1024 ? file.size + ' B' : (file.size/1024/1024).toFixed(2) + ' MiB'));
}

document.getElementById('disc-inspection-dialog').addEventListener('cancel',event=>{event.preventDefault();closeDiscInspection();});
document.getElementById('disc-inspection-dialog').addEventListener('close',()=>{if(!document.getElementById('disc-inspection-dialog').open)closeDiscInspection();});
