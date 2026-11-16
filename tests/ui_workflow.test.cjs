const {test} = require('node:test');
const assert = require('node:assert/strict');
const {deriveWorkbenchState} = require('../src/templates/workflow.js');
const {downloadTaskOutcome} = require('../src/templates/workflow.js');
const {repairActionStatus} = require('../src/templates/workflow.js');
test('identified review and duplicate rows need no individual confirmation', () => {
    const game = {match_status:'review',needs_review:true,new_label:'游戏',original_item_label:'游戏',thumbnail_source:'Game (Japan)'};
    assert.equal(repairActionStatus(game), 'download');
    assert.equal(repairActionStatus({...game,match_status:'duplicate'}), 'download');
    assert.equal(repairActionStatus({...game,new_label:'新名称'}), 'matched');
    assert.equal(repairActionStatus({...game,cover_exists:true}), 'ready');
    assert.equal(repairActionStatus({...game,cover_exists:true,artwork:{Named_Boxarts:{status:'exists'},Named_Snaps:{status:'missing'}}}), 'download');
    assert.equal(repairActionStatus({...game,thumbnail_source:''}), 'incomplete');
    assert.equal(repairActionStatus({...game,new_label:''}), 'incomplete');
    assert.equal(repairActionStatus({...game,new_label:'新名称',thumbnail_source:''}, 'names'), 'rename');
    assert.equal(repairActionStatus({...game,applied:true}), 'applied');
});
test('finished transport does not report success when images failed or task was cancelled', () => {
    const partial = downloadTaskOutcome('completed', {total:{failed:27}});
    assert.equal(partial.complete, false);
    assert.equal(partial.label, '部分完成');
    assert.match(partial.message, /27/);
    assert.equal(downloadTaskOutcome('cancelled', {total:{failed:0}}).complete, false);
    assert.equal(downloadTaskOutcome('completed', {total:{failed:0,success:27}}).complete, true);
});
const ready = {operation: null, previewKey: 'a', inputKey: 'a', playlist: 'test.lpl', system: 'GBA', selected: 1, thumbnails: 'images', download: true};

test('first launch never claims a completed step or enables writes', () => {
    const state = deriveWorkbenchState({previewKey:null, inputKey:'a', selected:0});
    assert.equal(state.hasLibrary, false);
    assert.equal(state.canApply, false);
    assert.equal(state.canPreview, false);
});
test('scanned library requires an explicit list choice', () => {
    const state = deriveWorkbenchState({scanned:true,previewKey:null,inputKey:'a',selected:0});
    assert.equal(state.hasLibrary,true);
    assert.equal(state.canPreview,false);
});
test('valid playlist permits a preview, not a write without proposals', () => {
    const state = deriveWorkbenchState({...ready,previewKey:null});
    assert.equal(state.canPreview,true);
    assert.equal(state.canApply,false);
});
test('empty, unchecked and unconfirmed review-only selections cannot apply', () => {
    assert.equal(deriveWorkbenchState({...ready,selected:0}).canApply,false);
    assert.equal(deriveWorkbenchState({...ready,selected:1}).canApply,true);
});
test('changed context invalidates a previous preview even if rows remain', () => {
    const state = deriveWorkbenchState({...ready,inputKey:'changed path, source or mode'});
    assert.equal(state.previewValid,false);
    assert.equal(state.canApply,false);
});
test('names-only operation does not require an image directory', () => {
    assert.equal(deriveWorkbenchState({...ready,thumbnails:''}).canApply,false);
    assert.equal(deriveWorkbenchState({...ready,download:false,thumbnails:''}).canApply,true);
});
for (const operation of ['scan','preview','apply','pick']) {
    test(`during ${operation}, duplicate actions and batch processing are disabled`, () => {
        const state = deriveWorkbenchState({...ready,operation,batchDir:'lists',batchThumbnails:'images'});
        assert.equal(state.canPreview,false);
        assert.equal(state.canApply,false);
        assert.equal(state.canReviewBatch,false);
    });
}
test('failed or cancelled apply does not claim completion and allows recovery', () => {
    const state=deriveWorkbenchState({...ready,operation:null,applied:false});
    assert.equal(state.canApply,true);
});
test('all-system analysis requires a scanned library but no artwork folder', () => {
    assert.equal(deriveWorkbenchState({...ready}).canReviewBatch,false);
    assert.equal(deriveWorkbenchState({...ready,scanned:true,batchDir:'lists',thumbnails:''}).canReviewBatch,true);
    assert.equal(deriveWorkbenchState({...ready,scanned:true,batchDir:'lists'}).canReviewBatch,true);
});

