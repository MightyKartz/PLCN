/* The server owns the reviewed plan. Editing any input invalidates its job ID. */
const m3uEditor={group:null,files:null,order:[],selected:new Set(),revision:0,previewId:null,previewKey:null,busy:false,changed:false};
const m3uField=name=>document.getElementById('m3u-'+name);
function invalidateM3uPreview(){m3uEditor.revision++;m3uEditor.previewId=null;m3uEditor.previewKey=null;m3uField('apply').disabled=true;m3uField('review').hidden=true;}
function openM3uEditor(group,files){
    if(workbench.operation)return;
    Object.assign(m3uEditor,{group,files,order:[...group.discs],selected:new Set(group.discs),changed:false});
    invalidateM3uPreview();
    m3uField('label').value=group.label;
    const first=files.get(group.members[0]);
    m3uField('filename').value=group.kind==='m3u'?(first.path.startsWith('mtp://')?decodeURIComponent(first.path.split('/').pop()):first.path.split('/').pop())
        :files.get(group.discs[0]).disc.family.replace(/[<>:"/\\|?*\r\n]/g,'_')+'.m3u';
    m3uField('mode').value='switch';m3uField('preserve-states').checked=false;
    m3uField('status').textContent='选择光盘和顺序，再预览实际文件、列表和存档变化。原光盘文件始终保留。';
    renderM3uDiscs();m3uField('dialog').showModal();
}
function renderM3uDiscs(){
    const rows=m3uField('discs');rows.replaceChildren();
    for(const [index,id] of m3uEditor.order.entries()){
        const file=m3uEditor.files.get(id),row=document.createElement('li');
        const check=document.createElement('input');check.type='checkbox';check.checked=m3uEditor.selected.has(id);check.setAttribute('aria-label','包含 '+file.path);
        check.onchange=()=>{if(check.checked)m3uEditor.selected.add(id);else m3uEditor.selected.delete(id);invalidateM3uPreview();};row.appendChild(check);
        const text=document.createElement('span');text.textContent=(index+1)+'. '+file.path;row.appendChild(text);
        for(const [offset,label] of [[-1,'上移'],[1,'下移']]){
            const button=document.createElement('button');button.type='button';button.className='btn btn-muted';button.textContent=label;
            button.disabled=index+offset<0||index+offset>=m3uEditor.order.length;
            button.onclick=()=>{[m3uEditor.order[index],m3uEditor.order[index+offset]]=[m3uEditor.order[index+offset],m3uEditor.order[index]];invalidateM3uPreview();renderM3uDiscs();};row.appendChild(button);
        }
        rows.appendChild(row);
    }
    const selected=m3uField('save-source').value;
    const sources=[...(m3uEditor.group.kind==='m3u'?[m3uEditor.group.members[0]]:[]),...m3uEditor.order];
    m3uField('save-source').replaceChildren(new Option('自动检查，仅无冲突时选择',''),...sources.map(id=>new Option(m3uEditor.files.get(id).path,m3uEditor.files.get(id).path)));
    m3uField('save-source').value=selected;
}
function m3uPayload(){return {playlist_path:discInspection.data.playlist_path,system:discInspection.data.system,group_id:m3uEditor.group.id,
    disc_ids:m3uEditor.order.filter(id=>m3uEditor.selected.has(id)),label:m3uField('label').value,filename:m3uField('filename').value,
    mode:m3uField('mode').value,save_source:m3uField('save-source').value,preserve_states:m3uField('preserve-states').checked,
    thumbnails:getThumbnailsDirectory()};}
async function m3uJob(route,payload){
    if(!beginWorkbenchOperation('m3u'))throw new Error('请等待当前任务');
    m3uEditor.busy=true;m3uField('fields').disabled=true;m3uField('close').disabled=true;
    m3uField('preview').disabled=true;m3uField('apply').disabled=true;
    try{
        const started=await desktopRequest(route,payload);
        return await new Promise((resolve,reject)=>{
            const events=new EventSource('/api/progress?job_id='+encodeURIComponent(started.job_id));
            events.onmessage=event=>{const job=JSON.parse(event.data);
                if(job.error||['failed','cancelled'].includes(job.status)){events.close();reject(new Error(job.error||'已取消'));}
                else if(job.status==='completed'){events.close();resolve({id:started.job_id,result:job.result});}
                else m3uField('status').textContent=job.message||'正在核对…';
            };
            events.onerror=()=>{m3uField('status').textContent='连接中断，正在重连；请等待任务结果，不要重复应用。';};
        });
    }finally{m3uEditor.busy=false;m3uField('fields').disabled=false;m3uField('close').disabled=false;m3uField('preview').disabled=false;endWorkbenchOperation();}
}
function m3uInputsKey(){return JSON.stringify(m3uPayload())+discInspectionKey();}
async function previewM3u(){
    invalidateM3uPreview();const revision=m3uEditor.revision,key=m3uInputsKey();
    try{const {id,result}=await m3uJob('/api/m3u/preview',m3uPayload());if(revision!==m3uEditor.revision || key!==m3uInputsKey())return;
        m3uEditor.previewId=id;m3uEditor.previewKey=key;m3uField('review').hidden=false;m3uField('content').textContent=result.content;
        m3uField('scope').textContent=(result.mode==='switch'?'更新当前列表，替换 '+result.removed_indices.length+' 个入口；':'仅保存 M3U，保留当前列表；')+'目标：'+result.target;
        const details=m3uField('details');details.replaceChildren();
        for(const text of [result.core.message,'电脑备份位置：'+result.backup_root,result.saves.note||'',
            ...(result.saves.states.length?['保留且不迁移即时存档：'+result.saves.states.join('、')]:[]),...result.issues,...result.notes,...result.saves.issues,
            ...result.changes.map(change=>({m3u:'保存 M3U',playlist:'更新当前列表',save_copy:'复制游戏内存档',artwork_copy:'延续原图片'}[change.kind])+' · '+change.path+' · '+change.size+' B'),
            ...result.retained_discs.map(item=>'未选中的原分盘保留独立入口：'+item.path),
            ...result.artwork_copies.map(item=>'保留原图并复制：'+item.source+' → '+item.target),
            ...result.saves.copies.map(copy=>'复制存档：'+copy.source+' → '+copy.target),
            ...result.affected_playlists.map(path=>'受此 M3U 顺序影响的现有列表：'+path)]){
            const line=document.createElement('li');line.textContent=text;details.appendChild(line);
        }
        m3uField('status').textContent=result.issues.length?'有待处理问题，请修改设置后重新预览。':result.can_apply?'方案已就绪；确认后备份并写入。请先退出 RetroArch。':'没有需要应用的变化。';
        m3uField('apply').disabled=!result.can_apply;
    }catch(error){m3uField('status').textContent=error.message;}
}
async function applyM3u(){
    const id=m3uEditor.previewId;if(!id||m3uEditor.busy)return;
    if(m3uEditor.previewKey!==m3uInputsKey()){invalidateM3uPreview();m3uField('status').textContent='方案输入已变化，请重新预览';return;}
    m3uEditor.previewId=null;
    try{const {result}=await m3uJob('/api/m3u/apply',{preview_job_id:id});m3uEditor.changed=true;reflectM3uResult(result);
        m3uField('status').textContent='已完成，原光盘和存档保留。电脑备份：'+result.backup_directory+'。关闭后刷新游戏库。';
        m3uField('review').hidden=true;
    }catch(error){m3uEditor.changed=true;m3uField('status').textContent=error.message+'；请在操作记录查看多盘操作记录。';}
}
async function closeM3uEditor(){
    if(m3uEditor.busy)return;invalidateM3uPreview();m3uField('dialog').close();
    if(m3uEditor.changed){m3uEditor.changed=false;closeDiscInspection();await scanDevice(false);}
}
async function recoverM3u(id,action,mode=''){
    assertWorkbenchIdle();
    const text=mode==='game_rom_update' ? workbenchText(action==='restore'?'恢复旧版 ROM？存档文件保持不变。':'继续此次 ROM 更新？请先退出 RetroArch。',action==='restore'?'Restore the previous ROM? Save files are kept.':'Resume this ROM update? Quit RetroArch first.') : mode.startsWith('game_') ? workbenchText(action==='restore'?'恢复此次列表修改？已复制的游戏文件会保留。':'核对当前列表后继续此次修改？',action==='restore'?'Restore this playlist change? Copied game files will be kept.':'Check the current playlist and continue this change?') : action==='restore'?'恢复此多盘操作？仅移除本次新建且未变化的文件，原光盘与存档不会删除。':'核对当前文件后继续这次未完成操作？';
    if(!await desktopConfirm(text))return;
    const {result}=await m3uJob('/api/m3u/recover',{id,action});
    desktopClearPreview();reflectM3uResult(result);await refreshDesktop();return result;
}
function reflectM3uResult(result){
    if(Number.isInteger(result.playlist_count) && currentDeviceScan){
        const normalize=value=>value.replaceAll('\\','/');
        const entry=currentDeviceScan.playlists.find(item=>normalize(item.path)===normalize(result.playlist_path));
        if(entry){entry.item_count=result.playlist_count;currentDeviceScan.totals.items=currentDeviceScan.playlists.reduce((sum,item)=>sum+item.item_count,0);renderDeviceScan(currentDeviceScan);}
    }
    resetGameLibrary();renderWorkbench();
}
m3uField('fields').addEventListener('input',invalidateM3uPreview);
m3uField('fields').addEventListener('change',invalidateM3uPreview);
m3uField('dialog').addEventListener('cancel',event=>{event.preventDefault();closeM3uEditor();});
