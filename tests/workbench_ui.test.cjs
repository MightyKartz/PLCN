const test=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');
function runtime(fetch){const elements=new Map();const element=id=>{if(!elements.has(id))elements.set(id,{hidden:true,open:false,showModal(){this.open=true;},close(){this.open=false;},focus(){},setAttribute(){},classList:{toggle(name,value){this[name]=value;}}});return elements.get(id);};const context={module:{exports:{}},document:{addEventListener(){},getElementById:element,querySelector:element},workbenchText:zh=>zh,desktopRequest:fetch};vm.createContext(context);vm.runInContext(fs.readFileSync('src/templates/workbench.js','utf8'),context);return {...context.module.exports,elements};}
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

test('task shortcut shows active counts, a failure dot, and hides unknown status',()=>{
 const {workbenchOverview:state,renderWorkbenchTaskBadge:render,elements}=runtime();
 state.job={status:'failed'};render();
 const badge=elements.get('task-center-badge');
 assert.equal(badge.hidden,false);assert.equal(badge.textContent,'');assert.equal(badge.classList['task-failed'],true);
 state.activeJobs=2;state.job={status:'running'};render();
 assert.equal(badge.textContent,'2');assert.equal(badge.classList['task-failed'],false);
 state.activeJobs=0;state.job={status:'completed'};render();assert.equal(badge.hidden,true);
 state.taskError=true;render();assert.equal(badge.hidden,true);assert.match(elements.get('task-center-button').title,/暂不可用/);
});

test('Chinese display-name counts follow the selected storage scope',()=>{
 const {workbenchGroups}=runtime();
 const data={playlists:[{system:'GBA',locations:{internal:{count:2,missing:0,non_chinese_names:1,covers:[]},card:{count:3,missing:1,non_chinese_names:2,covers:[]}}}]};
 assert.equal(workbenchGroups(data,'all')[0].nonChineseNames,3);
 assert.equal(workbenchGroups(data,'card')[0].nonChineseNames,2);
 assert.equal(workbenchGroups(data,'internal')[0].nonChineseNames,1);
});
