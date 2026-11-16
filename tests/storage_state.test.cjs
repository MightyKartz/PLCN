const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
function harness(){
    const fields=new Map(),events=[];
    const field=id=>{if(!fields.has(id))fields.set(id,{value:'',disabled:false,hidden:false,textContent:'',replaceChildren(){},querySelectorAll(){return [];}});return fields.get(id);};
    const c={console,Set,JSON,document:{getElementById:field},workbench:{operation:null},
        beginWorkbenchOperation(op){if(c.workbench.operation)return false;c.workbench.operation=op;return true;},endWorkbenchOperation(){c.workbench.operation=null;},
        desktopRequest:async()=>({job_id:'active'}),EventSource:class{constructor(){events.push(this);}close(){this.closed=true;}}};
    vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/templates/storage.js'),'utf8')+'\nglobalThis.store=storageTask',c);
    return {c,field:id=>field('storage-'+id),events};
}
const deferred=()=>{let resolve;return {promise:new Promise(r=>resolve=r),resolve};};
test('old analysis cannot re-enable conversion when library or settings changed',async()=>{
    const {c,field}=harness(),pending=deferred();let input='A';c.storageKey=()=>input;c.storagePayload=()=>({});c.storageJob=()=>pending.promise;
    const task=c.analyzeStorage();input='B';pending.resolve({id:'old',result:{}});await task;
    assert.equal(c.store.analysis,null);assert.equal(field('convert').disabled,true);
});
test('conversion consumes analysis once and does not send client paths or tool',async()=>{
    const {c}=harness(),pending=deferred();c.storageKey=()=> 'same';Object.assign(c.store,{analysis:'plan',key:'same',selected:new Set(['disc'])});let count=0;
    c.storageJob=(route,payload)=>{count++;assert.deepEqual(JSON.parse(JSON.stringify(payload)),{analysis_job_id:'plan',disc_ids:['disc']});return pending.promise;};
    const task=c.convertStorage();await c.convertStorage();assert.equal(count,1);pending.resolve({result:null});await task;
    assert.equal(c.store.analysis,null);
});
test('library change blocks a ready analysis without submitting',async()=>{
    const {c,field}=harness();Object.assign(c.store,{analysis:'plan',key:'old'});c.storageKey=()=> 'new';
    c.storageJob=()=>assert.fail('stale request');await c.convertStorage();assert.equal(c.store.analysis,null);assert.match(field('status').textContent,/重新分析/);
});
test('SSE reconnect keeps lock and cancellation addresses the existing job',async()=>{
    const {c,field,events}=harness();const calls=[];c.desktopRequest=async(route,payload)=>{calls.push({route,payload});return {job_id:'active'};};
    const task=c.storageJob('/api/chd/convert',{});await new Promise(resolve=>setImmediate(resolve));
    events[0].onerror();assert.equal(c.store.busy,true);assert.equal(field('close').disabled,true);
    await c.cancelStorageTask();assert.equal(calls.length,2);assert.equal(calls[1].payload.job_id,'active');
    events[0].onmessage({data:JSON.stringify({status:'cancelled',error:'cancelled'})});await assert.rejects(task,/cancelled/);
    assert.equal(c.workbench.operation,null);assert.equal(c.store.busy,false);assert.equal(events[0].closed,true);
});

test('reducing the selected batch enables conversion when the full batch exceeds free space',()=>{
    const {c,field}=harness();const size=100000000;
    c.store.report={can_convert:true,free_bytes:64*1024*1024+6*size,rows:[{id:'one',source_bytes:size},{id:'two',source_bytes:size}]};
    c.store.selected=new Set(['one','two']);c.updateStorageSelection();assert.equal(field('convert').disabled,true);
    c.store.selected.delete('two');c.updateStorageSelection();assert.equal(field('convert').disabled,false);
});
