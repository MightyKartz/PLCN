const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../src/templates/artwork.js'), 'utf8');

function harness(request) {
    const elements = {};
    const get = id => elements[id] ||= {value: '', disabled: false, options: [{}, {}, {}], listeners: {},
        replaceChildren() {}, appendChild() {}, setAttribute() {}, focus() {this.focused=true;},
        scrollIntoView() {this.scrolled=true;}, showModal() {this.open=true;}, close() {this.open=false;},
        addEventListener(name, callback) {this.listeners[name]=callback;}};
    const item = {index: 4, label: 'Chosen', rom_path: '/roms/four.gba'};
    const input = ['test.lpl', 'GBA', 'images'];
    const selectedRepairs = [{enabled:true}, {enabled:true}];
    const context = {document: {getElementById: get, createElement: () => get('created')}, setTimeout,
        workbenchText: (zh, en) => en, gameLibraryInput: () => input,
        gameLibrary: {key: JSON.stringify(input), data: {items: [item]}},
        loadGameLibrary: async () => {context.reloadedLibrary = true;},
        currentChanges: selectedRepairs, workbench: {operation: null},
        beginWorkbenchOperation: op => {context.workbench.operation = op; return true;},
        endWorkbenchOperation: () => {context.workbench.operation = null;},
        openPathSettings: () => {}, renderGameLibrary: () => {}, desktopRequest: request};
    vm.createContext(context);
    vm.runInContext(source + '\nthis.state = () => artworkDialogState;', context);
    context.openArtworkDialog(item, false);
    return {context, item, elements, input, selectedRepairs};
}

test('single-game preview never inherits or changes the bulk repair selection', async () => {
    let payload;
    const {context, elements, selectedRepairs} = harness(async (_url, body) => {
        payload = body; return {token:'candidate', image_url:'/image', width:12, height:16};
    });
    elements['artwork-source'].value = 'Goodboy';
    await context.previewArtwork();
    assert.equal(payload.index, 4);
    assert.equal(payload.label, 'Chosen');
    assert.equal(payload.changes, undefined);
    assert.equal(elements['artwork-confirm'].disabled, true);
    elements['artwork-candidate-image'].onload();
    assert.equal(elements['artwork-confirm'].disabled, false);
    assert.deepEqual(selectedRepairs, [{enabled:true}, {enabled:true}]);
    context.invalidateArtworkCandidate();
    assert.equal(context.state().candidate, null);
    assert.equal(elements['artwork-confirm'].disabled, true);
});

test('late candidates cannot populate a different game dialog', async () => {
    let reply;
    const {context, elements} = harness(() => new Promise(resolve => {reply = resolve;}));
    elements['artwork-source'].value = 'Game';
    const pending = context.previewArtwork();
    vm.runInContext('artworkDialogState = null; workbench.operation = null;', context);
    context.openArtworkDialog({index:5,label:'Another',rom_path:'/roms/five.gba'}, false);
    reply({token:'old',image_url:'/old'}); await pending;
    assert.equal(context.state().context.index, 5);
    assert.equal(context.state().candidate, null);
    assert.equal(elements['artwork-candidate'].hidden, true);
});

test('empty search and preview explain the missing input without a failed network request', async () => {
    let calls = 0;
    const {context, elements} = harness(async () => {calls++;});
    elements['artwork-source'].value = '  ';
    await context.searchArtwork();
    assert.equal(calls, 0);
    assert.match(elements['artwork-message'].textContent, /Enter a game title/);
    assert.equal(elements['artwork-source'].focused, true);
    await context.previewArtwork();
    assert.equal(calls, 0);
    assert.match(elements['artwork-message'].textContent, /select a candidate/);
    assert.equal(elements['artwork-confirm'].disabled, true);
});

test('duplicate confirmation is locked and successful update changes only the current row', async () => {
    let submit, calls=0;
    const {context, item, elements} = harness(async url => {
        if (url.endsWith('/apply')) {calls++;return new Promise(resolve=>{submit=resolve;});}
        return {jobs:[{id:'one',status:'completed',result:{target:'image.png',image_url:'/updated',backup:'image.png.bak'}}]};
    });
    context.state().candidate = {token:'token'};
    const first=context.confirmArtwork();
    await context.confirmArtwork();
    assert.equal(calls,1);
    submit({job_id:'one'});await first;
    assert.equal(item.image_url,'/updated');
    assert.equal(context.reloadedLibrary,true);
    assert.equal(context.state(),null);
    assert.equal(context.workbench.operation,null);
    assert.equal(elements['artwork-dialog'].open,false);
    assert.equal(elements['game-artwork-action-4'].focused,true);
    assert.equal(elements['game-artwork-action-4'].scrolled,true);
    assert.equal(item.artwork_backup,'image.png.bak');
    assert.match(item.artwork_result,/backed up/);
});

