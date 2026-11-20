const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
function harness(){
    const fields=new Map(),events=[];
    const field=id=>{if(!fields.has(id))fields.set(id,{value:'',checked:false,disabled:false,hidden:false,textContent:'',replaceChildren(){},querySelectorAll(){return [];}});return fields.get(id);};
    const c={console,Set,JSON,document:{getElementById:field},workbench:{operation:null},
        beginWorkbenchOperation(op){if(c.workbench.operation)return false;c.workbench.operation=op;return true;},endWorkbenchOperation(){c.workbench.operation=null;},
        desktopRequest:async()=>({job_id:'active'}),EventSource:class{constructor(){events.push(this);}close(){this.closed=true;}},resetGameLibrary(){},desktopClearPreview(){},refreshDesktop:async()=>{},scanDevice:async()=>{},currentDeviceScan:null};
    vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/templates/chd-deployment.js'),'utf8')+'\nglobalThis.store=chdDeployment',c);
    return {c,field:id=>field('deploy-'+id),events};
}
const deferred=()=>{let resolve;return {promise:new Promise(r=>resolve=r),resolve};};
test('late deployment preview cannot enable apply after configuration or library changes',async()=>{
    const {c,field}=harness(),pending=deferred();let key='A';c.deploymentKey=()=>key;c.deploymentPayload=()=>({});c.deploymentJob=()=>pending.promise;
    const task=c.previewChdDeployment();key='B';pending.resolve({id:'old',result:{}});await task;
    assert.equal(c.store.preview,null);assert.equal(field('apply').disabled,true);
});
test('one confirmation sends only a single server-owned deployment plan ID',async()=>{
    const {c}=harness(),pending=deferred();c.deploymentKey=()=> 'same';Object.assign(c.store,{preview:'plan',key:'same'});let count=0;
    c.deploymentJob=(route,payload)=>{count++;assert.deepEqual(JSON.parse(JSON.stringify(payload)),{preview_job_id:'plan'});return pending.promise;};
    const task=c.applyChdDeployment();await c.applyChdDeployment();assert.equal(count,1);pending.resolve({result:{status:'completed'}});await task;
    assert.equal(c.store.preview,null);
});
test('changed runtime report invalidates a ready deployment',async()=>{
    const {c,field}=harness();Object.assign(c.store,{preview:'plan',key:'old'});c.deploymentKey=()=> 'new';
    c.deploymentJob=()=>assert.fail('stale request');await c.applyChdDeployment();assert.equal(c.store.preview,null);assert.match(field('status').textContent,/重新预览/);
});
test('SSE reconnect keeps write lock and cancellation does not resubmit',async()=>{
    const {c,field,events}=harness();const calls=[];c.desktopRequest=async(route,payload)=>{calls.push({route,payload});return {job_id:'active'};};
    const task=c.deploymentJob('/api/chd/deployment/apply',{});await new Promise(resolve=>setImmediate(resolve));
    events[0].onerror();assert.equal(c.store.busy,true);assert.equal(field('close').disabled,true);
    await c.cancelChdDeployment();assert.equal(calls.length,2);assert.equal(calls[1].payload.job_id,'active');
    events[0].onmessage({data:JSON.stringify({status:'failed',error:'partial'})});await assert.rejects(task,/partial/);
    assert.equal(c.workbench.operation,null);assert.equal(c.store.busy,false);
});

test('a queued settings close cannot discard the response for a reopened CHD history',async()=>{
    const fields=new Map(),listeners=new Map(),pending=deferred();
    function node(){return {children:[],open:false,textContent:'',setAttribute(){},querySelectorAll(){return [];},replaceChildren(){this.children=[];},appendChild(child){this.children.push(child);},addEventListener(type,handler){listeners.set(type,handler);},showModal(){this.open=true;}};}
    const field=id=>{if(!fields.has(id))fields.set(id,node());return fields.get(id);};
    const c={console,setTimeout,clearTimeout,currentUILanguage:'zh',currentDeviceScan:null,openFilePicker(){},renderWorkbench(){},wbIcon:node,
        document:{getElementById:field,createElement:node,querySelector:field,querySelectorAll:()=>[]},desktopRequest:()=>pending.promise};
    vm.createContext(c);const source=fs.readFileSync(path.join(__dirname,'../src/templates/desktop.js'),'utf8');vm.runInContext(source.slice(0,source.indexOf('initializeDisplayPreferences();')),c);
    c.desktopRequest=()=>pending.promise;
    const request=c.openOperationHistory('chd');listeners.get('close')(); // The previous close event arrives after showModal.
    pending.resolve({chd_operations:[],chd_deployments:[]});await request;
    assert.ok(field('desktop-content').children.length>0);assert.equal(field('desktop-message').textContent,'');
});