// Exercise the real filtering function, including the old accidental inversion regression.
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const templateDir=path.join(__dirname,'../src/templates');
const html=fs.readFileSync(path.join(templateDir,'plcn.html'),'utf8');
const page=Array.from(html.matchAll(/<script src="\/assets\/([^"/]+)"><\/script>/g),
    match=>fs.readFileSync(path.join(templateDir,match[1]),'utf8')).join('\n');
const configSource=fs.readFileSync(path.join(templateDir,'config.js'),'utf8');
function source(name) {
    const start=page.search(new RegExp('^(?:async )?function '+name+'\\(', 'm'));
    assert.notEqual(start,-1,`Missing UI function: ${name}`);
    const remaining=page.slice(start);
    const next=remaining.slice(1).search(/^(?:async )?function /m);
    return next<0 ? remaining : remaining.slice(0,next+1);
}
test('known search names do not become download sources and explain gallery failures separately', () => {
    const context={document:{getElementById:()=>({value:'both'})}, workbenchText:zh=>zh,
        getRepairMode:()=> 'both', uiText:x=>x, hasExistingCover:()=>false,
        previewArtworkState:require('../src/templates/workflow.js').previewArtworkState};
    vm.createContext(context);
    vm.runInContext(source('getCoverStatusInfo'),context);
    const game={new_label:'仙剑奇侠传',original_item_label:'仙剑奇侠传',thumbnail_source:null,
        artwork_query:'Sword and Fairy',artwork_identity_status:'resolved',artwork_gallery_status:'not_found'};
    assert.equal(repairActionStatus(game),'incomplete');
    assert.equal(context.getCoverStatusInfo(game).label,'未匹配图片源');
    assert.equal(context.getCoverStatusInfo({...game,artwork_gallery_status:'unavailable'}).label,'图库查询失败');
    assert.equal(context.getCoverStatusInfo({...game,artwork_identity_status:'unresolved',artwork_gallery_status:'unknown'}).label,'名称未识别');
    assert.equal(repairActionStatus({...game,new_label:'新名称'},'names'),'rename');
});
test('clicking All twice preserves row selection', () => {
    const context={currentPreviewFilter:'all',currentChanges:[{enabled:true}], document:{querySelectorAll:()=>[]},renderPreviewTable:()=>{},renderWorkbench:()=>{}};
    vm.createContext(context);
    vm.runInContext(source('setPreviewFilter'),context);
    const button={classList:{add:()=>{},contains:()=>true}};
    context.setPreviewFilter('all',button); context.setPreviewFilter('all',button);
    assert.equal(context.currentChanges[0].enabled,true);
});
test('manual confirmation moves a review item into actionable filter', () => {
    const context={currentPreviewFilter:'review',getMatchInfo:c=>({kind:c.review_confirmed?'reviewed':c.match_status}),isActionableChange:c=>c.review_confirmed===true,isEditedChange:()=>false};
    vm.createContext(context);vm.runInContext(source('matchesFilter'),context);
    assert.equal(context.matchesFilter({match_status:'duplicate'},''),true);
    assert.equal(context.matchesFilter({match_status:'review',review_confirmed:true},''),false);
    context.currentPreviewFilter='matched';
    assert.equal(context.matchesFilter({match_status:'review',review_confirmed:true},''),true);
});

