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
