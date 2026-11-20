const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
function harness(){
    const fields=new Map(),events=[];
    const field=id=>{if(!fields.has(id))fields.set(id,{value:'',checked:false,disabled:false,hidden:false,textContent:'',replaceChildren(){},querySelectorAll(){return [];}});return fields.get(id);};
    const c={console,Set,JSON,document:{getElementById:field},workbench:{operation:null},
        beginWorkbenchOperation(op){if(c.workbench.operation)return false;c.workbench.operation=op;return true;},endWorkbenchOperation(){c.workbench.operation=null;},
        desktopRequest:async()=>({job_id:'active'}),EventSource:class{constructor(){events.push(this);}close(){this.closed=true;}},resetGameLibrary(){},desktopClearPreview(){},refreshDesktop:async()=>{},scanDevice:async()=>{},currentDeviceScan:null,currentUILanguage:'zh',
        workbenchText:(zh,en)=>c.currentUILanguage==='en'?en:zh,
        wbIconButton(button,name,label){button.iconName=name;button.title=label;button.ariaLabel=label;}};
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

test('an invalid cleanup id retires the continuation entry',async()=>{
    const {c,field}=harness();
    c.deploymentJob=async()=>{const error=new Error('该清理任务已失效，请重新生成方案');error.code='cleanup_invalid';throw error;};
    const button=field('cleanup');button.dataset={job:'old-id'};button.hidden=false;
    await c.continueChdCleanup();
    assert.equal(button.dataset.job,undefined);assert.equal(button.hidden,true);
    assert.match(field('status').textContent,/失效/);
});

test('an ambiguous failure offers a recheck entry instead of resubmitting',async()=>{
    const {c,field}=harness();
    let requestId;c.deploymentJob=async(route,payload)=>{requestId=payload.request_id;throw new Error('网络错误');};
    const lookups=[];c.desktopRequest=async(route,payload)=>{lookups.push({route,payload});return {job:null};};
    const button=field('cleanup');button.dataset={job:'old-id'};button.hidden=false;
    await c.continueChdCleanup();
    assert.equal(button.dataset.job,'old-id');assert.equal(button.dataset.check,'1');
    assert.equal(button.hidden,false);assert.equal(button.disabled,false);
    assert.match(field('status').textContent,/无法确认|核对/);
    // The recheck only binds the job carrying this request's id via exact lookup.
    c.deploymentJob=async()=>assert.fail('must not resubmit');
    c.desktopRequest=async(route,payload)=>{lookups.push({route,payload});
        return {job:{id:'job-9',request_id:requestId,status:'completed',
        result:{status:'completed',deleted:['/a.cue'],remaining:[],unverified:[]}}};};
    await c.continueChdCleanup();
    assert.equal(button.hidden,true);
    assert.match(field('status').textContent,/清理完成/);
    assert.ok(lookups.length>=2);
    for(const entry of lookups){assert.equal(entry.route,'/api/jobs/by-request');assert.equal(entry.payload.request_id,requestId);}
});

test('reconcile never binds a cleanup job from another request or game',async()=>{
    const {c,field}=harness();
    c.deploymentJob=async()=>{throw new Error('连接已失效');};
    // A foreign job is invisible to the exact request lookup.
    c.desktopRequest=async()=>({job:null});
    c.store.record='game-A';
    const button=field('cleanup');button.dataset={job:'old-id'};button.hidden=false;
    await c.continueChdCleanup();
    assert.equal(button.dataset.job,'old-id');assert.equal(button.dataset.check,'1');
    // A stale response after switching games must not touch the new window.
    let resolve;c.desktopRequest=()=>new Promise(r=>resolve=r);
    c.deploymentJob=async()=>assert.fail('recheck must not resubmit');
    const task=c.continueChdCleanup();
    c.store.record='game-B';button.dataset.job='b-cleanup';button.hidden=false;
    resolve({job:null});await task;
    assert.equal(button.dataset.job,'b-cleanup');assert.equal(button.dataset.check,undefined);
});

test('reconcile binds the latest remaining list when the submitted job finished',async()=>{
    const {c,field}=harness();
    c.document.createElement=()=>({textContent:''});
    field('details').appendChild=function(){};
    let requestId;c.deploymentJob=async(route,payload)=>{requestId=payload.request_id;throw new Error('连接已失效');};
    c.store.record='game';
    c.desktopRequest=async()=>({job:{id:'job-9',request_id:requestId,status:'completed',result:{status:'partial',deleted:['/a.cue'],remaining:[{path:'/a.bin',error:'io'}],cleanup_id:'next-id'}}});
    const button=field('cleanup');button.dataset={job:'old-id'};button.hidden=false;
    await c.continueChdCleanup();
    assert.equal(button.dataset.job,'next-id');assert.equal(button.hidden,false);assert.equal(button.disabled,false);
});

test('a cancelled cleanup job rebinds the freshly issued id with its remaining list',async()=>{
    const {c,field}=harness();
    c.document.createElement=()=>({textContent:''});
    field('details').appendChild=function(){};
    c.deploymentJob=async()=>{const error=new Error('cancelled');
        error.result={status:'partial',cancelled:true,deleted:['/game.cue'],remaining:[{path:'/game.bin',error:'停止'}],cleanup_id:'new-id'};throw error;};
    const button=field('cleanup');button.dataset={job:'old-id'};button.hidden=false;
    await c.continueChdCleanup();
    assert.equal(button.dataset.job,'new-id');assert.equal(button.hidden,false);assert.equal(button.disabled,false);
    assert.match(field('status').textContent,/已取消/);
});

test('check mode keeps a search icon and read-only labels; a valid id restores delete mode in both languages',async()=>{
    const {c,field}=harness();
    const button=field('cleanup');button.dataset={job:'old-id'};button.hidden=false;
    c.deploymentJob=async()=>{throw new Error('连接已失效');};
    c.desktopRequest=async()=>({job:null});
    await c.continueChdCleanup();
    assert.equal(button.dataset.check,'1');
    assert.equal(button.iconName,'search');
    assert.equal(button.title,'核对清理结果');assert.equal(button.ariaLabel,'核对清理结果');
    // A bound cleanup id restores delete semantics.
    c.document.createElement=()=>({textContent:''});field('details').appendChild=function(){};
    c.showCleanupResult({status:'partial',remaining:[{path:'/a.bin',error:'io'}],unverified:[],cleanup_id:'next'});
    assert.equal(button.dataset.job,'next');assert.equal(button.dataset.check,undefined);
    assert.equal(button.iconName,'trash');
    assert.equal(button.title,'继续清理原镜像');assert.equal(button.ariaLabel,'继续清理原镜像');
    // English labels for both modes.
    c.currentUILanguage='en';
    c.offerCleanupCheck();
    assert.equal(button.iconName,'search');
    assert.equal(button.title,'Check cleanup result');assert.equal(button.ariaLabel,'Check cleanup result');
    c.showCleanupResult({status:'partial',remaining:[{path:'/b.bin',error:'io'}],unverified:[],cleanup_id:'n2'});
    assert.equal(button.iconName,'trash');
    assert.equal(button.title,'Continue removing originals');assert.equal(button.ariaLabel,'Continue removing originals');
});

test('an unverified-only apply result lists the paths and offers no cleanup action',async()=>{
    const {c,field}=harness();
    Object.assign(c.store,{preview:'plan',key:'k'});c.deploymentKey=()=> 'k';
    const entries=[];c.document.createElement=()=>{const node={textContent:''};entries.push(node);return node;};
    field('details').appendChild=function(){};
    c.deploymentJob=async()=>({result:{status:'partial',error:'1 项删除结果待核对',
        unverified:[{path:'/roms/a.cue',error:'删除已执行但无法核对'}],actual_image_delta_bytes:null,cleanup_remaining:[]}});
    const button=field('cleanup');
    await c.applyChdDeployment();
    assert.equal(button.hidden,true);
    assert.match(field('status').textContent,/待核对/);
    assert.equal(entries[0].textContent,'待核对：/roms/a.cue · 删除已执行但无法核对');
});
