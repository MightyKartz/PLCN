const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {deriveWorkbenchState} = require('../src/templates/workflow.js');
const source = fs.readFileSync(require('node:path').join(__dirname, '../src/templates/library.js'), 'utf8');

function harness() {
    const elements = {};
    const element = id => elements[id] ||= {value: '', hidden: false};
    const pending = [];
    const context = {AbortController, URLSearchParams, workbench: {operation: null},
        document: {getElementById: element},
        workbenchText: (zh, en) => zh,
        getSystemAbbreviation: s => s, formatGameCount: n => `${n} games`,
        fetch: (url, options) => new Promise(resolve => pending.push({url, options, resolve})),
        renderWorkbench: () => context.syncGameLibrary({previewValid: false}, false)};
    vm.createContext(context);
    vm.runInContext(source + '\nthis.store = gameLibrary; this.markers = ARTWORK_KIND_MARKERS; renderGameLibrary = () => {};', context);
    context.select = path => {
        element('playlist_path').value = path;
        element('system_name').value = 'GBA';
        context.syncGameLibrary({previewValid: false}, false);
    };
    context.reply = async (index, data, ok = true) => {
        pending[index].resolve({ok, json: async () => data});
        await new Promise(resolve => setImmediate(resolve));
    };
    return {context, elements, pending};
}

test('selection starts a read and cannot enable apply without repair proposals', async () => {
    const {context, pending} = harness();
    context.select('one.lpl');
    assert.match(pending[0].url, /^\/api\/playlist\/items\?/);
    assert.equal(context.store.loading, true);
    await context.reply(0, {items: [{label: 'Current'}]});
    assert.equal(context.store.data.items.length, 1);
    const state = deriveWorkbenchState({playlist: 'one.lpl', system: 'GBA', previewKey: null, inputKey: 'one', selected: 1});
    assert.equal(state.canPreview, true);
    assert.equal(state.canApply, false);
});

test('A → B → A rejects both late responses even when the path matches again', async () => {
    const {context, pending} = harness();
    context.select('a.lpl'); context.select('b.lpl'); context.select('a.lpl');
    assert.equal(pending[0].options.signal.aborted, true);
    assert.equal(pending[1].options.signal.aborted, true);
    await context.reply(2, {items: [{label: 'Newest A'}]});
    await context.reply(1, {items: [{label: 'B'}]});
    await context.reply(0, {items: [{label: 'Old A'}]});
    assert.equal(context.store.data.items[0].label, 'Newest A');
});

test('clearing selection or starting preview discards an outstanding read', async () => {
    for (const action of ['clear', 'preview', 'batch']) {
        const {context, elements, pending} = harness();
        context.select('a.lpl');
        if (action === 'clear') context.select('');
        else {
            context.workbench.operation = action === 'preview' ? 'preview' : null;
            context.syncGameLibrary({previewValid: false}, action === 'batch');
        }
        await context.reply(0, {items: [{label: 'Old'}]});
        assert.equal(context.store.data, null);
        assert.equal(elements['game-library'].hidden, true);
        assert.equal(pending[0].options.signal.aborted, true);
    }
});

test('failed reads can retry and an empty list is a successful result', async () => {
    const {context} = harness();
    context.select('missing.lpl');
    await context.reply(0, {error: 'Disconnected'}, false);
    assert.equal(context.store.error, 'Disconnected');
    context.retryGameLibrary();
    await context.reply(1, {items: []});
    assert.equal(context.store.error, '');
    assert.equal(context.store.loading, false);
    assert.equal(context.store.data.items.length, 0);
});

test('changing the image directory rejects the previous artwork response', async () => {
    const {context, elements} = harness();
    context.select('a.lpl');
    elements.thumbnails_dir.value = 'new-images';
    context.syncGameLibrary({previewValid: false}, false);
    await context.reply(1, {items: [{label: 'New image'}]});
    await context.reply(0, {items: [{label: 'Old image'}]});
    assert.equal(context.store.data.items[0].label, 'New image');
});

test('image filters distinguish missing files from damage and read errors', () => {
    const {context}=harness();
    assert.equal(context.gameMatchesImageFilter({image_status:'missing'}, 'missing'), true);
    assert.equal(context.gameMatchesImageFilter({image_status:'exists'}, 'missing'), false);
    for (const status of ['invalid','unreadable','unconfigured']) {
        assert.equal(context.gameMatchesImageFilter({image_status:status}, 'problem'), true);
        assert.equal(context.gameMatchesImageFilter({image_status:status}, 'missing'), false);
    }
});

test('rows offer to fill every artwork type that is not already present', () => {
    const {context}=harness();
    assert.deepEqual([...context.missingArtworkKinds({})], []);
    assert.deepEqual([...context.missingArtworkKinds({artwork_status: {Named_Boxarts: 'exists', Named_Snaps: 'exists', Named_Titles: 'exists'}})], []);
    assert.deepEqual([...context.missingArtworkKinds({artwork_status: {Named_Boxarts: 'exists', Named_Snaps: 'missing', Named_Titles: 'invalid'}})], ['Named_Snaps', 'Named_Titles']);
    assert.deepEqual([...context.missingArtworkKinds({artwork_status: {Named_Boxarts: 'unreadable', Named_Snaps: 'exists', Named_Titles: 'exists'}})], ['Named_Boxarts']);
});

test('a row counts as missing until all three artwork types are present', () => {
    const {context}=harness();
    const status = (box, snap, title) => ({Named_Boxarts: box, Named_Snaps: snap, Named_Titles: title});
    assert.equal(context.gameMatchesImageFilter({image_status:'exists', artwork_status:status('exists','exists','exists')}, 'missing'), false);
    assert.equal(context.gameMatchesImageFilter({image_status:'exists', artwork_status:status('exists','missing','exists')}, 'missing'), true);
    assert.equal(context.gameMatchesImageFilter({image_status:'missing', artwork_status:status('missing','missing','missing')}, 'missing'), true);
    // Damaged artwork is still a gap to fill, not a reason to hide the row.
    assert.equal(context.gameMatchesImageFilter({image_status:'invalid', artwork_status:status('invalid','exists','exists')}, 'missing'), true);
    for (const state of ['unconfigured', 'unreadable']) {
        const item = {image_status:state, artwork_status:status('missing','missing','missing')};
        assert.equal(context.gameMatchesImageFilter(item, 'missing'), false);
        assert.equal(context.gameMatchesImageFilter(item, 'problem'), true);
    }
});

test('artwork chips and row buttons share one vocabulary per image type', () => {
    const {context}=harness();
    assert.equal(context.artworkKindLabel('Named_Boxarts'), '封面');
    assert.equal(context.artworkKindLabel('Named_Snaps'), '游戏截图');
    assert.equal(context.artworkKindLabel('Named_Titles'), '标题图');
    assert.equal(context.artworkKindState('exists'), '已有');
    assert.equal(context.artworkKindState('invalid'), '损坏');
    assert.equal(context.artworkKindState('missing'), '缺少');
    assert.equal(context.markers.exists, '✓');
    assert.equal(context.markers.invalid, '!');
    assert.equal(context.markers.missing, '○');
});