test('polling failure preserves the original job and locks source edits until retry', async () => {
    let pollFails=true, submits=0;
    const {context,elements}=harness(async url=>{
        if(url.endsWith('/apply')) {submits++;return {job_id:'one'};}
        if(pollFails)throw new Error('disconnected');
        return {jobs:[{id:'one',status:'completed',result:{target:'image.png',image_url:'/updated'}}]};
    });
    context.state().candidate={token:'token'};
    await context.confirmArtwork();
    assert.equal(context.state().jobId,'one');
    assert.equal(elements['artwork-source'].disabled,true);
    assert.equal(elements['artwork-close'].disabled,true);
    assert.equal(elements['artwork-confirm'].disabled,false);
    assert.equal(elements['artwork-dialog'].open,true);
    pollFails=false;await context.confirmArtwork();
    assert.equal(submits,1);
    assert.equal(elements['artwork-close'].disabled,false);
    assert.equal(elements['artwork-dialog'].open,false);
});

test('failed writes stay open for retry; successful close events cannot dismiss a new dialog', async () => {
    const {context,elements,item}=harness(async url=>url.endsWith('/apply') ? {job_id:'one'} : {jobs:[{id:'one',status:'failed',error:'device disconnected'}]});
    assert.equal(elements['artwork-confirm'].textContent,'Confirm');
    context.state().candidate={token:'candidate'};
    await context.confirmArtwork();
    assert.equal(elements['artwork-dialog'].open,true);
    assert.equal(elements['artwork-confirm'].textContent,'Confirm');
    assert.equal(elements['artwork-message'].textContent,'device disconnected');
    context.closeArtworkDialog();
    context.openArtworkDialog(item,false);
    elements['artwork-dialog'].listeners.close();
    assert.equal(elements['artwork-dialog'].open,true);
    assert.equal(context.state().context.label,item.label);
});

test('opening artwork resolves the English title then automatically searches official candidates', async () => {
    const calls=[];
    const {context,elements,item}=harness(async (url,body)=>{
        calls.push([url,body]);
        if(url.endsWith('/resolve'))return {status:'resolved',reason:'database',query:'Game (USA)',names:['Game (USA)']};
        return {total:1,names:['Game (USA)'],candidates:[{name:'Game (USA)',image_url:'/official-image',exact:true}]};
    });
    context.workbench.operation=null;
    await context.openArtworkDialog(item);
    assert.deepEqual(calls.map(c=>c[0]),['/api/artwork/context','/api/artwork/resolve','/api/artwork/search']);
    assert.equal(calls[2][1].automatic,true);
    assert.equal(elements['artwork-source'].value,'Game (USA)');
    assert.equal(elements['artwork-upload'].disabled,false);
    assert.equal(elements['artwork-confirm'].disabled,true);
});

test('changing the query prevents late automatic resolution from replacing user input', async () => {
    let resolved; const calls=[];
    const {context,elements}=harness((url)=>{calls.push(url);return new Promise(r=>{resolved=r;});});
    const pending=context.discoverArtwork();
    elements['artwork-source'].value='My title'; context.artworkSearchChanged();
    resolved({status:'resolved',reason:'database',query:'Old title'}); await pending;
    assert.equal(elements['artwork-source'].value,'My title');
    assert.deepEqual(calls,['/api/artwork/context']);
});

test('local import remains available during search and its candidate survives a late search result', async () => {
    let finishSearch;
    const {context,elements}=harness(async url=>{
        if(url.endsWith('/search'))return new Promise(resolve=>{finishSearch=resolve;});
        return {token:'local',image_url:'/local',source:'local.png',width:12,height:16,current_image_url:'/old',current_status:'exists'};
    });
    context.FileReader=class {readAsDataURL(){this.result='data:image/png;base64,eA==';this.onload();}};
    elements['artwork-source'].value='Game';
    const pending=context.searchArtwork();
    assert.equal(elements['artwork-upload'].disabled,false);
    await context.importArtwork({name:'local.png',size:10});
    elements['artwork-candidate-image'].onload();
    finishSearch({total:0,names:[]}); await pending;
    assert.equal(context.state().candidate.token,'local');
    assert.equal(elements['artwork-comparison'].hidden,false);
    assert.equal(elements['artwork-current-image'].src,'/old');
    assert.equal(elements['artwork-confirm'].disabled,false);
});

test('shared artwork shows the affected ROMs and does not reuse the ambiguous label for search',async()=>{
    let lookup, preview;
    const {context,elements,item}=harness(async(url,body)=>{
        if(url.endsWith('/context'))return {shared:[{index:4,rom_name:'Four.gba'},{index:5,rom_name:'Five.gba'}],suggested_label:'Four'};
        if(url.endsWith('/resolve')) {lookup=body; return {status:'unresolved',names:[]};}
        preview=body; return {token:'separate',new_label:'Four',image_url:'/new',source:'Game Four',width:12,height:16};
    });
    context.workbench.operation=null;
    await context.openArtworkDialog(item);
    assert.equal(elements['artwork-shared'].hidden,false);
    assert.equal(lookup.label,'Four');
    elements['artwork-source'].value='Game Four';
    await context.previewArtwork();
    assert.equal(preview.new_label,'Four');
    assert.equal(preview.label,'Chosen');
    elements['artwork-candidate-image'].onload();
    assert.match(elements['artwork-message'].textContent,/rename this entry/);
    context.artworkIndependentNameChanged();
    assert.equal(elements['artwork-confirm'].disabled,true);
});
