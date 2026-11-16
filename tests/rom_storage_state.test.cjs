const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
function harness(){
    const fields=new Map(),events=[];
    const field=id=>{if(!fields.has(id))fields.set(id,{value:'',disabled:false,hidden:true,open:true,textContent:'',options:[],replaceChildren(){},querySelectorAll(){return [];}});return fields.get(id);};
    const c={console,Set,JSON,document:{getElementById:field},workbench:{operation:null},
        beginWorkbenchOperation(op){if(c.workbench.operation)return false;c.workbench.operation=op;return true;},endWorkbenchOperation(){c.workbench.operation=null;},
        desktopRequest:async()=>({job_id:'active'}),EventSource:class{constructor(){events.push(this);}close(){this.closed=true;}}};
    vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/templates/rom-storage.js'),'utf8')+'\nglobalThis.store=romStorage',c);
    return {c,field:id=>field('rom-storage-'+id),events};
}
const deferred=()=>{let resolve;return {promise:new Promise(r=>resolve=r),resolve};};
test('stale analysis never enables conversion after library change',async()=>{
    const {c,field}=harness(),pending=deferred();let key='A';c.romKey=()=>key;c.romPayload=()=>({});c.romJob=()=>pending.promise;
    const task=c.analyzeRomStorage();key='B';pending.resolve({id:'old',result:{}});await task;
    assert.equal(c.store.analysis,null);assert.equal(field('convert').disabled,true);
});
test('one-shot conversion sends only server plan ID and selected IDs',async()=>{
    const {c}=harness(),pending=deferred();c.romKey=()=> 'same';Object.assign(c.store,{analysis:'plan',key:'same',selected:new Set(['rom'])});let count=0;
    c.romJob=(route,payload)=>{count++;assert.equal(route,'/api/rom-storage/convert');assert.deepEqual(JSON.parse(JSON.stringify(payload)),{analysis_job_id:'plan',file_ids:['rom']});return pending.promise;};
    const task=c.convertRomStorage();await c.convertRomStorage();assert.equal(count,1);pending.resolve({result:null});await task;
    assert.equal(c.store.analysis,null);
});
test('changed directory blocks submission',async()=>{
    const {c,field}=harness();Object.assign(c.store,{analysis:'plan',key:'old'});c.romKey=()=> 'new';
    c.romJob=()=>assert.fail('stale request');await c.convertRomStorage();assert.equal(c.store.analysis,null);assert.match(field('status').textContent,/重新分析/);
});
test('older storage response and cancelled picker cannot replace current directory',async()=>{
    const {c,field}=harness(),first=deferred(),second=deferred();let calls=0;c.desktopRequest=()=>++calls===1?first.promise:second.promise;
    const a=c.browseRomStorage('internal');const b=c.browseRomStorage('sd');
    second.resolve({path:'sd/SS',parent:'sd',directories:[]});await b;
    first.resolve({path:'internal/NES',parent:'internal',directories:[]});await a;
    assert.equal(c.store.browsePath,'sd/SS');assert.equal(field('path').textContent,'sd/SS');
    const third=deferred();c.desktopRequest=()=>third.promise;const task=c.browseRomStorage('old');c.closeRomPicker();third.resolve({path:'old',directories:[]});await task;
    assert.equal(c.store.browsePath,null);assert.equal(field('analyze').disabled,false);
});
test('start analysis commits the browsed folder without an extra use-directory click',async()=>{
    const {c,field}=harness();field('picker').hidden=false;c.store.pickField='source';c.store.browsePath='sd/Roms/SS';
    c.romJob=async()=>{assert.equal(field('source').value,'sd/Roms/SS');assert.equal(field('target').value,'sd/Roms/SS');throw new Error('stop after selection');};
    await c.analyzeRomStorage();assert.equal(field('picker').hidden,true);assert.match(field('status').textContent,/stop/);
});
test('SSE reconnect retains lock and cancel targets the existing job',async()=>{
    const {c,events}=harness(),calls=[];c.desktopRequest=async(route,payload)=>{calls.push({route,payload});return {job_id:'active'};};
    const task=c.romJob('/api/rom-storage/convert',{});await new Promise(resolve=>setImmediate(resolve));events[0].onerror();assert.equal(c.store.busy,true);
    await c.cancelRomStorage();assert.equal(calls[1].payload.job_id,'active');events[0].onmessage({data:JSON.stringify({status:'cancelled',error:'fixture'})});
    await assert.rejects(task,/fixture/);assert.equal(c.workbench.operation,null);assert.equal(c.store.busy,false);
});
test('MTP picker offers both storages of this device without scan-dialog state',async()=>{
    const {c,field}=harness();c.romPayload=()=>({playlist_path:'mtp://device/00010001/RetroArch/playlists/GBA.lpl'});
    c.libraryHome={device:{storages:[{transport:'mtp',label:'本机',path:'mtp://device/00010001/RetroArch'},
        {transport:'mtp',label:'存储卡',path:'mtp://device/00020001/RetroArch'},
        {transport:'mtp',label:'别的设备',path:'mtp://other/00010001/RetroArch'}]}};
    c.Option=function(label,value){return {label,value};};field('storage').replaceChildren=(...options)=>field('storage').options=options;
    c.desktopRequest=async()=>({path:'mtp://device/00010001/',parent:'mtp://device/00010001/',directories:[]});
    await c.pickRomStorage('source');assert.equal(field('storage').options.length,2);
    assert.equal(field('storage').options[1].value,'mtp://device/00020001/');assert.equal(field('picker').hidden,false);
});
