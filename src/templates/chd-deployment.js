/* Separate confirmation for device writes; a conversion result alone authorizes no deployment. */
const chdDeployment={record:null,busy:false,job:null,revision:0,preview:null,key:null,changed:false};
const deployField=name=>document.getElementById('deploy-'+name);
function deploymentPayload(){return {conversion_id:chdDeployment.record.id,system:chdDeployment.record.system||document.getElementById('system_name').value,
    disc_ids:[...deployField('discs').querySelectorAll('input:checked')].map(input=>input.value),mode:deployField('mode').value,
    runtime:{version:deployField('version').value.trim(),confirmed:deployField('tested').checked},scope_confirmed:deployField('scope').checked};}
function deploymentKey(){return JSON.stringify(deploymentPayload())+document.getElementById('playlist_path').value;}
function invalidateDeployment(){chdDeployment.revision++;chdDeployment.preview=null;chdDeployment.key=null;deployField('apply').disabled=true;deployField('review').hidden=true;}
function openChdDeployment(record){
    if(workbench.operation)return;
    Object.assign(chdDeployment,{record,changed:false});invalidateDeployment();
    deployField('origin').textContent='已验证转换记录：'+record.id+' · 原游戏库：'+record.playlist;
    deployField('settings').open=true;deployField('runtime').open=false;deployField('mode').value='copy';deployField('version').value='';deployField('tested').checked=false;deployField('scope').checked=false;
    const discs=deployField('discs');discs.replaceChildren();
    for(const result of record.results.filter(result=>result.status==='content_verified')){
        const label=document.createElement('label');label.className='deploy-check';const input=document.createElement('input');input.type='checkbox';input.value=result.id;input.checked=true;
        label.appendChild(input);const text=document.createElement('span');text.textContent=result.source+' → '+result.output;label.appendChild(text);discs.appendChild(label);
    }
    deployField('status').textContent='默认仅回传副本。更新引用与清理必须先完成运行报告，再核对实际变更。';deployField('dialog').showModal();
}
async function closeChdDeployment(){
    if(chdDeployment.busy)return;invalidateDeployment();deployField('dialog').close();
    if(chdDeployment.changed){chdDeployment.changed=false;resetGameLibrary();desktopClearPreview();await refreshDesktop();if(currentDeviceScan?.connected)await scanDevice(false);}
}
async function deploymentJob(route,payload){
    if(!beginWorkbenchOperation('chd-deploy'))throw new Error('请等待当前任务');
    chdDeployment.busy=true;deployField('fields').disabled=true;deployField('cancel').hidden=false;
    for(const name of ['close','preview','apply'])deployField(name).disabled=true;
    try{
        const started=await desktopRequest(route,payload);chdDeployment.job=started.job_id;
        return await new Promise((resolve,reject)=>{
            const events=new EventSource('/api/progress?job_id='+encodeURIComponent(started.job_id));
            events.onmessage=event=>{const job=JSON.parse(event.data);
                if(['failed','cancelled'].includes(job.status)){events.close();reject(new Error(job.error||'任务已停止，请检查持久记录'));}
                else if(job.status==='completed'){events.close();resolve({id:started.job_id,result:job.result});}
                else deployField('status').textContent=job.message||'正在核对…';
            };
            events.onerror=()=>{deployField('status').textContent='连接中断，正在重连；不会重复提交方案。';};
        });
    }finally{
        chdDeployment.busy=false;chdDeployment.job=null;deployField('fields').disabled=false;deployField('cancel').hidden=true;
        deployField('close').disabled=false;deployField('preview').disabled=false;endWorkbenchOperation();
    }
}
async function cancelChdDeployment(){
    try{if(chdDeployment.job)await desktopRequest('/api/jobs/cancel',{job_id:chdDeployment.job});}
    catch(error){deployField('status').textContent='取消请求未送达：'+error.message+'；任务可能仍在运行。';}
}
async function previewChdDeployment(){
    invalidateDeployment();const revision=chdDeployment.revision,key=deploymentKey();
    try{
        const {id,result}=await deploymentJob('/api/chd/deployment/preview',deploymentPayload());
        if(revision!==chdDeployment.revision||key!==deploymentKey())return;
        chdDeployment.preview=id;chdDeployment.key=key;deployField('review').hidden=false;deployField('settings').open=!result.can_apply;deployField('dialog').scrollTop=0;
        const details=deployField('details');details.replaceChildren();
        for(const text of ['方式：'+({copy:'仅回传；保留原文件与引用',switch:'回传并更新引用；保留原文件',replace:'回传、更新引用并清理有备份且无其他引用的原文件'}[result.mode]),
            '电脑备份：'+result.backup_directory,'镜像空间净变化：'+storageBytes(result.image_delta_bytes)+'；不含电脑备份和元数据备份，电脑同卷备份可能使总可用空间减少',
            ...result.copies.map(item=>'回传并回读：'+item.source+' → '+item.target+(item.created?'':'（已有相同目标，保留）')),
            ...result.reference_changes.map(item=>'备份并更新引用：'+item.path),...result.deletions.map(item=>'有电脑备份后移除：'+item.path),
            ...result.retained.map(item=>'保留共享源：'+item.path+'；引用：'+item.consumers.join('、')),
            ...result.roots.map(path=>'递归引用检查目录：'+path),...result.scope_errors,
            ...result.capacity.map(item=>'空间检查：'+item.path+' · 需要 '+storageBytes(item.required)+'／可用 '+storageBytes(item.free)),
            ...result.runtime.cores.map(core=>'受影响核心：'+core),'核心版本报告：'+(result.runtime.version||'未提供')+'；记录来源为用户报告，不等于软件已验证安装',...result.issues]){
            const line=document.createElement('li');line.textContent=text;details.appendChild(line);
        }
        deployField('status').textContent=result.can_apply?'方案就绪。确认执行前请退出 RetroArch。':'有待处理项，当前方案不能执行。';deployField('apply').disabled=!result.can_apply;
    }catch(error){deployField('status').textContent=error.message;}
}
async function applyChdDeployment(){
    const id=chdDeployment.preview;if(!id||chdDeployment.busy)return;
    if(chdDeployment.key!==deploymentKey()){invalidateDeployment();deployField('status').textContent='输入或游戏库已变化，请重新预览。';return;}
    chdDeployment.preview=null;
    try{
        const {result}=await deploymentJob('/api/chd/deployment/apply',{preview_job_id:id});chdDeployment.changed=true;
        deployField('status').textContent='已完成。电脑备份：'+result.backup_directory+'。可从操作记录还原原镜像和引用。';deployField('review').hidden=true;
    }catch(error){chdDeployment.changed=true;deployField('status').textContent=error.message+'；请在操作记录检查 CHD 回传记录。';}
}
async function recoverChdDeployment(id,action){
    assertWorkbenchIdle();
    if(!await desktopConfirm(action==='restore'?'恢复此 CHD 操作？先还原原镜像，再还原引用，最后移除本次新建且未变化的 CHD。':'核对电脑备份、目标与引用后继续原方案？'))return;
    try{
        await deploymentJob('/api/chd/deployment/recover',{id,action});resetGameLibrary();desktopClearPreview();await refreshDesktop();
    }catch(error){await refreshDesktop();showStatus(error.message,'error');}
}
