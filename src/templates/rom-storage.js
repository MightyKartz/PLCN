/* Stage 4A owns its plan, selection and directory browser independently of CHD. */
const romStorage={busy:false,job:null,analysis:null,key:null,revision:0,report:null,selected:new Set(),pickerRevision:0,browsePath:null,parent:null,pickField:null};
const romField=name=>document.getElementById('rom-storage-'+name);
function romPayload(){return {playlist_path:document.getElementById('playlist_path').value,system:document.getElementById('system_name').value,
    source_directory:romField('source').value,target_directory:romField('target').value,workspace:romField('workspace').value.trim()};}
function romKey(){return JSON.stringify(romPayload());}
function invalidateRomStorage(){romStorage.revision++;romStorage.analysis=null;romStorage.key=null;romStorage.report=null;romStorage.selected.clear();romField('analysis').hidden=true;romField('convert').disabled=true;romField('result').hidden=true;}
function closeRomPicker(){romStorage.pickerRevision++;romStorage.browsePath=null;romField('picker').hidden=true;if(!romStorage.busy)romField('analyze').disabled=false;}
function openRomStorage(){
    if(workbench.operation)return;
    invalidateRomStorage();closeRomPicker();romField('settings').open=true;romField('source').value='';romField('target').value='';
    romField('status').textContent='选择源目录和主机平铺目标；分析不会移动游戏。ZIP 仅生成电脑副本。';
    romField('dialog').showModal();
}
function closeRomStorage(){if(romStorage.busy)return;invalidateRomStorage();closeRomPicker();romField('dialog').close();}
async function pickRomWorkspace(){
    const revision=romStorage.revision;
    try{const result=await desktopRequest('/api/desktop/pick',{kind:'directory',initial:romField('workspace').value});
        if(revision!==romStorage.revision||!romField('dialog').open)return;
        if(result.path){romField('workspace').value=result.path;invalidateRomStorage();}
    }catch(error){if(revision===romStorage.revision)romField('status').textContent=error.message;}
}
async function pickRomStorage(name){
    invalidateRomStorage();const playlist=romPayload().playlist_path,revision=++romStorage.pickerRevision;romStorage.pickField=name;
    try{
        if(!playlist.startsWith('mtp://')){
            const result=await desktopRequest('/api/desktop/pick',{kind:'directory',initial:romField(name).value});
            if(revision!==romStorage.pickerRevision||!romField('dialog').open)return;
            if(result.path){romField(name).value=result.path;if(name==='source'&&!romField('target').value)romField('target').value=result.path;invalidateRomStorage();}
            return;
        }
        const serial=playlist.split('/')[2];
        const storages=(libraryHome.device?.storages||libraryHome.data?.sources||[])
            .filter(source=>source.transport==='mtp'&&source.path.split('/')[2]===serial)
            .map(source=>({label:source.label,root:source.path.split('/').slice(0,4).join('/')+'/'}));
        if(!storages.length)throw new Error('当前设备的存储信息未就绪，请返回主界面重新检测');
        const select=romField('storage');select.replaceChildren(...storages.map(storage=>new Option(storage.label,storage.root)));
        romField('picker').hidden=false;
        await browseRomStorage(romField(name).value||storages[0].root);
    }catch(error){if(revision===romStorage.pickerRevision)romField('status').textContent=error.message;}
}
async function browseRomStorage(path){
    const revision=++romStorage.pickerRevision;romStorage.browsePath=null;
    romField('use').disabled=true;romField('analyze').disabled=true;romField('up').disabled=true;romField('directories').replaceChildren();
    try{
        const result=await desktopRequest('/api/content/directories?path='+encodeURIComponent(path));
        if(revision!==romStorage.pickerRevision||!romField('dialog').open||romStorage.busy)return;
        romStorage.browsePath=result.path;romStorage.parent=result.parent;romField('path').textContent=result.path;
        for(const option of romField('storage').options)if(result.path===option.value||result.path.startsWith(option.value.replace(/\/$/,'')+'/'))romField('storage').value=option.value;
        for(const directory of result.directories){const button=desktopElement('button',directory.name,romField('directories'));button.type='button';button.className='btn btn-muted';button.onclick=()=>browseRomStorage(directory.path);}
        romField('use').disabled=false;romField('up').disabled=result.parent===result.path;
    }catch(error){if(revision===romStorage.pickerRevision)romField('status').textContent=error.message;}
    finally{if(revision===romStorage.pickerRevision)romField('analyze').disabled=false;}
}
function chooseRomStorage(){
    if(!romStorage.browsePath)return false;
    romField(romStorage.pickField).value=romStorage.browsePath;
    if(romStorage.pickField==='source'&&!romField('target').value)romField('target').value=romStorage.browsePath;
    closeRomPicker();invalidateRomStorage();return true;
}
function updateRomSelection(){
    const report=romStorage.report;if(!report)return;
    const selected=report.rows.filter(row=>romStorage.selected.has(row.id));
    const required=3*selected.reduce((sum,row)=>sum+row.size,0)+64*1024*1024;
    romField('budget').textContent='已选 '+selected.length+' 个 ROM；电脑预算 '+storageBytes(required)+'；可用 '+storageBytes(report.free_bytes);
    romField('convert').disabled=romStorage.busy||!romStorage.analysis||!selected.length||required>report.free_bytes;
}
async function romJob(route,payload){
    if(!beginWorkbenchOperation('rom-storage'))throw new Error('请等待当前任务');
    romStorage.busy=true;romField('fields').disabled=true;
    for(const name of ['close','analyze','convert'])romField(name).disabled=true;
    for(const input of romField('rows').querySelectorAll('input'))input.disabled=true;
    romField('cancel').hidden=false;
    try{
        const started=await desktopRequest(route,payload);romStorage.job=started.job_id;
        return await new Promise((resolve,reject)=>{
            const events=new EventSource('/api/progress?job_id='+encodeURIComponent(started.job_id));
            events.onmessage=event=>{const job=JSON.parse(event.data);
                if(['failed','cancelled'].includes(job.status)){events.close();reject(new Error(job.error||'任务已取消'));}
                else if(job.status==='completed'){events.close();resolve({id:started.job_id,result:job.result});}
                else romField('status').textContent=job.message||'处理中…';
            };
            events.onerror=()=>{romField('status').textContent='连接中断，正在重连；任务不会重复提交。';};
        });
    }finally{
        romStorage.job=null;romStorage.busy=false;romField('fields').disabled=false;
        romField('close').disabled=false;romField('analyze').disabled=false;romField('cancel').hidden=true;endWorkbenchOperation();
        for(const input of romField('rows').querySelectorAll('input'))input.disabled=!romStorage.analysis;
    }
}
async function cancelRomStorage(){
    try{if(romStorage.job)await desktopRequest('/api/jobs/cancel',{job_id:romStorage.job});}
    catch(error){romField('status').textContent='取消请求未送达：'+error.message;}
}
async function analyzeRomStorage(){
    if(!romField('picker').hidden&&!chooseRomStorage()){romField('status').textContent='请等待目录读取完成';return;}
    invalidateRomStorage();const revision=romStorage.revision,key=romKey();
    try{
        const {id,result}=await romJob('/api/rom-storage/analyze',romPayload());
        if(revision!==romStorage.revision||key!==romKey())return;
        romStorage.analysis=id;romStorage.key=key;romStorage.report=result;romField('analysis').hidden=false;romField('settings').open=false;
        const summary=romField('summary');summary.replaceChildren();
        const counts={};for(const row of result.rows)counts[row.layout]=(counts[row.layout]||0)+1;
        for(const line of ['可平铺候选 '+(counts.candidate||0)+' · 已在主机目录 '+(counts.already_flat||0)+' · 同名冲突 '+(counts.conflict||0)+' · 保留目录例外 '+(counts.keep||0),
            '目标：'+result.target_directory,'电脑输出：'+result.output_directory,result.note])desktopElement('p',line,summary);
        romField('rows').replaceChildren();
        for(const row of result.rows){
            const article=desktopElement('article',undefined,romField('rows'));article.className='storage-row';article.dataset.layout=row.layout;
            const label=desktopElement('label',undefined,article),check=document.createElement('input');check.type='checkbox';check.disabled=!row.zip_eligible;check.checked=row.zip_eligible;
            if(row.zip_eligible)romStorage.selected.add(row.id);
            check.onchange=()=>{if(check.checked)romStorage.selected.add(row.id);else romStorage.selected.delete(row.id);updateRomSelection();};
            label.appendChild(check);desktopElement('strong',row.name,label);
            for(const line of [({candidate:'可平铺候选（移动与引用待后续确认）',already_flat:'已在主机目录',conflict:'同名冲突 · 保留原文件',keep:'保留目录结构'}[row.layout])+' · '+storageBytes(row.size),
                '源：'+row.source,...(row.layout!=='keep'?['平铺目标：'+row.target]:[]),...row.issues,
                row.zip_eligible?'可生成单成员 ZIP；保留文件名，解压内容逐字节核对':'本轮不生成 ZIP',
                ...row.cores.map(core=>core.declares_zip_extraction?'上游声明可解包 · '+core.path:'该核心解包支持未核对 · '+core.path)])desktopElement('p',line,article);
        }
        updateRomSelection();romField('status').textContent='分析完成。核对冲突与例外后，可生成所选 ROM 的电脑副本。';
    }catch(error){romField('status').textContent=error.message;}
}
async function convertRomStorage(){
    const id=romStorage.analysis;if(!id||romStorage.busy)return;
    if(romStorage.key!==romKey()){invalidateRomStorage();romField('status').textContent='列表或目录已变化，请重新分析';return;}
    romStorage.analysis=null;
    try{
        const {result}=await romJob('/api/rom-storage/convert',{analysis_job_id:id,file_ids:[...romStorage.selected]});
        const panel=romField('result');panel.replaceChildren();panel.hidden=false;romField('analysis').hidden=true;
        for(const line of ['ZIP 电脑副本已完成 · 掌机节省空间 0 B','输出目录：'+result.output_directory,
            ...result.results.map(row=>row.output+' · '+storageBytes(row.input_bytes)+' → '+storageBytes(row.output_bytes)+' · 解压内容逐字节一致'),
            '原文件和列表保留；核心加载、存档及设备替换尚未验收。任务记录可在设置 → 任务与恢复查看。'])desktopElement('p',line,panel);
        romField('status').textContent='已完成电脑副本与解压校验。';romField('dialog').scrollTop=romField('dialog').scrollHeight;
    }catch(error){romField('status').textContent=error.message+'；已完成副本与中断记录见任务与恢复。';}
}
