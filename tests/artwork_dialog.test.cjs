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

test('unresolved DOS identity clears old executable text and does not search the gallery', async () => {
    const calls = [];
    const {context, elements, input, item} = harness(async url => {
        calls.push(url);
        return url.endsWith('/context') ? {shared: []} : {status: 'unresolved', names: [], query: ''};
    });
    context.closeArtworkDialog();
    input[1] = 'DOS';
    context.openArtworkDialog({...item, label: '金庸群侠传', rom_path: '/DOS/金庸群侠传.zip#Z.COM'}, false);
    elements['artwork-source'].value = 'Z';
    await context.discoverArtwork();
    assert.equal(elements['artwork-source'].value, '');
    assert.match(elements['artwork-identity'].textContent, /Title not identified/);
    assert.equal(calls.includes('/api/artwork/search'), false);
    assert.equal(elements['artwork-confirm'].disabled, true);
});

test('an empty gallery and a network failure have different messages', async () => {
    let failed = false;
    const {context, elements} = harness(async () => {
        if (failed) throw new Error('Connection timed out');
        return {names: [], total: 0, candidates: []};
    });
    elements['artwork-source'].value = 'Known DOS title';
    await context.searchArtwork();
    assert.match(elements['artwork-message'].textContent, /No gallery match/);
    failed = true;
    await context.searchArtwork();
    assert.match(elements['artwork-message'].textContent, /Library search failed.*Connection timed out/);
});

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
    elements['artwork-candidate-image-Named_Boxarts'].onload();
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
    assert.equal(elements['artwork-comparison'].hidden, true);
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

test('artwork opened from repair preview preserves edits on cancel and invalidates them after a write', async () => {
    const {context, item} = harness(async url => url.endsWith('/apply') ? {job_id:'one'}
        : {jobs:[{id:'one',status:'completed',result:{target:'new.png',image_url:'/new',new_label:'New name'}}]});
    context.closeArtworkDialog();
    context.workbench.previewKey = 'old-playlist';
    let invalidations = 0;
    context.invalidateWorkbenchPreview = () => {invalidations++; context.workbench.previewKey=null;};
    context.openArtworkDialog(item, false);
    context.closeArtworkDialog();
    assert.equal(invalidations, 0);
    context.openArtworkDialog(item, false);
    context.state().candidate = {token:'token'};
    await context.confirmArtwork();
    assert.equal(invalidations, 1);
    assert.equal(context.workbench.previewKey, null);
    assert.equal(context.state(), null);
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
    elements['artwork-candidate-image-Named_Boxarts'].onload();
    finishSearch({total:0,names:[]}); await pending;
    assert.equal(context.state().candidate.token,'local');
    assert.equal(elements['artwork-comparison'].hidden,false);
    assert.equal(elements['artwork-current-image-Named_Boxarts'].src,'/old');
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
    elements['artwork-candidate-image-Named_Boxarts'].onload();
    assert.match(elements['artwork-message'].textContent,/rename this entry/);
    context.artworkIndependentNameChanged();
    assert.equal(elements['artwork-confirm'].disabled,true);
});

test('official results take priority, fallback candidates require explicit preview and preserve provider id', async () => {
    let official = true;
    const calls = [];
    const {context,elements} = harness(async (url,body) => {
        calls.push([url,body]);
        if (url.endsWith('/preview')) return {token:'review',image_url:'/staged',width:10,height:20,
            source:'Cover',provenance:{provider_label:'Wikipedia',platform:'DOS',version:'1995 cover'}};
        if (body.provider === 'wikipedia') return {provider:'wikipedia',total:1,names:['Cover'],candidates:[{id:'external',name:'Cover',platform:'DOS',version:'1995 cover'}]};
        return official ? {total:1,names:['Official'],candidates:[{name:'Official'}]} : {total:0,names:[],candidates:[]};
    });
    elements['artwork-source'].value='DOS Game';
    await context.searchArtwork(true);
    assert.equal(calls.length,1);
    assert.equal(calls[0][1].provider,'libretro');
    official=false; calls.length=0;
    await context.searchArtwork(true);
    assert.equal(calls.length,2);
    assert.equal(calls[1][1].provider,'wikipedia');
    assert.equal(context.state().candidate,null);
    assert.equal(elements['artwork-confirm'].disabled,true);
    elements.created.onclick();
    await new Promise(resolve=>setImmediate(resolve));
    assert.equal(calls[2][1].candidate_id,'external');
    assert.equal(calls[2][1].source,undefined);
    assert.match(elements['artwork-candidate-caption-Named_Boxarts'].textContent,/Wikipedia.*DOS.*1995 cover/);
    assert.equal(elements['artwork-confirm'].disabled,true);
    elements['artwork-candidate-image-Named_Boxarts'].onload();
    assert.equal(elements['artwork-confirm'].disabled,false);
    context.artworkSearchChanged();
    assert.equal(context.state().selectedExternal,null);
    assert.equal(elements['artwork-confirm'].disabled,true);
});

