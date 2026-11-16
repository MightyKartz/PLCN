/* A server-owned move/ZIP plan; opening this dialog does not authorize writes. */
const romRelocation={source:null,busy:false,job:null,revision:0,preview:null,key:null,changed:false};
const relocateField=name=>document.getElementById('relocate-'+name);
function relocationPayload(){return {...romRelocation.source,mode:relocateField('mode').value,
    runtime:{version:relocateField('version').value.trim(),confirmed:relocateField('tested').checked},scope_confirmed:relocateField('scope').checked};}
function relocationKey(){return JSON.stringify(relocationPayload())+document.getElementById('playlist_path').value;}
function invalidateRelocation(){romRelocation.revision++;romRelocation.preview=null;romRelocation.key=null;relocateField('apply').disabled=true;relocateField('review').hidden=true;}
function openRomRelocation(source){
    if(workbench.operation)return;
    romRelocation.source=source;romRelocation.changed=false;invalidateRelocation();
    relocateField('origin').textContent='源游戏库：'+source.playlist+'；保持原文件名，不覆盖冲突，不清理原目录。';
    relocateField('mode').value='copy';relocateField('version').value='';relocateField('tested').checked=false;relocateField('scope').checked=false;relocateField('settings').open=true;
    relocateField('status').textContent='默认仅复制。请先预览目标、引用范围和空间，再确认执行。';relocateField('dialog').showModal();
}
async function closeRomRelocation(){
    if(romRelocation.busy)return;invalidateRelocation();relocateField('dialog').close();
    if(romRelocation.changed){romRelocation.changed=false;resetGameLibrary();desktopClearPreview();await refreshDesktop();if(currentDeviceScan?.connected)await scanDevice(false);}
}
async function relocationJob(route,payload){
    if(!beginWorkbenchOperation('rom-relocation'))throw new Error('请等待当前任务');
    romRelocation.busy=true;relocateField('fields').disabled=true;relocateField('cancel').hidden=false;
    for(const name of ['close','preview','apply'])relocateField(name).disabled=true;
    try{
        const started=await desktopRequest(route,payload);romRelocation.job=started.job_id;
        return await new Promise((resolve,reject)=>{
            const events=new EventSource('/api/progress?job_id='+encodeURIComponent(started.job_id));
            events.onmessage=event=>{const job=JSON.parse(event.data);
                if(['failed','cancelled'].includes(job.status)){events.close();reject(new Error(job.error||'操作已停止，请核对任务记录'));}
                else if(job.status==='completed'){events.close();resolve({id:started.job_id,result:job.result});}
                else relocateField('status').textContent=job.message||'正在处理…';
            };
            events.onerror=()=>{relocateField('status').textContent='连接中断，正在重连；不会重复提交方案。';};
        });
    }finally{
        romRelocation.job=null;romRelocation.busy=false;relocateField('fields').disabled=false;relocateField('cancel').hidden=true;
        relocateField('close').disabled=false;relocateField('preview').disabled=false;endWorkbenchOperation();
    }
}
async function cancelRomRelocation(){
    try{if(romRelocation.job)await desktopRequest('/api/jobs/cancel',{job_id:romRelocation.job});}
    catch(error){relocateField('status').textContent='取消请求未送达：'+error.message;}
}
async function previewRomRelocation(){
    invalidateRelocation();const revision=romRelocation.revision,key=relocationKey();
    try{
        const {id,result}=await relocationJob('/api/rom-storage/relocation/preview',relocationPayload());
        if(revision!==romRelocation.revision||key!==relocationKey())return;
        romRelocation.preview=id;romRelocation.key=key;relocateField('review').hidden=false;relocateField('settings').open=!result.can_apply;
        const details=relocateField('details');details.replaceChildren();
        for(const text of ['方式：'+({copy:'仅复制；原文件与引用保留',switch:'复制并更新引用；原文件保留',replace:'复制、更新引用并清理有备份的原文件'}[result.mode]),
            '电脑备份：'+result.backup_directory,'本次源／目标文件净释放：'+storageBytes(result.image_delta_bytes)+'；不含电脑备份和元数据备份，同卷备份可能减少总可用空间',
            ...result.copies.map(item=>'复制并回读校验：'+item.source+' → '+item.target+(item.created?'':'（复用此前复制操作的已校验目标）')),
            ...result.reference_changes.map(item=>'备份并更新引用：'+item.path),
            ...result.deletions.map(item=>'校验与备份完成后移除：'+item.path),
            ...result.retained.map(item=>'保留仍有引用的源文件：'+item.path+' · '+item.consumers.join('、')),
            '存档检查：'+({checked:'固定全局目录已核对，原存档位置保持不变',pending:'尚有待处理项',not_required:'仅复制，不切换入口'}[result.saves.status]),
            ...result.saves.directories.map(path=>'保留存档目录：'+path),...result.saves.issues,
            ...result.roots.map(path=>'递归引用范围：'+path),...result.scope_errors,
            ...result.capacity.map(item=>'空间：'+storageBytes(item.required)+'／可用 '+storageBytes(item.free)+' · '+item.path),
            '核心版本报告：'+(result.runtime.version||'未提供')+'（用户报告，未验证安装版本）',...result.issues])desktopElement('li',text,details);
        relocateField('status').textContent=result.can_apply?'方案就绪。请核对实际文件与引用，再确认执行。':'有待处理项，当前方案不能执行。';relocateField('apply').disabled=!result.can_apply;relocateField('dialog').scrollTop=0;
    }catch(error){relocateField('status').textContent=error.message;}
}
async function applyRomRelocation(){
    const id=romRelocation.preview;if(!id||romRelocation.busy)return;
    if(romRelocation.key!==relocationKey()){invalidateRelocation();relocateField('status').textContent='目录、列表或方式已变化，请重新预览';return;}
    romRelocation.preview=null;
    try{
        const {result}=await relocationJob('/api/rom-storage/relocation/apply',{preview_job_id:id});romRelocation.changed=true;
        relocateField('review').hidden=true;relocateField('status').textContent='已完成。电脑备份：'+result.backup_directory+'；任务与恢复可还原原文件和引用。'+(result.mode==='copy'?'验证目标运行后，可修改执行方式并重新预览，或稍后从任务记录继续。':'');
    }catch(error){romRelocation.changed=true;relocateField('status').textContent=error.message+'；请从设置 → 任务与恢复查看整理记录。';}
}
async function recoverRomRelocation(id,action){
    assertWorkbenchIdle();if(!await desktopConfirm(action==='restore'?'恢复原目录与引用？先还原源文件，再还原引用和关联；仍有新引用的输出会保留。':'核对备份、目标、引用和存档设置后继续此方案？'))return;
    try{await relocationJob('/api/rom-storage/relocation/recover',{id,action});resetGameLibrary();desktopClearPreview();await refreshDesktop();}
    catch(error){await refreshDesktop();showStatus(error.message,'error');}
}
