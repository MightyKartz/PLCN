const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
function harness() {
    const elements=new Map(),pending=[];
    let selected='mtp://device/00010001/RetroArch/playlists/SS.lpl';
    const field=id=>{
        if(!elements.has(id))elements.set(id,{value:'',textContent:'',hidden:false,open:false,
            replaceChildren(){},addEventListener(){},showModal(){this.open=true;},close(){this.open=false;}});
        return elements.get(id);
    };
    const c={AbortController,URLSearchParams,workbench:{operation:null},document:{getElementById:field},
        gameLibraryInput:()=>[selected,'Sega - Saturn'],workbenchText:zh=>zh,
        beginWorkbenchOperation(op){c.workbench.operation=op;},endWorkbenchOperation(){c.workbench.operation=null;},
        fetch:(url,options)=>new Promise(resolve=>pending.push({url,options,resolve})),
        desktopRequest:async(url,payload,opts)=>{const res=await c.fetch(url,{...opts});const data=await res.json();if(res.ok===false)throw new Error(data.error||'HTTP error');return data;},
        Map};
    vm.createContext(c);
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/templates/discs.js'),'utf8')+'\nglobalThis.store=discInspection;',c);
    c.renderDiscInspection=()=>{c.rendered=c.store.data;};
    return {c,field,pending,select:value=>{selected=value;},reply:(index,data,ok=true)=>pending[index].resolve({ok,json:async()=>data})};
}

test('closing and reopening rejects an old request without unlocking the newer inspection',async()=>{
    const {c,pending,reply,select}=harness();
    const old=c.openDiscInspection();c.closeDiscInspection();
    assert.equal(pending[0].options.signal.aborted,true);
    select('mtp://device/00010001/RetroArch/playlists/PS1.lpl');const latest=c.openDiscInspection();
    reply(0,{groups:['old']});await old;
    assert.equal(c.workbench.operation,'disc-inspection');assert.equal(c.store.data,null);
    reply(1,{groups:['new']});await latest;
    assert.equal(c.rendered.groups[0],'new');assert.equal(c.workbench.operation,null);
});

test('a changed playlist cannot receive the previous graph',async()=>{
    const {c,reply,select}=harness();const request=c.openDiscInspection();select('other.lpl');
    reply(0,{groups:['stale']});await request;
    assert.equal(c.store.data,null);assert.equal(c.workbench.operation,null);
});

test('inspection errors remain explicit and another read can be started',async()=>{
    const {c,field,reply}=harness();const first=c.openDiscInspection();
    reply(0,{error:'设备目录无法读取'},false);await first;
    assert.match(field('disc-inspection-summary').textContent,/检查失败：设备目录无法读取/);
    assert.equal(c.workbench.operation,null);c.closeDiscInspection();
    const second=c.openDiscInspection();reply(1,{groups:[]});await second;
    assert.deepEqual(Array.from(c.store.data.groups),[]);
});

test('group filtering uses actual reference files and keeps errors separate from candidates',()=>{
    const {c}=harness();const files=new Map([['one',{path:'/Roms/Game (Disc 1).chd'}]]);
    const group={label:'空想科学世界',files:['one'],kind:'disc_set',issues:[]};
    assert.equal(c.discGroupMatches(group,files,'disc 1','candidate'),true);
    assert.equal(c.discGroupMatches(group,files,'空想','all'),true);
    assert.equal(c.discGroupMatches(group,files,'','attention'),false);
    assert.equal(c.discGroupMatches({...group,issues:[{code:'missing'}]},files,'','attention'),true);
    assert.equal(c.discGroupMatches(group,files,'','m3u'),false);
});

test('unmapped references never display as missing or zero-sized',()=>{
    const {c}=harness();
    assert.equal(c.discFileStatus({status:'unmapped',size:null}),'尚未检查');
    assert.equal(c.discFileStatus({status:'missing',size:null}),'文件缺失');
    assert.match(c.discFileStatus({status:'present',size:1048576}),/1.00 MiB/);
});
