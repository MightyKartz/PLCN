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
    const elements={
        'thumbnails_override':{value:''},
        'rom_name_cn_path':{value:''},
    };
    const context={workbench:{operation:null},completionJobIds:new Set(),
        currentDeviceScan:{directories:{playlists:'/lib/playlists',thumbnails_exists:true}},
        document:{getElementById:id=>elements[id]},
        beginWorkbenchOperation:()=>true,endWorkbenchOperation:()=>{},
        workbenchText:zh=>zh,getThumbnailsDirectory:()=>'/lib/thumbnails',
        renderWorkbench:()=>{},refreshAfterCompletion:()=>{},invalidateWorkbenchPreview:()=>{},
        finishBatchRun:(...args)=>{finished=args;},
        watchCompletionJob:async jobId=>jobId==='preview-1'?context.analysis:context.applyResult,
        desktopRequest:async(url,body)=>{calls.push({url,body});
            return url==='/api/batch/preview'?{job_id:'preview-1'}:url==='/api/batch/apply'?{job_id:'apply-1'}:{};}};
    vm.createContext(context);vm.runInContext(source('runAllSystemsCompletion'),context);
    context.analysis={can_apply:true,rows:[]};context.applyResult={receipt_id:'r1'};
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
        const context={workbench:{operation:null}, completionJobIds:new Set(), EventSource:class {constructor(){events=this;} close(){closed=true;}},
            renderWorkbench:()=>{}, workbenchText:zh=>zh, downloadTaskOutcome,
            showStatus:(message,type)=>notices.push({message,type}),
            applyCompletedJobToPreview:()=>applied++, desktopDialog:{open:true}, desktopView:'completion',
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

test('direct completion reports applied games and counts only review items as manual work', async () => {
    const toasts=[]; let previewed;
    const elements={'playlist_path':{value:'/lib/SNES.lpl'},'system_name':{value:'SNES'}};
    const changes=[
        {index:0,new_label:'暗影狂奔',thumbnail_source:'Shadowrun (USA)',actionable:true},
        {index:1,new_label:'极速传说',thumbnail_source:'F-Zero',actionable:false},
        {index:2,new_label:'存疑游戏',thumbnail_source:'Dubious',identity:{requires_review:true},actionable:false},
    ];
    const context={workbench:{operation:null},completionJobIds:new Set(),
        document:{getElementById:id=>elements[id]||{value:'',disabled:false}},
        getProcessingOptions:()=>({download_thumbnails:true,write_names:true}),
        getThumbnailsDirectory:()=>'/thumbs',
        beginWorkbenchOperation:()=>true,endWorkbenchOperation:()=>{},
        invalidateWorkbenchPreview:()=>{},renderWorkbench:()=>{},refreshAfterCompletion:()=>{},
        workbenchInputKey:()=>'k',saveConfig:async()=>true,
        desktopRequest:async(url)=>url==='/api/playlist/preview'?{changes}:{job_id:'apply-1'},
        preparePreviewChanges:list=>list,isActionableChange:c=>c.actionable===true,
        currentMatchesWriteName:()=>false,
        watchCompletionJob:async()=>({applied_count:1,receipt_id:'r1',download_summary:{types:{}}}),
        showActionToast:toast=>toasts.push(toast),
        workbenchText:zh=>zh,uiText:x=>x,previewTask:scope=>{previewed=scope;},
        openDesktop:()=>{}};
    vm.createContext(context);
    vm.runInContext(source('needsManualReview')+source('runDirectCompletion'),context);
    await context.runDirectCompletion();
    assert.equal(toasts.length,1);
    assert.equal(toasts[0].message,'已补全 1 个游戏，1 个游戏需手动处理');
    assert.equal(toasts[0].receiptId,'r1');
    toasts[0].details();
    assert.notEqual(previewed,undefined);
});

for (const closed of [true, false]) {
    test(`operation history ignores a response after ${closed ? 'closing' : 'a newer refresh'}`, async () => {
        let finish;
        let renders = 0;
        const dialog = {open:true};
        const body = {replaceChildren:()=>{renders++;}};
        const context = {desktopRenderVersion:0, desktopView:'completion', desktopDialog:dialog,
            document:{getElementById:()=>body}, syncIdleButtons:()=>{},
            desktopRequest:url=>url === '/api/desktop'
                ? new Promise(resolve=>{finish=resolve;})
                : Promise.resolve({receipts:[]})};
        vm.createContext(context);vm.runInContext(source('refreshDesktop'),context);
        const pending=context.refreshDesktop();
        if (closed) dialog.open=false; else context.desktopRenderVersion++;
        finish({jobs:[]});await pending;
        assert.equal(renders,0);
    });
}

for (const state of [{applying:true}, {jobId:'writing'}]) {
    test(`game selection stays fixed while artwork is ${state.applying ? 'applying' : 'awaiting its result'}`, () => {
        const context={gameInspector:{saving:false},artworkDialogState:state,gameLibrary:{activeIndex:0},
            renderGameLibrary:()=>{throw Error('must not switch during a write');}};
        vm.createContext(context);vm.runInContext(source('inspectGame'),context);
        context.inspectGame(1);
        assert.equal(context.gameLibrary.activeIndex,0);
    });
}

for (const launchFolder of ['', '/storage/CARD/Roms/MD']) {
    test(`import ${launchFolder ? 'recovers the launch folder and enables confirmation' : 'keeps confirmation visible and explains a missing launch folder'}`, async () => {
        let focused=false, submitted;
        const fields={apply:{},destination:{value:'mtp://device/00020001/Roms/MD'},system:{value:'MD'},
            android:{value:'',parentElement:{hidden:true},setAttribute(){},removeAttribute(){},scrollIntoView(){},focus(){focused=true;}},
            playlist:{value:'MD.lpl'},'destination-fields':{},'playlist-path':{}};
        const context={gameManagement:{sources:['Game.md'],setup:{android:true},generation:1,analysisToken:0},
            gmField:id=>fields[id],gmStatus:()=>{},workbenchText:zh=>zh,gmError:error=>error.message,
            document:{getElementById:()=>({setAttribute(){}})},
            desktopRequest:async()=>({android_directory:launchFolder}),
            gmJob:async(url,payload)=>{submitted=payload;return {id:'preview',result:{files:[],playlist:'MD.lpl',can_apply:true,required_bytes:10,free_bytes:100,added:[{}]}};},
            gmRenderFiles:()=>{},gameSize:String};
        vm.createContext(context);vm.runInContext(source('previewGameImport'),context);
        await context.previewGameImport();
        assert.equal(fields.apply.hidden,false);
        assert.equal(fields.apply.disabled,!launchFolder);
        assert.equal(focused,!launchFolder);
        if (launchFolder) assert.equal(submitted.android_directory,launchFolder);
        else {assert.equal(submitted,undefined);assert.equal(fields['destination-fields'].hidden,false);}
    });
}

test('import uses the decoded filename of an existing MTP playlist', () => {
    const system='Sega - Mega Drive - Genesis';
    const fields={system:{value:system},destination:{},android:{},playlist:{}};
    const context={gmField:id=>fields[id],gameManagement:{setup:{profiles:[]},root:'mtp://device/00020001/RetroArch'},
        currentDeviceScan:{playlists:[{valid:true,system,path:'mtp://device/00020001/RetroArch/playlists/Sega%20-%20Mega%20Drive%20-%20Genesis.lpl'}]},
        getSystemAbbreviation:()=> 'MD',gmInvalidate:()=>{},gmRenderDestinationSummary:()=>{},gmAutoAnalyze:()=>{}};
    vm.createContext(context);vm.runInContext(source('gmChangeSystem'),context);context.gmChangeSystem();
    assert.equal(fields.playlist.value,system+'.lpl');
});

test('new handheld system requires an explicit copy directory instead of using the library storage', () => {
    const fields={system:{value:'MD'},destination:{},android:{},playlist:{}};
    const context={gmField:id=>fields[id],gameManagement:{setup:{android:true,profiles:[]},root:'mtp://device/00010001/RetroArch'},
        currentDeviceScan:{playlists:[]},getSystemAbbreviation:()=> 'MD',gmInvalidate:()=>{},gmRenderDestinationSummary:()=>{},gmAutoAnalyze:()=>{}};
    vm.createContext(context);vm.runInContext(source('gmChangeSystem'),context);context.gmChangeSystem();
    assert.equal(fields.destination.value,'');
    assert.equal(fields.android.value,'');
});

test('an expired local session is renewed once before repeating a rejected request', async () => {
    const calls=[];
    const json={ok:true,status:200,headers:{get:()=> 'application/json'},json:async()=>({job_id:'one-job'})};
    const context={fetch:async(url,options)=>{calls.push({url,options});return calls.length===1?{status:403}:calls.length===2?{ok:true}:json;},desktopText:zh=>zh};
    vm.createContext(context);vm.runInContext(source('desktopRequest'),context);
    const result=await context.desktopRequest('/api/games/apply',{preview_job_id:'preview'});
    assert.equal(result.job_id,'one-job');
    assert.deepEqual(calls.map(c=>c.url),['/api/games/apply','/','/api/games/apply']);
    assert.equal(calls[0].options.body,calls[2].options.body);
});

test('a network failure never automatically repeats a possible write', async () => {
    let calls=0;
    const context={fetch:async()=>{calls++;throw Error('offline');},desktopText:zh=>zh};
    vm.createContext(context);vm.runInContext(source('desktopRequest'),context);
    await assert.rejects(context.desktopRequest('/api/games/apply',{}),/offline/);
    assert.equal(calls,1);
});

test('an HTML error response produces a readable connection error instead of parsing HTML as JSON', async () => {
    const context={fetch:async()=>({status:500,headers:{get:()=> 'text/html'},json:()=>{throw Error('must not parse HTML');}}),desktopText:zh=>zh};
    vm.createContext(context);vm.runInContext(source('desktopRequest'),context);
    await assert.rejects(context.desktopRequest('/api/content/setup'),/连接已失效/);
});

test('reconnecting keeps the selected source and destination while preparing a fresh analysis', async () => {
    const fields={reconnect:{disabled:false}};
    const context={gameManagement:{setup:{android:true},sources:['selected.md']},gmField:id=>fields[id],
        fetch:async()=>({ok:true}),desktopRequest:async()=>({}),gmInvalidate:()=>{},
        previewGameImport:async()=>{context.analyzed=true;},gmStatus:()=>{},gmError:error=>error.message};
    vm.createContext(context);vm.runInContext(source('reconnectGameImport'),context);
    await context.reconnectGameImport();
    assert.deepEqual(context.gameManagement.sources,['selected.md']);
    assert.equal(context.analyzed,true);assert.equal(fields.reconnect.disabled,false);
});

test('an unverified import mapping keeps selected sources visible and blocks confirmation', async () => {
    const fields={apply:{},android:{value:'/storage/CARD/Roms/MD'},destination:{value:'mtp://device/00010001/Roms/MD'},system:{value:'MD'},playlist:{value:'MD.lpl'},'playlist-path':{},'mapping-status':{}};
    const context={gameManagement:{sources:['Selected.md'],generation:1,analysisToken:0,setup:{android:true}},
        gmField:id=>fields[id],workbenchText:zh=>zh,gmStatus:()=>{},gmRenderFiles:()=>{},
        gmJob:async()=>({id:'preview',result:{mapping_state:'unverified',files:[],playlist:'MD.lpl',can_apply:false}})};
    vm.createContext(context);vm.runInContext(source('previewGameImport'),context);
    await context.previewGameImport();
    assert.equal(context.gameManagement.analysisFiles,null);
    assert.deepEqual(context.gameManagement.sources,['Selected.md']);
    assert.equal(fields.apply.hidden,false);assert.equal(fields.apply.disabled,true);
    assert.match(fields['mapping-status'].textContent,/待核对/);
});

for (const confirmed of [false,true]) {
    test(`inline mapping ${confirmed ? 'saves explicit manual configuration and retains sources' : 'requires the handheld confirmation before saving'}`, async () => {
        let saved=false, analyzed=false;
        const fields={'mapping-confirm':{checked:confirmed},destination:{value:'mtp://device/00020001/Roms/MD'},system:{value:'MD'},android:{value:'/storage/CARD/Roms/MD'},playlist:{value:'MD.lpl'}};
        const context={matchMedia:()=>({matches:false,addEventListener(){}}),gameManagement:{root:'mtp://device/00010001/RetroArch',sources:['Chosen.md'],setup:{profiles:[]}},gmField:id=>fields[id],gmStatus:()=>{},workbenchText:zh=>zh,
            gmJob:async(route,payload)=>{assert.equal(payload.confirmed,true);saved=true;return {result:{profiles:[{mapping_source:'manual'}]}};},
            gmInvalidate:()=>{},previewGameImport:async()=>{analyzed=true;},gmError:error=>error.message};
        vm.createContext(context);vm.runInContext(source('saveGameImportMapping'),context);
        await context.saveGameImportMapping();
        assert.equal(saved,confirmed);assert.equal(analyzed,confirmed);
        assert.deepEqual(context.gameManagement.sources,['Chosen.md']);
    });
}

test('selecting identical ROM content clears a previously prepared replacement', async()=>{
    const context={gameInspector:{romPlan:{id:'older-version'},status:'old status'},
        inspectorJob:async()=>({result:{can_apply:false}}),workbenchText:zh=>zh,renderGameInspector:()=>{}};
    vm.createContext(context);vm.runInContext(source('prepareRomUpdate'),context);
    await context.prepareRomUpdate({source:'same-content.gba'});
    assert.equal(context.gameInspector.romPlan,null);
    assert.match(context.gameInspector.status,/无需更新/);
});

test('updating an import conflict waits for the selected library before preparing its ROM',async()=>{
    let prepared=false, loaded=false;
    const candidate={playlist:'GBA.lpl',expected:'snapshot',index:2,source:'new.gba'};
    const context={workbench:{operation:null},closeGameManagement:()=>{},currentDeviceScan:{playlists:[{path:'GBA.lpl'}]},
        selectScannedPlaylist:async()=>{},gameLibrary:{loading:true,data:null},gameLibraryInput:()=>['GBA.lpl','GBA','images'],
        loadGameLibrary:async()=>{loaded=true;context.gameLibrary.data={expected:'snapshot'};},inspectGame:()=>{},
        prepareRomUpdate:async payload=>{assert.equal(loaded,true);assert.equal(payload.source,'new.gba');prepared=true;},
        showGameLibraryToast:message=>{throw Error(message);},gmError:error=>error.message,workbenchText:zh=>zh};
    vm.createContext(context);vm.runInContext(source('updateImportedRom'),context);await context.updateImportedRom(candidate);
    assert.equal(prepared,true);
});
for (const errors of [[], ['NES: playlist changed']]) {
    test(`all-systems completion reports ${errors.length} failed playlists and retains undo`, () => {
        let toast;
        const context = {
            invalidateWorkbenchPreview: () => {}, workbenchText: zh => zh,
            showActionToast: value => { toast = value; }, openOperationHistory: () => 'completion',
            batchRunCreatedArtworkDir: false
        };
        vm.createContext(context);
        vm.runInContext(source('finishBatchRun'), context);
        context.finishBatchRun('completed', {rows: []}, {
            applied_count: 2, receipt_id: 'partial-receipt', errors, playlists: [], download_summary: {types: {}}
        });
        assert.equal(toast.message, errors.length ? '已补全 2 个游戏，1 个列表处理失败' : '已补全 2 个游戏');
        assert.equal(toast.receiptId, 'partial-receipt');
        assert.equal(toast.details(), 'completion');
    });
}