test('direct import entry prepares game context without querying either gallery', async () => {
    const calls=[];
    const {context,item,elements}=harness(async (url)=>{
        calls.push(url);
        return url.endsWith('/context') ? {shared:[]} : {status:'resolved',reason:'curated',query:'Known',names:['Known']};
    });
    context.closeArtworkDialog();
    await context.openArtworkImport(item);
    assert.deepEqual(calls,['/api/artwork/context','/api/artwork/resolve']);
    assert.equal(elements['artwork-upload'].focused,true);
    assert.equal(elements['artwork-confirm'].disabled,true);
});

test('missing types are checked by default and one preview fills them together', async () => {
    let preview;
    const {context,elements}=harness(async (url,body)=>{
        if (url.endsWith('/context')) return {shared:[], artwork:{Named_Boxarts:{status:'exists'}, Named_Snaps:{status:'missing'}, Named_Titles:{status:'missing'}}};
        if (url.endsWith('/resolve')) return {status:'resolved',reason:'database',query:'Game (USA)',names:['Game (USA)']};
        if (url.endsWith('/preview')) {preview=body; return {token:'three',images:[
            {kind:'Named_Snaps',label:'游戏截图',target:'/img/Named_Snaps/Game.png',image_url:'/snap',source:'Game (USA)',width:8,height:8,current_status:'missing'},
            {kind:'Named_Titles',label:'标题图',target:'/img/Named_Titles/Game.png',image_url:'/title',source:'Game (USA)',width:8,height:8,current_status:'missing'}],
            skipped:[{kind:'Named_Boxarts',label:'封面',reason:'在线图库未收录此类型图片'}]};}
        return {total:1,names:['Game (USA)'],candidates:[{name:'Game (USA)'}]};
    });
    await context.discoverArtwork();
    assert.equal(elements['artwork-kind-Named_Boxarts'].checked, false);
    assert.equal(elements['artwork-kind-Named_Snaps'].checked, true);
    assert.equal(elements['artwork-kind-Named_Titles'].checked, true);
    assert.equal(elements['artwork-kind-status-Named_Boxarts'].textContent, 'Has image');
    await context.previewArtwork();
    assert.deepEqual([...preview.kinds], ['Named_Snaps','Named_Titles']);
    assert.equal(elements['artwork-row-Named_Boxarts'].hidden, true);
    assert.equal(elements['artwork-row-Named_Snaps'].hidden, false);
    assert.equal(elements['artwork-row-Named_Titles'].hidden, false);
    assert.match(elements['artwork-skipped'].textContent, /Not in the official library/);
    assert.equal(elements['artwork-confirm'].disabled, true);
    elements['artwork-candidate-image-Named_Snaps'].onload();
    assert.equal(elements['artwork-confirm'].disabled, true);
    elements['artwork-candidate-image-Named_Titles'].onload();
    assert.equal(elements['artwork-confirm'].disabled, false);
    assert.match(elements['artwork-message'].textContent, /Will write: Screenshot, Title screen/);
});

test('an already complete game keeps the box art selected and can add one type', async () => {
    let preview;
    const {context,elements}=harness(async (url,body)=>{
        if (url.endsWith('/context')) return {shared:[], artwork:{Named_Boxarts:{status:'exists'}, Named_Snaps:{status:'exists'}, Named_Titles:{status:'exists'}}};
        if (url.endsWith('/resolve')) return {status:'resolved',reason:'database',query:'Game',names:['Game']};
        if (url.endsWith('/preview')) {preview=body; return {token:'one',image_url:'/one',source:'Game',width:8,height:8,current_status:'missing'};}
        return {total:1,names:['Game'],candidates:[{name:'Game'}]};
    });
    await context.discoverArtwork();
    assert.equal(elements['artwork-kind-Named_Boxarts'].checked, true);
    assert.equal(elements['artwork-kind-Named_Snaps'].checked, false);
    elements['artwork-kind-Named_Snaps'].checked = true;
    elements['artwork-kind-Named_Boxarts'].checked = false;
    context.artworkKindChanged();
    await context.previewArtwork();
    assert.deepEqual([...preview.kinds], ['Named_Snaps']);
});

test('changing the image types discards a candidate staged for the old set', async () => {
    const {context,elements}=harness(async url=>url.endsWith('/preview')
        ? {token:'staged',image_url:'/staged',source:'Game',width:8,height:8,current_status:'missing'}
        : {total:1,names:['Game'],candidates:[{name:'Game'}]});
    elements['artwork-source'].value='Game';
    await context.previewArtwork();
    elements['artwork-candidate-image-Named_Boxarts'].onload();
    assert.equal(elements['artwork-confirm'].disabled, false);
    context.artworkKindChanged();
    assert.equal(context.state().candidate, null);
    assert.equal(elements['artwork-confirm'].disabled, true);
    assert.match(elements['artwork-message'].textContent, /Image types changed/);
});