const desktopSource=fs.readFileSync(require('node:path').join(__dirname,'../src/templates/desktop.js'),'utf8');
function pickerContext(request) {
    const context={operation:null, fallback:null, selected:null, document:{getElementById:()=>({value:'initial'})},
        openFilePicker:(...args)=>{context.fallback=args;},
        beginWorkbenchOperation:operation=>{if(context.operation)return false; context.operation=operation;return true;},
        endWorkbenchOperation:()=>{context.operation=null;},
        desktopRequest:request, showStatus:()=>{}, desktopText:zh=>zh,
        selectFile:path=>{assert.equal(context.operation,null);context.selected=path;context.operation='scan';}};
    vm.createContext(context);
    vm.runInContext(desktopSource.slice(desktopSource.indexOf('const builtInFilePicker'),desktopSource.indexOf('async function openPathSettings')),context);
    return context;
}
test('native picker locks duplicate requests and releases before a selected folder starts scanning', async () => {
    let resolve, requests=0;
    const context=pickerContext(()=>{requests++;return new Promise(r=>{resolve=r;});});
    const pending=context.openFilePicker('retroarch_root',true);
    assert.equal(context.operation,'pick');
    await context.openFilePicker('playlist_path',false);
    assert.equal(requests,1);
    resolve({path:'chosen'}); await pending;
    assert.equal(context.selected,'chosen');
    assert.equal(context.operation,'scan');
});
test('unavailable native picker unlocks and opens fallback for the original input', async () => {
    const context=pickerContext(async()=>{throw new Error('No Tk');});
    await context.openFilePicker('playlist_path',false);
    assert.equal(context.operation,null);
    assert.deepEqual(context.fallback,['playlist_path',false,undefined]);
});
test('cancelling native picker unlocks without selecting a new path', async () => {
    const context=pickerContext(async()=>({path:null}));
    await context.openFilePicker('playlist_path',false);
    assert.equal(context.operation,null);
    assert.equal(context.selected,null);
    assert.equal(context.fallback,null);
});
test('late folder responses cannot replace a newer directory or enable stale selection', async () => {
    const elements={fileModal:{open:true},fileList:{textContent:'',innerHTML:'',appendChild:()=>{}},selectDirBtn:{disabled:false},currentPath:{textContent:''}};
    const pending=[];
    const context={fileListVersion:0,currentPath:'.',workbenchText:zh=>zh,console,
        document:{getElementById:id=>elements[id]},fetch:()=>new Promise(resolve=>pending.push(resolve))};
    vm.createContext(context);
    vm.runInContext(source('loadFileList'),context);
    const first=context.loadFileList('old');
    assert.equal(elements.selectDirBtn.disabled,true);
    const second=context.loadFileList('new');
    pending[1]({json:async()=>({current_path:'new',items:[]})}); await second;
    pending[0]({json:async()=>({current_path:'old',items:[]})}); await first;
    assert.equal(context.currentPath,'new');
    assert.equal(elements.currentPath.textContent,'new');
    const closed=context.loadFileList('closed');elements.fileModal.open=false;
    pending[2]({json:async()=>({current_path:'closed',items:[]})});await closed;
    assert.equal(context.currentPath,'new');
    assert.equal(elements.selectDirBtn.disabled,true);
});

test('reloading legacy config preserves its image folder as an override while clearing selection', () => {
    const values={playlist_path:'one.lpl',system_name:'GBA',thumbnails_dir:'single-images',batch_thumbnails_dir:'batch-images',rom_name_cn_path:'data/rom-name-cn'};
    const elements={}; const element=id=>elements[id]||={value:'',classList:{add:()=>{},remove:()=>{},toggle:()=>{}},style:{},textContent:'',setAttribute:()=>{},disabled:false,hidden:false};
    const context={fetch:async()=>({ok:true,json:async()=>values}),document:{getElementById:element},renderWorkbench:()=>{},showStatus:()=>{}, uiText:x=>x};
    vm.createContext(context);
    vm.runInContext(source('loadConfig'),context);
    return context.loadConfig().then(()=>{
        assert.equal(element('thumbnails_override').value,'single-images');
        assert.equal(element('playlist_path').value,'');
        assert.equal(element('system_name').value,'');
    });
});

test('an explicit empty override follows the detected directory instead of a stored effective path', async () => {
    const elements={};
    const element=id=>elements[id]||={value:''};
    const context={document:{getElementById:element},currentDeviceScan:{directories:{thumbnails:'detected-images'}},
        fetch:async()=>({ok:true,json:async()=>({retroarch_root:'library',thumbnails_override:'',thumbnails_dir:'stale-images'})}),
        renderWorkbench:()=>{},showStatus:()=>{},uiText:x=>x};
    vm.createContext(context);
    vm.runInContext(source('getThumbnailsDirectory')+source('loadConfig'),context);
    await context.loadConfig();
    assert.equal(context.getThumbnailsDirectory(),'detected-images');
    element('thumbnails_override').value='custom-images';
    assert.equal(context.getThumbnailsDirectory(),'custom-images');
    element('thumbnails_override').value='';
    assert.equal(context.getThumbnailsDirectory(),'detected-images');
});

test('a manual artwork override belongs to its library and survives only same-library navigation', () => {
    const elements={retroarch_root:{value:'library-a'},thumbnails_override:{value:'custom-images'}};
    const context={pathSettingsRoot:'library-a',legacyThumbnailsSetting:false,document:{getElementById:id=>elements[id]}};
    vm.createContext(context);
    vm.runInContext(source('setLibraryRoot'),context);
    context.setLibraryRoot('library-a');
    assert.equal(elements.thumbnails_override.value,'custom-images');
    context.setLibraryRoot('library-b');
    assert.equal(elements.thumbnails_override.value,'');
    assert.equal(context.pathSettingsRoot,'library-b');
});

test('preview options reject turning both operations off and preserve the selected game scope', async () => {
    let previews=0, mode='names', receivedScope=null;
    const scope={entries:[[1,'/selected.sfc']]};
    const control={checked:false};
    const context={getProcessingOptions:()=>({write_names:mode!=='none',download_thumbnails:mode==='both'}),
        previewTask:async value=>{previews++;receivedScope=value;},workbench:{previewScope:scope},showStatus:()=>{},workbenchText:zh=>zh};
    vm.createContext(context);vm.runInContext(source('changePreviewOptions'),context);
    await context.changePreviewOptions(control);assert.equal(previews,1);assert.equal(receivedScope,scope);
    mode='none';await context.changePreviewOptions(control);
    assert.equal(control.checked,true);assert.equal(previews,1);
});

