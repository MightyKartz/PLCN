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
        getRepairMode:()=> 'both', uiText:x=>x, hasExistingCover:()=>false};
    vm.createContext(context);
    vm.runInContext(source('getCoverStatusInfo'),context);
    const game={new_label:'仙剑奇侠传',original_item_label:'仙剑奇侠传',thumbnail_source:null,
        artwork_query:'Sword and Fairy',artwork_identity_status:'resolved',artwork_gallery_status:'not_found'};
    assert.equal(repairActionStatus(game),'incomplete');
    assert.equal(context.getCoverStatusInfo(game).label,'官方图库无');
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

test('preview options reject turning both operations off, and otherwise reanalyze', async () => {
    let previews=0, mode='names';
    const control={checked:false};
    const context={getProcessingOptions:()=>({write_names:mode!=='none',download_thumbnails:mode==='both'}),
        previewTask:async()=>{previews++;},showStatus:()=>{},workbenchText:zh=>zh};
    vm.createContext(context);vm.runInContext(source('changePreviewOptions'),context);
    await context.changePreviewOptions(control);assert.equal(previews,1);
    mode='none';await context.changePreviewOptions(control);
    assert.equal(control.checked,true);assert.equal(previews,1);
});

test('batch application sends only the reviewed job, never fresh paths or proposals', async () => {
    let sent, tracked;
    const context={batchReviewId:'review-1',workbench:{operation:null},
        document:{getElementById:id=>({disabled:false,checked:true,close:()=>{},addEventListener:()=>{}})},
        beginWorkbenchOperation:()=>true,desktopRequest:async(url,body)=>{sent={url,body};return {job_id:'apply-1'};},
        invalidateWorkbenchPreview:()=>{},showLogPanel:()=>{},trackProgress:(...args)=>{tracked=args;}};
    vm.createContext(context);vm.runInContext(source('applyBatchReview'),context);
    await context.applyBatchReview();
    assert.equal(sent.url,'/api/batch/apply');
    assert.equal(sent.body.preview_job_id,'review-1');
    assert.equal(Object.hasOwn(sent.body,'batch_dir'),false);
    assert.equal(Object.hasOwn(sent.body,'changes'),false);
    assert.equal(context.batchReviewId,null);
    assert.deepEqual(tracked,['apply-1','batch']);
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