test('clearing every image type blocks the preview instead of a partial write', async () => {
    const {context,elements}=harness(async()=>({total:0,names:[]}));
    elements['artwork-source'].value='Game';
    for (const kind of ['Named_Boxarts','Named_Snaps','Named_Titles']) elements['artwork-kind-' + kind].checked = false;
    context.artworkKindChanged();
    assert.match(elements['artwork-message'].textContent, /at least one image type/);
    await context.previewArtwork();
    assert.equal(context.state().candidate, null);
    assert.equal(elements['artwork-confirm'].disabled, true);
});

test('a confirmed update reports every written type on the game row', async () => {
    const {context,item,elements}=harness(async url=>url.endsWith('/apply') ? {job_id:'one'}
        : {jobs:[{id:'one',status:'completed',result:{backup:'Game.png.bak',images:[
            {kind:'Named_Boxarts',target:'/img/Named_Boxarts/Game.png',image_url:'/box'},
            {kind:'Named_Snaps',target:'/img/Named_Snaps/Game.png',image_url:'/snap'}]}}]});
    context.state().candidate={token:'token'};
    await context.confirmArtwork();
    assert.equal(item.image_url,'/box');
    assert.equal(item.image_path,'/img/Named_Boxarts/Game.png');
    assert.match(item.artwork_result,/Updated Box art, Screenshot artwork/);
    assert.equal(elements['artwork-dialog'].open,false);
});

test('an unidentified Chinese title offers graded catalog names instead of a dead end', async () => {
    const calls = [];
    const {context, elements, item} = harness(async (url, body) => {
        calls.push([url, body]);
        if (url.endsWith('/context')) return {shared: []};
        if (url.endsWith('/resolve')) return {status: 'unresolved', reason: 'filename', query: '', names: ['Ys III (USA)'],
            suggestions: [{english_name: 'Ys - Wanderers from Ys (Japan)', chinese_name: '伊苏国3', tier: 'fuzzy', score: 86},
                {english_name: 'Ys III (USA)', chinese_name: '伊苏国3', tier: 'fuzzy', score: 86}]};
        return {total: 1, names: ['Ys III (USA)'], candidates: [{name: 'Ys III (USA)', image_url: '/ys', tier: 'exact', score: 100}]};
    });
    context.closeArtworkDialog();
    context.openArtworkDialog({...item, label: '伊苏3', rom_path: '/roms/伊苏3.md'}, false);
    await context.discoverArtwork();
    // A suggestion is never a search: the gallery is only queried after the user chooses.
    assert.deepEqual(calls.map(call => call[0]), ['/api/artwork/context', '/api/artwork/resolve']);
    assert.equal(elements['artwork-source'].value, '');
    assert.equal(elements['artwork-names-wrap'].hidden, false);
    assert.match(elements['artwork-names-label'].textContent, /candidates/i);
    assert.match(elements['artwork-identity'].textContent, /name catalog/i);
    elements.created.onclick();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(calls[2][0], '/api/artwork/search');
    assert.equal(calls[2][1].query, 'Ys III (USA)');
    assert.equal(calls[2][1].automatic, false);
    assert.equal(calls[2][1].label, '伊苏3');
    assert.equal(elements['artwork-source'].value, 'Ys III (USA)');
    assert.equal(elements['artwork-names-wrap'].hidden, true);
});

test('catalog candidates show the Chinese name, grade and match score', () => {
    const {context} = harness(async () => ({names: [], total: 0, candidates: []}));
    assert.equal(context.artworkSuggestionDetail({chinese_name: '伊苏国3', tier: 'fuzzy', score: 86}),
        'Chinese name: 伊苏国3 · Close name, check the edition · Match 86%');
    assert.equal(context.artworkSuggestionDetail({tier: 'exact'}), 'Exact title match');
    assert.equal(context.artworkTierLabel('words'), 'Contains every keyword');
    assert.equal(context.artworkKindName('Named_Snaps'), 'Screenshot');
});

test('an empty gallery offers catalog names before giving up on a Chinese search term', async () => {
    const {context, elements} = harness(async () => ({total: 0, names: [], candidates: [],
        suggestions: [{english_name: 'Ys III (USA)', chinese_name: '伊苏国3', tier: 'fuzzy', score: 86}]}));
    elements['artwork-source'].value = '伊苏3';
    await context.searchArtwork(false);
    assert.match(elements['artwork-message'].textContent, /name catalog/i);
    assert.equal(elements['artwork-names-wrap'].hidden, false);
    assert.match(elements['artwork-names-label'].textContent, /candidates/i);
});
