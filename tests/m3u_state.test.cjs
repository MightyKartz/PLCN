const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
function harness(){
    const fields=new Map(),events=[];
    const field=id=>{if(!fields.has(id))fields.set(id,{value:'',disabled:false,hidden:true,checked:false,textContent:'',children:[],
        replaceChildren(){this.children=[];},appendChild(value){this.children.push(value);},addEventListener(){},close(){this.open=false;},showModal(){this.open=true;}});return fields.get(id);};
    const c={document:{getElementById:field,createElement:()=>({textContent:''})},Option:function(text,value){this.value=value;},
        workbench:{operation:null},beginWorkbenchOperation(op){if(c.workbench.operation)return false;c.workbench.operation=op;return true;},
        endWorkbenchOperation(){c.workbench.operation=null;},getThumbnailsDirectory:()=>'/images',discInspectionKey:()=> 'library-A',
        discInspection:{data:{playlist_path:'/library/SS.lpl',system:'Sega - Saturn'}},
        EventSource:class{constructor(){events.push(this);}close(){this.closed=true;}},desktopRequest:async()=>({job_id:'job'}),
        scanDevice:async()=>{},closeDiscInspection(){},resetGameLibrary(){},renderWorkbench(){},currentDeviceScan:null};
    vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/templates/m3u.js'),'utf8')+'\nglobalThis.store=m3uEditor;',c);
    return {c,field:id=>field('m3u-'+id),events};
}
function deferred(){let resolve;return {promise:new Promise(r=>{resolve=r;}),resolve};}
const result={content:'Disc1.chd\nDisc2.chd\n',mode:'file',removed_indices:[],target:'/Roms/Game.m3u',backup_root:'/backups',
    core:{message:'Fixture core info'},issues:[],notes:[],changes:[],saves:{issues:[],copies:[],states:[]},affected_playlists:[],
    retained_discs:[],artwork_copies:[],can_apply:true};

test('a late preview cannot enable apply after an input or library change',async()=>{
    const {c,field}=harness(),pending=deferred();let input='A';
    c.m3uPayload=()=>({key:input});c.m3uJob=()=>pending.promise;
    const request=c.previewM3u();input='B';pending.resolve({id:'old',result});await request;
    assert.equal(c.store.previewId,null);assert.equal(field('apply').disabled,true);
});

test('one confirmation consumes the server plan ID exactly once',async()=>{
    const {c}=harness(),pending=deferred();let submits=0;
    c.m3uPayload=()=>({key:'A'});c.store.previewId='preview';c.store.previewKey=c.m3uInputsKey();
    c.m3uJob=(route,payload)=>{submits++;assert.equal(payload.preview_job_id,'preview');return pending.promise;};
    const first=c.applyM3u();await c.applyM3u();assert.equal(submits,1);
    pending.resolve({result:{backup_directory:'/backup'}});await first;assert.equal(c.store.previewId,null);
});

test('changed inputs invalidate even a previously ready server plan',async()=>{
    const {c,field}=harness();c.m3uPayload=()=>({key:'new'});c.store.previewId='old';c.store.previewKey='old';
    c.m3uJob=()=>assert.fail('Stale plan must not submit');await c.applyM3u();
    assert.equal(c.store.previewId,null);assert.match(field('status').textContent,/重新预览/);
});

test('selected disc order is the displayed order and excluded discs do not submit',()=>{
    const {c,field}=harness();c.store.group={id:'group'};c.store.order=['three','one','two'];c.store.selected=new Set(['two','three']);
    field('mode').value='file';field('filename').value='Game.m3u';field('label').value='Game';
    assert.deepEqual(Array.from(c.m3uPayload().disc_ids),['three','two']);
});

test('SSE reconnect does not release the write lock or resubmit the operation',async()=>{
    const {c,field,events}=harness();let requests=0;c.desktopRequest=async()=>{requests++;return {job_id:'active'};};
    const job=c.m3uJob('/api/m3u/apply',{preview_job_id:'plan'});await new Promise(resolve=>setImmediate(resolve));
    events[0].onerror();assert.equal(c.workbench.operation,'m3u');assert.equal(field('close').disabled,true);
    assert.equal(requests,1);assert.match(field('status').textContent,/重连/);
    events[0].onmessage({data:JSON.stringify({status:'completed',result:{status:'applied'}})});
    const response=await job;assert.equal(response.result.status,'applied');assert.equal(c.workbench.operation,null);
    assert.equal(events[0].closed,true);
});

test('application and restoration refresh the same library counts and discard old item cache',()=>{
    const {c}=harness();let cleared=0,renders=0;
    c.currentDeviceScan={playlists:[{path:'C:\\Library\\SS.lpl',item_count:2},{path:'C:\\Library\\Other.lpl',item_count:1}],totals:{items:3}};
    c.resetGameLibrary=()=>{cleared++;};c.renderDeviceScan=()=>{renders++;};
    c.reflectM3uResult({playlist_path:'C:/Library/SS.lpl',playlist_count:1});
    assert.equal(c.currentDeviceScan.totals.items,2);assert.equal(cleared,1);assert.equal(renders,1);
    c.reflectM3uResult({playlist_path:'C:/Library/SS.lpl',playlist_count:2});
    assert.equal(c.currentDeviceScan.totals.items,3);assert.equal(cleared,2);
});
