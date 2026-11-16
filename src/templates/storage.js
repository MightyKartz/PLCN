/* Local-copy storage workflow: source/library/input changes invalidate the server analysis. */
const storageTask={busy:false,job:null,analysis:null,key:null,revision:0,report:null,selected:new Set()};
const storageField=name=>document.getElementById('storage-'+name);
const storageBytes=value=>value==null?'未知':value<1024?value+' B':value<1024*1024?(value/1024).toFixed(2)+' KiB':(value/1024/1024).toFixed(2)+' MiB';
function storagePayload(){return {playlist_path:document.getElementById('playlist_path').value,system:document.getElementById('system_name').value,
    workspace:storageField('workspace').value.trim(),tool:storageField('tool').value.trim()};}
function storageKey(){return JSON.stringify(storagePayload());}
function invalidateStoragePlan(){storageTask.revision++;storageTask.analysis=null;storageTask.key=null;storageTask.report=null;storageTask.selected.clear();storageField('analysis').hidden=true;storageField('convert').disabled=true;}
function updateStorageSelection(){
    const report=storageTask.report;if(!report)return;
    const selected=report.rows.filter(row=>storageTask.selected.has(row.id));
    const required=2*selected.reduce((sum,row)=>sum+row.source_bytes,0)+3*Math.max(0,...selected.map(row=>row.source_bytes))+64*1024*1024;
    storageField('budget').textContent='已选 '+selected.length+' 张；电脑可用 '+storageBytes(report.free_bytes)+'；所选工作空间预算 '+storageBytes(required);
    const ready=report.can_convert&&selected.length&&report.free_bytes>=required;
    storageField('convert').disabled=!ready;
    storageField('status').textContent=ready?'请核对所选光盘与输出位置，确认后开始电脑转换。':!selected.length?'请选择可转换的光盘。':report.free_bytes<required?'电脑空间不足，请减少所选光盘或更换工作目录。':'工具尚未就绪，请核对提示。';
}
function openStorageOptimization(){
    if(workbench.operation)return;
    invalidateStoragePlan();storageField('result').hidden=true;storageField('settings').open=true;
    storageField('status').textContent='仅分析当前选中列表；首版转换本地 BINARY 2352 扇区 CUE，已有 CHD 自动跳过。';
    storageField('dialog').showModal();
}
function closeStorageOptimization(){if(storageTask.busy)return;invalidateStoragePlan();storageField('dialog').close();}
async function pickStoragePath(name,kind){
    try{const result=await desktopRequest('/api/desktop/pick',{kind,initial:storageField(name).value});if(result.path){storageField(name).value=result.path;invalidateStoragePlan();}}
    catch(error){storageField('status').textContent=error.message;}
}
async function storageJob(route,payload){
    if(!beginWorkbenchOperation('storage'))throw new Error('请等待当前任务');
    storageTask.busy=true;storageField('fields').disabled=true;
    for(const name of ['close','analyze','convert'])storageField(name).disabled=true;
    storageField('cancel').hidden=false;
    for(const input of storageField('rows').querySelectorAll('input'))input.disabled=true;
    try{
        const started=await desktopRequest(route,payload);storageTask.job=started.job_id;
        return await new Promise((resolve,reject)=>{
            const events=new EventSource('/api/progress?job_id='+encodeURIComponent(started.job_id));
            events.onmessage=event=>{const job=JSON.parse(event.data);
                if(['failed','cancelled'].includes(job.status)){events.close();reject(new Error(job.error||'任务已取消；已验证结果见任务与恢复'));}
                else if(job.status==='completed'){events.close();resolve({id:started.job_id,result:job.result});}
                else storageField('status').textContent=job.message||'正在处理…';
            };
            events.onerror=()=>{storageField('status').textContent='连接中断，正在重连；任务不会重复提交。';};
        });
    }finally{
        storageTask.job=null;storageTask.busy=false;storageField('fields').disabled=false;
        storageField('close').disabled=false;storageField('analyze').disabled=false;storageField('cancel').hidden=true;endWorkbenchOperation();
        for(const input of storageField('rows').querySelectorAll('input'))input.disabled=!storageTask.analysis;
    }
}
async function cancelStorageTask(){
    try{if(storageTask.job)await desktopRequest('/api/jobs/cancel',{job_id:storageTask.job});}
    catch(error){storageField('status').textContent='取消请求未送达：'+error.message+'；任务仍在运行，可重试取消。';}
}
async function analyzeStorage(){
    invalidateStoragePlan();storageField('result').hidden=true;
    const revision=storageTask.revision,key=storageKey();
    try{
        const {id,result}=await storageJob('/api/chd/analyze',storagePayload());
        if(revision!==storageTask.revision||key!==storageKey())return;
        storageTask.analysis=id;storageTask.key=key;storageTask.report=result;storageField('analysis').hidden=false;storageField('settings').open=false;
        const summary=storageField('summary');summary.replaceChildren();
        const facts=['关联文件已知体积：'+storageBytes(result.observed_bytes)+'；可转换源文件去重：'+storageBytes(result.input_bytes),
            '电脑可用：'+storageBytes(result.free_bytes)+'；保守工作空间预算：'+storageBytes(result.required_bytes),
            '压缩后大小与节省比例：未知；原文件保留，掌机实际释放空间为 0',
            '输出目录：'+result.output_directory];
        for(const text of facts){const line=document.createElement('p');line.textContent=text;summary.appendChild(line);}
        const detail=document.createElement('details'),heading=document.createElement('summary');heading.textContent='工具信息与分析范围';detail.appendChild(heading);summary.appendChild(detail);
        for(const text of [result.tool.available?'chdman '+result.tool.version+' · '+result.tool.path:result.tool.message,
            result.tool.message,result.device_space.message,
            '列表引用检查：'+(result.coverage.errors.length?'存在未读列表；不据此替换或清理':'当前列表目录'),result.note]){
            const line=document.createElement('p');line.textContent=text;detail.appendChild(line);
        }
        const rows=storageField('rows');rows.replaceChildren();
        for(const row of result.rows){
            const article=document.createElement('article');article.className='storage-row';rows.appendChild(article);
            const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.checked=row.eligible;check.disabled=!row.eligible;
            if(row.eligible)storageTask.selected.add(row.id);
            check.onchange=()=>{if(check.checked)storageTask.selected.add(row.id);else storageTask.selected.delete(row.id);updateStorageSelection();};
            label.appendChild(check);const title=document.createElement('strong');title.textContent=row.path;label.appendChild(title);article.appendChild(label);
            for(const text of [row.format.toUpperCase()+(row.eligible?' → CHD':' · 不转换')+' · '+storageBytes(row.source_bytes??row.size),...(row.eligible?['输出文件：'+row.output_name]:[]),...row.issues,...row.shared_sources.map(path=>'多个光盘共享源文件，按唯一文件统计且不清理：'+path),
                ...row.core.map(core=>(core.declares_chd?'官方声明支持 CHD':'CHD 支持未知')+' · '+core.path+'；安装版本和运行未验证'),
                '直接列表引用 '+row.references.length+' 项；原文件与引用始终保留']){
                const line=document.createElement('p');line.textContent=text;article.appendChild(line);
            }
        }
        updateStorageSelection();
    }catch(error){storageField('status').textContent=error.message;}
}
async function convertStorage(){
    const id=storageTask.analysis;
    if(!id||storageTask.busy)return;
    if(storageTask.key!==storageKey()){invalidateStoragePlan();storageField('status').textContent='列表或配置变化，请重新分析。';return;}
    const selected=[...storageTask.selected];storageTask.analysis=null;
    try{
        const {result}=await storageJob('/api/chd/convert',{analysis_job_id:id,disc_ids:selected});
        const panel=storageField('result');panel.replaceChildren();panel.hidden=false;storageField('analysis').hidden=true;storageField('dialog').scrollTop=0;
        for(const text of ['电脑转换已完成，输出目录：'+result.output_directory,
            ...result.results.map(row=>'内容已比对 · '+row.output+' · '+storageBytes(row.input_bytes)+' → '+storageBytes(row.output_bytes)),
            '通过 CHD verify 与解压后的逐轨扇区比对；尚未验证核心加载、换盘或存档。列表和原文件未修改。']){
            const line=document.createElement('p');line.textContent=text;panel.appendChild(line);
        }
        storageField('status').textContent='已完成。原文件保留；任务记录已保存，可在设置 → 任务与恢复查看。';
    }catch(error){storageField('status').textContent=error.message+'；已验证输出与错误记录见设置 → 任务与恢复。';}
}