test('all-systems completion applies the analyzed preview job and skips apply when nothing to do', async () => {
    const calls=[]; let finished;
    const wrap={hidden:true};
    const elements={
        'batch-review-dialog':{querySelector:()=>wrap,showModal(){this.open=true;}},
        'batch-review-status':{dataset:{},textContent:''},
        'batch-run-progress':{removeAttribute(){}},
        'batch-review-rows':{replaceChildren(){}},
        'batch-review-title':{textContent:''},
        'batch-run-note':{textContent:''},
        'thumbnails_override':{value:''},
        'rom_name_cn_path':{value:''},
    };
    const context={workbench:{operation:null},
        currentDeviceScan:{directories:{playlists:'/lib/playlists',thumbnails_exists:true}},
        document:{getElementById:id=>elements[id]},
        beginWorkbenchOperation:()=>true,endWorkbenchOperation:()=>{},
        workbenchText:zh=>zh,getThumbnailsDirectory:()=>'/lib/thumbnails',
        setBatchRunRunning:()=>{},finishBatchRun:(...args)=>{finished=args;},
        watchBatchRunJob:async()=>context.analysis,
        desktopRequest:async(url,body)=>{calls.push({url,body});
            return url==='/api/batch/preview'?{job_id:'preview-1'}:url==='/api/batch/apply'?{job_id:'apply-1'}:{};}};
    vm.createContext(context);vm.runInContext(source('runAllSystemsCompletion'),context);
    context.analysis={can_apply:true,rows:[]};
    await context.runAllSystemsCompletion();
    assert.deepEqual(calls.map(call=>call.url),['/api/batch/preview','/api/batch/apply']);
    assert.equal(calls[1].body.preview_job_id,'preview-1');
    assert.equal(calls[1].body.continue_on_error,true);
    assert.equal(finished[0],'completed');
    calls.length=0;finished=undefined;
    context.analysis={can_apply:false,rows:[]};
    await context.runAllSystemsCompletion();
    assert.deepEqual(calls.map(call=>call.url),['/api/batch/preview','/api/batch/discard']);
    assert.equal(calls[1].body.preview_job_id,'preview-1');
    assert.equal(finished[0],'completed');
});

test('task transport keeps writes locked on disconnect and distinguishes cancellation from failure', () => {
    for (const status of ['cancelled','failed','completed']) {
        let events, closed=false, refreshes=0, applied=0;
        const notices=[];
        const context={workbench:{operation:null}, EventSource:class {constructor(){events=this;} close(){closed=true;}},
            renderWorkbench:()=>{}, workbenchText:zh=>zh, downloadTaskOutcome,
            showStatus:(message,type)=>notices.push({message,type}),
            applyCompletedJobToPreview:()=>applied++, desktopDialog:{open:true}, desktopView:'tasks',
            refreshDesktop:()=>refreshes++, endWorkbenchOperation:()=>{context.workbench.operation=null;}};
        vm.createContext(context);vm.runInContext(source('trackProgress'),context);
        context.trackProgress('job-1');
        events.onerror();assert.equal(context.workbench.operation,'apply');
        events.onmessage({data:JSON.stringify({status, error:status==='completed'?null:'任务已停止', result:{download_summary:{total:{failed:0}}}})});
        assert.equal(closed,true);
        assert.equal(context.workbench.operation,null);
        assert.equal(context.workbench.jobId,null);
        assert.equal(refreshes,1);
        assert.equal(applied,status==='failed'?0:1);
        assert.equal(notices[0].type,status==='cancelled'?'info':status==='failed'?'error':'success');
    }
});

test('one confirmation submits once and a stale preview cannot submit', async () => {
    const changes=[{new_label:'游戏',original_item_label:'Game',thumbnail_source:'Game'}];
    let resolve, tracked;
    const calls=[];
    const context={workbench:{operation:null},currentChanges:changes,currentUILanguage:'zh',
        document:{getElementById:()=>({value:'games.lpl'})},getThumbnailsDirectory:()=> 'images',
        workbenchSnapshot:()=>({canApply:context.valid && !context.workbench.operation}),valid:true,
        getIncludedChanges:()=>changes,currentMatchesWriteName:()=>false,getProcessingOptions:()=>({write_names:true,download_thumbnails:true}),
        beginWorkbenchOperation:operation=>{context.workbench.operation=operation;return true},
        renderWorkbench:()=>{},showStatus:()=>{},endWorkbenchOperation:()=>{context.workbench.operation=null},
        rememberAppliedChanges:()=>{},trackProgress:id=>{tracked=id},alert:message=>assert.fail(message),
        fetch:(url,options)=>{calls.push({url,body:JSON.parse(options.body)});return new Promise(r=>resolve=r)}};
    vm.createContext(context);vm.runInContext(source('applyChanges'),context);
    const pending=context.applyChanges();
    assert.equal(calls.length,1);
    assert.equal(calls[0].url,'/api/playlist/apply');
    assert.equal(calls[0].body.changes[0].new_label,'游戏');
    await context.applyChanges();
    assert.equal(calls.length,1,'Double click must not submit a second job');
    resolve({json:async()=>({job_id:'job-1'})});await pending;
    assert.equal(tracked,'job-1');
    context.workbench.operation=null;context.valid=false;
    await context.applyChanges();assert.equal(calls.length,1);
});

