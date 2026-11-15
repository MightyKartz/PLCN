const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('src/templates/welcome.js', 'utf8');
function harness(fetch) {
    const root = {value:''};
    const context = {fetch, workbench:{operation:null}, workbenchText:zh=>zh,
        document:{getElementById:()=>root}, scanDevice:async()=>{context.opened++}, opened:0};
    vm.createContext(context);
    vm.runInContext(source + '\nrenderLibraryHome = () => {}; this.state = libraryHome;', context);
    return context;
}
test('automatic discovery lists sources without opening them', async()=>{
    const c = harness(async()=>({ok:true,json:async()=>({sources:[{path:'adb://a'}],recent:[]})}));
    await c.refreshLibrarySources();
    assert.equal(c.opened,0); assert.equal(c.state.data.sources.length,1);
});
test('late discovery cannot replace a newer result', async()=>{
    let resolve;
    const first = new Promise(r=>resolve=r);
    let count=0;
    const c=harness(()=>++count===1?first:Promise.resolve({ok:true,json:async()=>({sources:['new']})}));
    const pending=c.refreshLibrarySources(); await c.refreshLibrarySources();
    resolve({ok:true,json:async()=>({sources:['old']})}); await pending;
    assert.equal(c.state.data.sources[0],'new');
});
test('failed discovery clears stale ready devices and keeps the error', async()=>{
    const c=harness(async()=>{throw Error('USB read failed')});
    c.state.data={sources:['old']}; await c.refreshLibrarySources();
    assert.equal(c.state.data,null); assert.match(c.state.error,/USB read failed/);
    assert.equal(c.state.loading,false);
});
test('explicit opening respects another running operation', async()=>{
    const c=harness(); c.workbench.operation='apply';
    await c.openLibrarySource({path:'adb://device'}); assert.equal(c.opened,0);
    c.workbench.operation=null; await c.openLibrarySource({path:'adb://device'});
    assert.equal(c.opened,1); assert.equal(c.state.opening,'');
});

test('recent library keeps the same label as its connected card', async()=>{
    const c=harness();
    const path='mtp://device/00010001/RetroArch';
    c.state.data={sources:[{path,label:'内部共享存储空间'}]};
    let saved;
    c.desktopRequest=async(url,entry)=>{saved=entry};
    await c.rememberOpenedLibrary({connected:true,root_path:path,playlists:[{}],device:{model:'Android MTP'}});
    assert.equal(saved.label,'内部共享存储空间');
    assert.equal(saved.path,path);
});

test('device selection groups MTP storages and opens a ready library without starting content scan', async()=>{
    const c=harness();
    const storages=[
        {transport:'mtp',serial:'handheld',path:'mtp://handheld/00020001/RetroArch',label:'Games',status:'no_library'},
        {transport:'mtp',serial:'handheld',path:'mtp://handheld/00010001/RetroArch',label:'Internal',status:'ready'},
        {transport:'mtp',serial:'other',path:'mtp://other/00010001/RetroArch',label:'Other',status:'ready'}];
    const devices=c.homeDeviceSources(storages);
    assert.equal(devices.length,2);assert.equal(devices[0].storages.length,2);
    assert.equal(devices[0].path,storages[1].path);assert.equal(devices[0].status,'ready');
    assert.equal(storages[0].status,'no_library');assert.equal(c.opened,0);
    await c.openLibrarySource(devices[0]);
    assert.equal(c.opened,1);assert.equal(c.state.device.storages.length,2);
});

test('a handheld without existing lists remains selectable', async()=>{
    const c=harness();
    const devices=c.homeDeviceSources([{transport:'mtp',path:'mtp://new/00010001/RetroArch',label:'Internal',status:'no_library'}]);
    assert.equal(devices.length,1);assert.equal(devices[0].status,'no_library');
    await c.openLibrarySource(devices[0]);assert.equal(c.opened,1);
});
