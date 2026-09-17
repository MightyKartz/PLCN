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
    assert.deepEqual(state.steps, ['current','waiting','waiting']);
    assert.equal(state.hasLibrary, false);
    assert.equal(state.canApply, false);
    assert.equal(state.canPreview, false);
});
test('scanned library requires an explicit list choice', () => {
    const state = deriveWorkbenchState({scanned:true,previewKey:null,inputKey:'a',selected:0});
    assert.equal(state.hasLibrary,true);
    assert.equal(state.canPreview,false);
    assert.deepEqual(state.steps,['done','waiting','waiting']);
});
test('valid playlist permits a preview, not a write without proposals', () => {
    const state = deriveWorkbenchState({...ready,previewKey:null});
    assert.equal(state.canPreview,true);
    assert.equal(state.canApply,false);
    assert.deepEqual(state.steps,['done','current','waiting']);
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
        assert.equal(state.canBatch,false);
    });
}
test('failed or cancelled apply does not claim completion and allows recovery', () => {
    const state=deriveWorkbenchState({...ready,operation:null,applied:false});
    assert.equal(state.canApply,true);
    assert.equal(state.steps[2],'waiting');
    assert.equal(deriveWorkbenchState({...ready,applied:true}).steps[2],'done');
});
test('batch requires its own target and image folder', () => {
    assert.equal(deriveWorkbenchState({...ready}).canBatch,false);
    assert.equal(deriveWorkbenchState({...ready,batchDir:'lists'}).canBatch,false);
    assert.equal(deriveWorkbenchState({...ready,batchDir:'lists',download:false}).canBatch,true);
});

// Exercise the real filtering function, including the old accidental inversion regression.
const fs=require('node:fs');
const vm=require('node:vm');
const page=fs.readFileSync(require('node:path').join(__dirname,'../src/templates/plcn.html'),'utf8');
function source(name,next) { return page.slice(page.indexOf('        function '+name),page.indexOf('        function '+next)); }
test('clicking All twice preserves row selection', () => {
    const context={currentPreviewFilter:'all',currentChanges:[{enabled:true}], document:{querySelectorAll:()=>[]},renderPreviewTable:()=>{},renderWorkbench:()=>{}};
    vm.createContext(context);
    vm.runInContext(source('setPreviewFilter','invertVisibleSelection'),context);
    const button={classList:{add:()=>{},contains:()=>true}};
    context.setPreviewFilter('all',button); context.setPreviewFilter('all',button);
    assert.equal(context.currentChanges[0].enabled,true);
});
test('manual confirmation moves a review item into actionable filter', () => {
    const context={currentPreviewFilter:'review',getMatchInfo:c=>({kind:c.review_confirmed?'reviewed':c.match_status}),isActionableChange:c=>c.review_confirmed===true,isEditedChange:()=>false};
    vm.createContext(context);vm.runInContext(source('matchesFilter','isEditedChange'),context);
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
    vm.runInContext(desktopSource.slice(desktopSource.indexOf('const builtInFilePicker'),desktopSource.indexOf('function setRepairMode')),context);
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
    vm.runInContext(page.slice(page.indexOf('        async function loadFileList('),page.indexOf('        function selectFile(')),context);
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

test('Escape defers to the browser while a modal is open instead of closing its parent', () => {
    let handler, active=true, closed=0;
    const context={document:{addEventListener:(_type,callback)=>{handler=callback;},querySelector:()=>active?{}:null},
        closeModal:()=>closed++,closeSearchModal:()=>closed++,closeProjectDocs:()=>closed++,toggleDetailsDrawer:()=>closed++,closeInspector:()=>closed++};
    vm.createContext(context);
    const start=page.indexOf("        document.addEventListener('keydown',");
    vm.runInContext(page.slice(start,page.indexOf('    </script>',start)),context);
    handler({key:'Escape'});
    assert.equal(closed,0);
    active=false;handler({key:'Escape'});
    assert.equal(closed,4);
});

test('reloading config preserves the current image directories when playlist inputs reset', () => {
    const values={single_playlist_path:'one.lpl',single_system_name:'GBA',single_thumbnails_dir:'single-images',batch_thumbnails_dir:'batch-images',rom_name_cn_path:'data/rom-name-cn'};
    const elements={}; const element=id=>elements[id]||={value:'',classList:{add:()=>{},remove:()=>{},toggle:()=>{}},style:{},textContent:'',setAttribute:()=>{},disabled:false,hidden:false};
    const context={fetch:async()=>({json:async()=>values}),document:{getElementById:element},loadStats:()=>{},renderWorkbench:()=>{},showStatus:()=>{}, uiText:x=>x};
    vm.createContext(context);
    vm.runInContext(page.slice(page.indexOf('        async function loadConfig('),page.indexOf('        async function loadStats(')),context);
    return context.loadConfig().then(()=>{
        assert.equal(element('thumbnails_dir').value,'single-images');
        assert.equal(element('batch_thumbnails_dir').value,'batch-images');
    });
});