test('inline apply summary counts only selected renames and games needing artwork', () => {
    const changes=[{new_label:'游戏',original_item_label:'Game',missing:true},
        {new_label:'Same',original_item_label:'Same',missing:false}];
    const context={currentChanges:[...changes,{}],needsCoverDownload:change=>change.missing,currentUILanguage:'zh'};
    vm.createContext(context);vm.runInContext(source('buildApplySummary')+source('formatApplySummaryText'),context);
    const summary=context.buildApplySummary(changes,{write_names:true,download_thumbnails:true});
    assert.equal(context.formatApplySummaryText(summary),'已选 2 项 · 修改名称 1 项 · 为 1 个游戏补全图片 · 跳过 1 项');
    const imagesOnly=context.buildApplySummary(changes,{write_names:false,download_thumbnails:true});
    assert.equal(imagesOnly.renamed,0);
    assert.match(context.formatApplySummaryText(imagesOnly),/保留当前名称/);
});

test('partial image failure preserves verified name snapshot and enables image-only retry', async () => {
    const row={proposal_id:'p',index:0,path:'/roms/Game.cue',original_label:'Game',original_item_label:'Game',
        original_db_name:'Saturn.lpl',original_item_snapshot:{path:'/roms/Game.cue',label:'Game'},new_label:'游戏',
        thumbnail_source:'Game (Japan)',system:'Saturn',match_status:'matched'};
    const context={currentChanges:[row],lastAppliedChangeKeys:new Set(['p']),lastAppliedWriteNames:true,lastAppliedDownloadEnabled:true,
        normalizeDownloadKey:v=>String(v||'').toLowerCase(),uiText:v=>v,workbenchText:zh=>zh,getRepairMode:()=> 'both',
        updateSummary:()=>{},renderPreviewTable:()=>{},repairActionStatus};
    vm.createContext(context);
    for (const name of ['getChangeIdentity','writebackMatchesChange','findWritebackRecord','findBoxartDownloadResult','applyCompletedJobToPreview']) vm.runInContext(source(name),context);
    const details=['Named_Boxarts','Named_Snaps','Named_Titles'].map((type,index)=>({type,game:'游戏',system:'Saturn',source:'Game (Japan)',
        status:index===1?'failed':'success',reason:index===1?'network_error':undefined,path:index===1?undefined:'/images/'+type+'.png',message:index===1?'连接失败':'下载成功'}));
    const result={download_summary:{writeback:{applied:[{proposal_id:'p',new_label:'游戏',actual_index:0}],failed:[],skipped:[]},details}};
    context.applyCompletedJobToPreview(result);
    assert.equal(row.applied,false);assert.equal(row.name_applied,true);assert.equal(row.enabled,true);
    assert.equal(row.original_item_snapshot.label,'游戏');assert.equal(row.original_item_label,'游戏');
    assert.equal(repairActionStatus(row),'download');
    assert.equal(row.artwork.Named_Boxarts.status,'exists');assert.equal(row.artwork.Named_Snaps.status,'failed');
    assert.equal(row.artwork_message,'连接失败');
    for (const name of ['normalizeDisplayName','hasChineseDisplayName','currentMatchesWriteName','getMatchInfo']) vm.runInContext(source(name),context);
    const refreshed={new_label:'游戏',original_item_label:'游戏',thumbnail_source:'Game (Japan)',match_status:'download',
        artwork:{Named_Boxarts:{status:'exists'},Named_Snaps:{status:'missing'},Named_Titles:{status:'exists'}}};
    assert.equal(context.getMatchInfo(row).label,context.getMatchInfo(refreshed).label);
    assert.equal(context.getMatchInfo(row).kind,context.getMatchInfo(refreshed).kind);
    const complete={...refreshed,artwork:{Named_Boxarts:{status:'exists'},Named_Snaps:{status:'exists'},Named_Titles:{status:'exists'}}};
    assert.equal(context.getMatchInfo(complete).label,'无需修复');
    assert.equal(context.getMatchInfo(complete).kind,'ready');
    let sent;
    Object.assign(context,{workbenchSnapshot:()=>({canApply:true}),document:{getElementById:()=>({value:'games.lpl'})},
        getThumbnailsDirectory:()=>'/images',getIncludedChanges:()=>[row],currentMatchesWriteName:()=>true,
        getProcessingOptions:()=>({write_names:true,download_thumbnails:true}),beginWorkbenchOperation:()=>true,
        renderWorkbench:()=>{},showStatus:()=>{},rememberAppliedChanges:()=>{},trackProgress:()=>{},
        fetch:async(url,options)=>{sent=JSON.parse(options.body);return {json:async()=>({job_id:'retry'})}}});
    vm.runInContext(source('applyChanges'),context);
    await context.applyChanges();assert.equal(sent.options.write_names,false);
    details[1]={...details[1],status:'success',path:'/images/snap.png'};
    context.lastAppliedWriteNames=false;context.applyCompletedJobToPreview(result);
    assert.equal(row.applied,true);assert.equal(row.enabled,false);assert.equal(row.name_applied,true);
});

