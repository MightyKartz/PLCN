const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const script = fs.readFileSync('src/templates/content-scan.js', 'utf8');
function source(name) {
    const start = script.search(new RegExp('^(?:async )?function ' + name + '\\(', 'm'));
    assert.notEqual(start, -1);
    const rest = script.slice(start), next = rest.slice(1).search(/^(?:async )?function /m);
    return next < 0 ? rest : rest.slice(0, next + 1);
}
function deferred() { let resolve; const promise = new Promise(r => { resolve = r; }); return {promise, resolve}; }
function harness() {
    const fields = new Map();
    const field = name => {
        if (!fields.has(name)) fields.set(name, {value:'', textContent:'', hidden:false, disabled:false, open:false, dataset:{},
            addEventListener(){}, removeAttribute(){}, setAttribute(){}, scrollIntoView(){}, focus(){},
            replaceChildren(...options){ this.value = options[0]?.value || ''; },
            showModal(){ this.open = true; }, close(){ this.open = false; }});
        return fields.get(name);
    };
    const context = {uiText:text=>text,wbIconButton(button,icon,label){button.title=label;},contentScan:{setup:{root:'mtp://device/00010001/RetroArch',android:true},revision:0,openGeneration:0},
        contentHintGeneration:0,contentCoreStatusGeneration:0,contentInfoGeneration:0,contentDirectoryGeneration:0,
        contentField:field,document:{getElementById:field},currentDeviceScan:null,
        renderContentConfiguration(){},loadContentCoreStatus(){},invalidateContentScan(){},
        URLSearchParams,Option:function(text,value){this.textContent=text;this.value=value;}};
    field('directory').value = 'mtp://device/00020001/Roms/SS';field('system').value = 'Sega - Saturn';
    field('core').value = 'mednafen_saturn';field('core-path').value = '/cores/mednafen_saturn.so';
    context.contentPayload = () => ({root:context.contentScan.setup.root,directory:field('directory').value,
        system:field('system').value,core_id:field('core').value,core_path:field('core-path').value});
    vm.createContext(context);
    return {context,field,load: name => vm.runInContext(source(name), context)};
}

test('late hints cannot replace manual configuration edited during the request', async () => {
    const {context:c,field,load} = harness(), pending = deferred();
    c.desktopRequest = () => pending.promise;
    load('loadContentHints');
    const request = c.loadContentHints();
    field('core-path').value = '/custom/core.so';c.contentScan.revision++;
    pending.resolve({android_directory:'/storage/old/Roms/SS',core_path:'/old/core.so'});
    await request;
    assert.equal(field('android').value,'');assert.equal(field('core-path').value,'/custom/core.so');
});

test('reopening the same device rejects responses from the old setup object', async () => {
    const {context:c,field,load} = harness(), pending = deferred();
    c.desktopRequest = () => pending.promise;load('loadContentHints');
    const request = c.loadContentHints();c.contentScan.setup = {...c.contentScan.setup};
    pending.resolve({android_directory:'/storage/old/Roms/SS'});await request;
    assert.equal(field('android').value,'');
});

test('core status follows the current path and never accepts an old installed result', async () => {
    const {context:c,field,load} = harness(), first = deferred(), second = deferred();
    let count = 0;c.desktopRequest = () => ++count === 1 ? first.promise : second.promise;
    load('contentCoreStatusKey');load('loadContentCoreStatus');
    const old = c.loadContentCoreStatus();field('core-path').value = '/new/core.so';
    const latest = c.loadContentCoreStatus();
    second.resolve({state:'unknown',message:'安装状态未知',detail:'MTP 无法验证'});await latest;
    first.resolve({state:'available',message:'已找到',detail:'old path'});await old;
    assert.equal(c.contentScan.coreStatus.state,'unknown');assert.match(c.contentScan.coreStatus.key,/new/);
});

test('core format information from the previous device cannot fill the new setup', async () => {
    const {context:c,field,load} = harness(), pending = deferred();
    field('extensions').value = 'cue chd m3u';c.desktopRequest = () => pending.promise;
    load('loadContentCoreInfo');const request = c.loadContentCoreInfo();
    c.contentScan.setup = {root:'/another/device'};
    pending.resolve({extensions:['chd']});await request;
    assert.equal(field('extensions').value,'cue chd m3u');assert.equal(field('content-core-formats').textContent,'');
});

test('scan waits for directory recognition already started by Use this directory', async () => {
    const {context:c,field,load} = harness(), pending = deferred();
    let submitted;
    c.contentScan.configurationTask = pending.promise;c.contentScan.setup.android = false;
    c.contentJob = async (path,payload) => { submitted = payload;throw Error('read-only submission boundary'); };
    load('previewContentScan');const request = c.previewContentScan();
    assert.equal(submitted,undefined);
    field('system').value = 'Sony - PlayStation';pending.resolve();await request;
    assert.equal(submitted.system,'Sony - PlayStation');
});

test('a missing advanced field opens its settings before receiving focus', () => {
    const {context:c,field,load} = harness();const settings = {open:false};let focused=false;
    field('core-path').closest = () => settings;field('core-path').focus = () => { focused = settings.open; };
    load('focusContentScanField');c.focusContentScanField('core-path','需要填写路径');assert.equal(focused,true);
});

test('two overlapping setup requests only populate the most recently opened device', async () => {
    const {context:c,field,load} = harness(), first=deferred(),second=deferred();
    c.workbench = {};c.libraryHome = {};c.selectedLibrarySystem = '';c.showStatus = () => {};
    c.changeContentSystem = () => {};c.desktopRequest = url => url.includes('first')?first.promise:second.promise;
    load('openContentScan');
    const old=c.openContentScan('/first'), latest=c.openContentScan('/second');
    const setup = root => ({root,android:false,profiles:[],systems:[{name:'Sega - Saturn'}]});
    second.resolve(setup('/second'));await latest;
    first.resolve(setup('/first'));await old;
    assert.equal(c.contentScan.setup.root,'/second');assert.equal(field('fields').disabled,false);
});


test('initial format filtering does not invalidate directory recognition in flight', async () => {
    const {context:c,field,load} = harness();let invalidations=0;
    field('extensions').value='cue chd unsupported';
    c.invalidateContentScan=()=>{invalidations++;};
    c.desktopRequest=async()=>({extensions:['cue','chd']});
    load('loadContentCoreInfo');await c.loadContentCoreInfo();
    assert.equal(field('extensions').value,'cue chd');assert.equal(invalidations,0);
});
