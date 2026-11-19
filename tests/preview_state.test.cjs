const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const templates = path.join(__dirname,'../src/templates');
function model(mode='both') {
    const context = {currentUILanguage:'zh', getRepairMode:()=>mode,uiText:text=>text,currentChanges:[],currentPreviewFilter:'all'};
    vm.createContext(context);
    for (const name of ['workflow.js','repair-model.js']) vm.runInContext(fs.readFileSync(path.join(templates,name),'utf8'),context);
    return context;
}
const game = {match_status:'matched', original_item_label:'Old',new_label:'中文名', thumbnail_source:'Game (Japan)',
    identity:{state:'exact_title',requires_review:false,release_verified:false}};

test('artwork recommendation keeps gallery ambiguity and never confirms release identity',()=>{
    const c=model();
    const row=c.preparePreviewChanges([{...game,thumbnail_source:null,artwork_identity_status:'resolved',
        artwork_gallery_status:'ambiguous',artwork_candidates:['Game (USA)','Game (Japan)']}])[0];
    assert.equal(row.thumbnail_source,'Game (Japan)');assert.equal(row.artwork_gallery_status,'ambiguous');
    assert.equal(row.artwork_recommended,true);assert.equal(row.identity.release_verified,false);
    assert.equal(c.previewArtworkState(row),'available');
});

test('candidate and conflict rows never become automatic writes through a cover recommendation',()=>{
    const c=model();
    for(const state of ['candidate','conflict','unresolved']) {
        const row=c.preparePreviewChanges([{...game,identity:{state,requires_review:true},
            artwork_identity_status:'resolved',artwork_gallery_status:'ambiguous',artwork_candidates:['Game (Japan)']}])[0];
        assert.equal(row.enabled,false);assert.equal(c.isActionableChange(row),false);
        assert.equal(c.matchesFilter(row,''),true);
        assert.equal(c.buildRepairPreviewSummary([row],'both').review,1);
    }
});

test('gallery errors, no match and unidentified titles remain distinct, including when a stale source exists',()=>{
    const c=model();
    assert.equal(c.previewArtworkState({...game,artwork_gallery_status:'unavailable'}),'query_failed');
    assert.equal(c.previewArtworkState({...game,artwork_gallery_status:'not_found'}),'no_source');
    assert.equal(c.previewArtworkState({...game,artwork_gallery_status:'not_found',artwork_identity_status:'unresolved'}),'unidentified');
    assert.equal(c.previewArtworkState({...game,artwork_gallery_status:'unavailable',cover_exists:true}),'exists');
    assert.equal(c.previewArtworkState({...game,cover_download_status:'failed',cover_download_reason:'network_error'}),'failed');
});

test('row filters and summary agree and selection changes only the planned scope',()=>{
    const c=model();
    const rows=[game,{...game,enabled:false},{...game,identity:{state:'candidate',requires_review:true}},
        {...game,thumbnail_source:null,artwork_gallery_status:'unavailable'}];
    const counts=c.buildRepairPreviewSummary(rows,'both');
    assert.equal(counts.selected,1);assert.equal(counts.renamed,1);assert.equal(counts.downloads,1);
    assert.equal(counts.candidates,1);assert.equal(counts.queryFailed,1);assert.equal(counts.review,2);
    c.currentPreviewFilter='missing-cover';
    assert.equal(rows.filter(row=>c.matchesFilter(row,'')).length,counts['missing-cover']);
    assert.match(c.formatPreviewScope(counts,'repair'),/身份待核对 1 项、图库查询失败 1 项/);
    assert.match(c.formatPreviewScope({added:[{}],retained:2,skipped:3},'scan'),/此次仅更新列表/);
});

test('explicit name edits permit a chosen candidate without treating artwork-only edits as identity confirmation',()=>{
    const c=model();c.currentChanges=[{...game,identity:{state:'candidate',requires_review:true}}];
    c.markChangeEdited(0,'图片','thumbnail_source');
    assert.equal(c.isActionableChange(c.currentChanges[0]),false);
    c.markChangeEdited(0,'名称','new_label');
    assert.equal(c.isActionableChange(c.currentChanges[0]),true);
    assert.equal(c.previewIdentityLabel(c.currentChanges[0]),'手动指定名称');
});

test('names-only plans do not claim artwork problems or downloads',()=>{
    const c=model('names');
    const row={...game,artwork_gallery_status:'unavailable'};
    const counts=c.buildRepairPreviewSummary([row],'names');
    assert.equal(counts.downloads,0);assert.equal(counts.queryFailed,0);assert.equal(counts['missing-cover'],0);
});

test('a late repair preview cannot populate a different current configuration',async()=>{
    const script=fs.readFileSync(path.join(templates,'preview.js'),'utf8');
    const start=script.indexOf('async function previewTask('), end=script.indexOf('\nfunction renderPreviewTable',start);
    let key='old',message='';
    const c={currentChanges:[], document:{getElementById:()=>({value:'fixture'})},getThumbnailsDirectory:()=>'/images',
        beginWorkbenchOperation:()=>true,invalidateWorkbenchPreview:()=>{},workbenchInputKey:()=>key,
        showStatus:text=>{message=text;},saveConfig:async()=>{key='new';return true;},getProcessingOptions:()=>({}),
        desktopRequest:async()=>({changes:[game]}),workbenchText:zh=>zh,uiText:x=>x,endWorkbenchOperation:()=>{}};
    vm.createContext(c);vm.runInContext(script.slice(start,end),c);await c.previewTask();
    assert.equal(c.currentChanges.length,0);assert.match(message,/配置已变化/);
});