test('missing gallery source and filename conflicts remain reviewable instead of completed', () => {
    for (const reason of ['not_found','filename_collision']) {
        const row={proposal_id:'p',new_label:'游戏',thumbnail_source:'Unmatched',system:'Saturn',original_item_label:'Game'};
        const context={currentChanges:[row],lastAppliedChangeKeys:new Set(['p']),lastAppliedWriteNames:true,lastAppliedDownloadEnabled:true,
            normalizeDownloadKey:v=>String(v||'').toLowerCase(),uiText:v=>v,updateSummary:()=>{},renderPreviewTable:()=>{}};
        vm.createContext(context);
        for (const name of ['getChangeIdentity','writebackMatchesChange','findWritebackRecord','findBoxartDownloadResult','applyCompletedJobToPreview']) vm.runInContext(source(name),context);
        context.applyCompletedJobToPreview({download_summary:{writeback:{applied:[{proposal_id:'p'}]},
            details:[{type:'Named_Boxarts',system:'Saturn',game:'游戏',source:'Unmatched',status:'failed',reason}]}});
        assert.equal(row.applied,false);assert.equal(row.artwork_blocked,true);assert.equal(row.enabled,false);
        assert.equal(repairActionStatus(row),'incomplete');
    }
});

test('a missing secondary image remains retryable and agrees with refreshed file states', () => {
    const row={proposal_id:'p',new_label:'游戏',original_item_label:'游戏',thumbnail_source:'Game (Japan)',system:'PS1'};
    const context={currentChanges:[row],lastAppliedChangeKeys:new Set(['p']),lastAppliedWriteNames:false,lastAppliedDownloadEnabled:true,
        normalizeDownloadKey:v=>String(v||'').toLowerCase(),uiText:v=>v,updateSummary:()=>{},renderPreviewTable:()=>{}};
    vm.createContext(context);
    for(const name of ['getChangeIdentity','writebackMatchesChange','findWritebackRecord','findBoxartDownloadResult','applyCompletedJobToPreview'])vm.runInContext(source(name),context);
    context.applyCompletedJobToPreview({download_summary:{writeback:{applied:[{proposal_id:'p'}]},details:
        ['Named_Boxarts','Named_Snaps','Named_Titles'].map(type=>({type,game:'游戏',system:'PS1',source:'Game (Japan)',
            status:type==='Named_Titles'?'failed':'success',reason:type==='Named_Titles'?'not_found':undefined,path:'/images/'+type+'.png'}))}});
    assert.equal(row.applied,false);assert.equal(row.artwork_blocked,false);assert.equal(row.enabled,true);
    assert.equal(repairActionStatus(row),'download');
    const refreshed={...row,applied:false,artwork:{Named_Boxarts:{status:'exists'},Named_Snaps:{status:'exists'},Named_Titles:{status:'missing'}}};
    assert.equal(repairActionStatus(row),repairActionStatus(refreshed));
    const {previewArtworkState}=require('../src/templates/workflow.js');
    assert.equal(previewArtworkState(row),'partial');
    assert.equal(previewArtworkState({...refreshed,cover_exists:true}),'partial');
});

