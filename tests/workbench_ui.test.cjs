const test=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');
function runtime(fetch){const elements=new Map();const element=id=>{if(!elements.has(id))elements.set(id,{hidden:true,open:false,showModal(){this.open=true;},close(){this.open=false;},focus(){},setAttribute(){},replaceChildren(){},classList:{add(){},toggle(name,value){this[name]=value;}}});return elements.get(id);};const context={URLSearchParams,module:{exports:{}},document:{createElementNS(){return {classList:{add(){}},setAttribute(){},append(){}};},addEventListener(){},getElementById:element,querySelector:element},workbenchText:zh=>zh,desktopRequest:fetch};vm.createContext(context);vm.runInContext(fs.readFileSync('src/templates/workbench.js','utf8'),context);return {...context.module.exports,elements,context};}
test('storage grouping uses ROM locations and never invents empty storage counts',()=>{const {workbenchGroups,wbStorageKind}=runtime();const data={playlists:[{system:'GBA',locations:{internal:{count:2,missing:1,covers:[]},card:{count:3,missing:0,covers:[]}}},{system:'GB',locations:{card:{count:1,missing:0,covers:[]}}}]};assert.equal(workbenchGroups(data,'all')[0].count,5);assert.equal(workbenchGroups(data,'internal').length,1);assert.equal(workbenchGroups(data,'card')[0].count,3);assert.equal(wbStorageKind('/storage/emulated/0/game.gba'),'internal');assert.equal(wbStorageKind('/storage/CARD/game.gba'),'card');});
test('late library response cannot overwrite a newer library',async()=>{let reply;const {workbenchOverview:state,loadWorkbenchOverview}=runtime(()=>new Promise(resolve=>reply=resolve));state.key='old';const pending=loadWorkbenchOverview('old','oldroot');state.key='new';state.data={current:true};reply({stale:true});await pending;assert.equal(state.data.current,true);assert.equal(state.data.stale,undefined);});

test('first read blocks until overview returns, later reads preserve interaction',()=>{
 const {libraryRead:state,beginLibraryRead:begin,finishLibraryRead:finish}=runtime();
 begin('scan','读取列表','root');assert.equal(state.blocking,true);
 begin('overview','统计游戏','root');finish('scan');assert.equal(state.owner,'overview');
 finish('overview');assert.equal(state.owner,'');assert.equal(state.readyRoot,'root');
 begin('scan','刷新列表','root');assert.equal(state.blocking,false);
 finish('scan','设备离线');assert.equal(state.error,'设备离线');
 begin('scan','切换设备','other');assert.equal(state.blocking,true);assert.equal(state.error,'');
 finish('scan','读取失败');assert.equal(state.error,'读取失败');assert.equal(state.readyRoot,'root');
});

test('Chinese display-name counts follow the selected storage scope',()=>{
 const {workbenchGroups}=runtime();
 const data={playlists:[{system:'GBA',locations:{internal:{count:2,missing:0,non_chinese_names:1,covers:[]},card:{count:3,missing:1,non_chinese_names:2,covers:[]}}}]};
 assert.equal(workbenchGroups(data,'all')[0].nonChineseNames,3);
 assert.equal(workbenchGroups(data,'card')[0].nonChineseNames,2);
 assert.equal(workbenchGroups(data,'internal')[0].nonChineseNames,1);
});

test('overview refresh reuses unchanged rows and fetches only changed playlists', async () => {
    const requested = [];
    const {context, workbenchOverview:state, loadWorkbenchOverview} = runtime(async url => {
        requested.push(url);
        return {overview:{path:'/library/GBA.lpl', updated:true}};
    });
    vm.runInContext('renderWorkbenchChrome = () => {}; this.workbenchSnapshot = () => ({});', context);
    const unchanged = {path:'/library/NES.lpl'};
    const oldRows = [['/library/NES.lpl','same','NES'], ['/library/GBA.lpl','old','GBA'], ['/library/GB.lpl','old','GB']];
    const newRows = [oldRows[0], ['/library/GBA.lpl','new','GBA']];
    state.loadedKey = JSON.stringify(['/library',oldRows,'/library/thumbnails']);
    state.key = JSON.stringify(['/library',newRows,'/library/thumbnails']);
    state.data = {playlists:[unchanged,{path:'/library/GBA.lpl'},{path:'/library/GB.lpl'}]};
    await loadWorkbenchOverview(state.key,'/library');
    assert.equal(requested.length,1);
    assert.equal(new URL(requested[0],'http://localhost').searchParams.get('path'),'/library/GBA.lpl');
    assert.equal(state.data.playlists[0],unchanged);
    assert.equal(state.data.playlists[1].updated,true);
    assert.equal(state.data.playlists.length,2);
});
