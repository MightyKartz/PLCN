const {test} = require('node:test');
const assert = require('node:assert/strict');
const {deriveWorkbenchState} = require('../src/templates/workflow.js');
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
for (const operation of ['scan','preview','apply']) {
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