test('unselected artwork versions show an actual candidate without marking it downloaded or selected', () => {
    const context={hasExistingCover:c=>Boolean(c.cover_exists),getRemoteCoverUrl:()=>'',encodeURIComponent};
    vm.createContext(context);vm.runInContext(source('getCoverPreviewUrl'),context);
    const row={system:'Sega - Saturn',thumbnail_source:null,artwork_candidates:['Dragon Force (Japan) (4M)'],artwork_gallery_status:'ambiguous'};
    const url=context.getCoverPreviewUrl(row);
    assert.equal(url,'/api/artwork/thumbnail?system=Sega%20-%20Saturn&kind=Named_Boxarts&name=Dragon%20Force%20(Japan)%20(4M)');
    assert.equal(row.thumbnail_source,null);assert.equal(row.cover_exists,undefined);
    assert.equal(context.getCoverPreviewUrl({...row,cover_exists:true,cover_path:'mtp://device/existing.png'}),'/api/thumbnail/preview?path=mtp%3A%2F%2Fdevice%2Fexisting.png');
    assert.equal(context.getCoverPreviewUrl({...row,artwork_gallery_status:'unavailable'}),'');
});

test('preview recommends verified artwork without losing disc constraints or existing choices', () => {
    let mode='both';
    const context={getRepairMode:()=>mode,shouldAutoSelectChange:c=>Boolean(c.thumbnail_source),currentMatchesWriteName:()=>true};
    vm.createContext(context);vm.runInContext(source('preparePreviewChanges'),context);
    const pending={new_label:'格兰蒂亚 (Disc 1)',original_item_label:'格兰蒂亚 (Disc 1)',
        artwork_identity_status:'resolved',artwork_gallery_status:'ambiguous',artwork_review_only:false,
        artwork_candidates:['Grandia (Japan) (Disc 1) (4M)','Grandia (Japan) (Disc 1) (1M)'],
        match_status:'review',needs_review:true};
    const row=context.preparePreviewChanges([pending])[0];
    assert.equal(row.thumbnail_source,'Grandia (Japan) (Disc 1) (1M)');
    assert.equal(row.artwork_recommended,true);assert.equal(row.enabled,true);
    assert.equal(repairActionStatus(row),'download');
    assert.equal(row.cover_exists,undefined);assert.equal(row.artwork_source_confirmed,undefined);
    assert.equal(pending.thumbnail_source,undefined);
    const dragon={...pending,artwork_candidates:['Dragon Force (Europe)','Dragon Force (USA)','Dragon Force (Japan) (4M)']};
    assert.equal(context.preparePreviewChanges([dragon])[0].thumbnail_source,'Dragon Force (Japan) (4M)');
    assert.equal(context.preparePreviewChanges([{...pending,thumbnail_source:'Manual choice'}])[0].thumbnail_source,'Manual choice');
    assert.equal(context.preparePreviewChanges([{...pending,artwork_gallery_status:'unavailable'}])[0].thumbnail_source,undefined);
    assert.equal(context.preparePreviewChanges([{...pending,artwork_identity_status:'unresolved'}])[0].thumbnail_source,undefined);
    mode='names';
    assert.equal(context.preparePreviewChanges([pending])[0].thumbnail_source,undefined);
});

test('Android directory suggestions keep storage mounts separate and require an exact folder', () => {
    const context={}; vm.createContext(context); vm.runInContext(source('androidDirectoryCandidates'),context);
    const items=[{rom_path:'/storage/4A21-0000/Roms/SS/Game/Game.cue'},
        {rom_path:'/storage/4A21-0000/Roms/SS/Other.cue'},
        {rom_path:'/storage/emulated/0/Roms/SS/Game.cue'},
        {rom_path:'/storage/4A21-0000/Roms/SSF/Game.cue'},
        {rom_path:'mtp://device/id/Roms/SS/Game.cue'}];
    assert.deepEqual(Array.from(context.androidDirectoryCandidates(items,'mtp://device/00020001/Roms/SS')),
        ['/storage/4A21-0000/Roms/SS','/storage/emulated/0/Roms/SS']);
    assert.deepEqual(Array.from(context.androidDirectoryCandidates(items,'mtp://device/00020001/')),[]);
});

test('starting without an Android path focuses the field without submitting a scan', async () => {
    let focused='', requests=0;
    const fields={directory:{value:'mtp://device/00020001/Roms/SS'},android:{value:''},
        'android-suggestions':{hidden:false},status:{},start:{}};
    fields.android.setAttribute=()=>{}; fields.android.scrollIntoView=()=>{};
    fields.android.focus=()=>{focused='android';};
    const context={uiText:text=>text,contentScan:{busy:false,setup:{android:true}},contentField:n=>fields[n],
        invalidateContentScan:()=>{},loadContentHints:async()=>{},contentJob:async()=>{requests++;}};
    vm.createContext(context);
    vm.runInContext(source('focusContentScanField')+source('previewContentScan'),context);
    await context.previewContentScan();
    assert.equal(focused,'android'); assert.equal(requests,0);
    assert.match(fields.status.textContent,/使用所选路径/);
});

test('confirming a suggested Android path invalidates preview without starting or writing', () => {
    let invalidated=false;
    const fields={'android-candidates':{value:'/storage/4A21-0000/Roms/SS'},android:{removeAttribute:()=>{}},status:{}};
    const context={uiText:text=>text,contentField:n=>fields[n],invalidateContentScan:()=>{invalidated=true;}};
    vm.createContext(context);vm.runInContext(source('useContentAndroidPath'),context);
    context.useContentAndroidPath();
    assert.equal(fields.android.value,'/storage/4A21-0000/Roms/SS');assert.equal(invalidated,true);
    assert.match(fields.status.textContent,/不会立即写入/);
});

test('directory hints fill the unique Android path automatically and preserve manual edits', async () => {
    const fields={directory:{value:'mtp://device/00020001/Roms/SS'},system:{value:'Sega - Saturn'},
        android:{value:'',removeAttribute:()=>{}},status:{},'android-suggestions':{},
        'android-candidates':{replaceChildren:()=>{}}};
    const context={uiText:text=>text,contentHintGeneration:0,contentScan:{setup:{android:true}},contentField:n=>fields[n],
        contentPayload:()=>({root:'mtp://device/00010001/RetroArch',directory:fields.directory.value,system:fields.system.value}),
        currentDeviceScan:{root_path:'mtp://device/00010001/RetroArch',playlists:[{valid:true,system:'Sega - Saturn',path:'SS.lpl'}]},
        URLSearchParams,Option:function(text,value){this.value=value;},
        desktopRequest:async url=>url.startsWith('/api/playlist/items')?{items:[{rom_path:'/storage/4A21-0000/Roms/SS/Game.cue'}]}:{}};
    Object.assign(context,{loadContentCoreStatus:()=>{},renderContentConfiguration:()=>{}});
    vm.createContext(context);vm.runInContext(source('androidDirectoryCandidates')+source('loadContentHints'),context);
    await context.loadContentHints();
    assert.equal(fields.android.value,'/storage/4A21-0000/Roms/SS');assert.equal(fields['android-suggestions'].hidden,true);
    fields.android.value='/storage/manual/Roms/SS';await context.loadContentHints();
    assert.equal(fields.android.value,'/storage/manual/Roms/SS');
});

test('choosing an SS folder detects Saturn even when the initial system is NES', async () => {
    let changed=false;
    const fields={directory:{value:'mtp://device/00020001/Roms/SS'},system:{value:'NES'}};
    const context={uiText:text=>text,contentHintGeneration:0,contentScan:{setup:{systems:[{name:'Sega - Saturn'}]}},contentField:n=>fields[n],
        contentPayload:()=>({root:'root',directory:fields.directory.value,system:'NES'}),URLSearchParams,
        currentDeviceScan:{root_path:'root',playlists:[{valid:true,system:'NES',path:'NES.lpl'},{valid:true,system:'Sega - Saturn',path:'SS.lpl'}]},
        changeContentSystem:()=>{changed=true;},
        desktopRequest:async url=>({items:[{rom_path:url.includes('SS.lpl')?'/storage/4A21-0000/Roms/SS/Game.cue':'/storage/4A21-0000/Roms/NES/Game.nes'}]})};
    Object.assign(context,{loadContentCoreStatus:()=>{},renderContentConfiguration:()=>{}});
    vm.createContext(context);vm.runInContext(source('androidDirectoryCandidates')+source('loadContentHints'),context);
    await context.loadContentHints(true);
    assert.equal(fields.system.value,'Sega - Saturn');assert.equal(changed,true);
});

test('scan adopts the currently browsed directory and waits for system/path detection', async () => {
    const fields={directory:{value:''},android:{value:''},'core-path':{value:''},status:{},start:{}};
    let submitted;
    const picker={hidden:false};
    const context={contentScan:{browserPath:'mtp://device/00020001/Roms/SS',setup:{android:true}},
        contentField:n=>fields[n],document:{getElementById:id=>id==='content-directory-picker'?picker:{disabled:false}},
        invalidateContentScan:()=>{},chooseContentDirectory:async()=>{
            await Promise.resolve();fields.directory.value='mtp://device/00020001/Roms/SS';
            fields.android.value='/storage/card/Roms/SS';fields['core-path'].value='/cores/saturn.so';picker.hidden=true;
        },contentPayload:()=>({directory:fields.directory.value,android_directory:fields.android.value}),
        contentInfoGeneration:0,contentJob:async(path,payload)=>{submitted=payload;throw Error('stop after read-only submission');}};
    vm.createContext(context);vm.runInContext(source('previewContentScan'),context);
    await context.previewContentScan();
    assert.equal(submitted.directory,'mtp://device/00020001/Roms/SS');
    assert.equal(submitted.android_directory,'/storage/card/Roms/SS');assert.equal(picker.hidden,true);
});
