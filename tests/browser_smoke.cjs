/* Real Chromium UI smoke test; Node 22's WebSocket is the only CDP client. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {setTimeout: delay} = require('node:timers/promises');

const [websocketUrl, baseUrl, libraryPath, width, height, output] = process.argv.slice(2);
const errors = [];
const pending = new Map();
const socket = new WebSocket(websocketUrl);
let sequence = 0;

function send(method, params = {}) {
    return new Promise((resolve, reject) => {
        const id = ++sequence;
        const timer = setTimeout(() => {
            pending.delete(id);
            reject(new Error(`CDP timed out: ${method}`));
        }, 5000);
        pending.set(id, {resolve, reject, timer});
        socket.send(JSON.stringify({id, method, params}));
    });
}

socket.addEventListener('message', event => {
    const message = JSON.parse(event.data);
    if (message.id) {
        const call = pending.get(message.id);
        if (!call) return; // A response can arrive after a command has timed out.
        pending.delete(message.id);
        clearTimeout(call.timer);
        if (message.error) call.reject(new Error(JSON.stringify(message.error)));
        else call.resolve(message.result);
    } else if (message.method === 'Runtime.exceptionThrown') {
        const detail = message.params.exceptionDetails;
        errors.push(detail.exception?.description || detail.text);
    } else if (message.method === 'Runtime.consoleAPICalled' && message.params.type === 'error') {
        errors.push(message.params.args.map(arg => arg.value || arg.description).join(' '));
    } else if (message.method === 'Network.responseReceived') {
        const {url, status} = message.params.response;
        if (url.startsWith(baseUrl + '/') && status >= 400) errors.push(`HTTP ${status}: ${url}`);
    } else if (message.method === 'Fetch.requestPaused') {
        // Thumbnail availability is outside this smoke test; local APIs remain real.
        send('Fetch.fulfillRequest', {
            requestId: message.params.requestId,
            responseCode: 200,
            responseHeaders: [{name: 'Content-Type', value: 'image/png'}],
            body: 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aO6kAAAAASUVORK5CYII=',
        }).catch(error => errors.push(error.message));
    }
});
socket.addEventListener('close', () => {
    for (const call of pending.values()) {
        clearTimeout(call.timer);
        call.reject(new Error('Chrome closed the DevTools connection'));
    }
    pending.clear();
});

async function evaluate(fn, ...args) {
    const result = await send('Runtime.evaluate', {
        expression: `(${fn})(...${JSON.stringify(args)})`,
        awaitPromise: true, returnByValue: true,
    });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    return result.result.value;
}

async function waitFor(fn, label, ...args) {
    const deadline = Date.now() + 10000;
    while (Date.now() < deadline) {
        assert.deepEqual(errors, [], 'Page errors');
        if (await evaluate(fn, ...args)) return;
        await delay(100);
    }
    throw new Error(`Timed out waiting for ${label}`);
}

function visible(selector) {
    const element = document.querySelector(selector);
    if (!element) return false;
    const rect = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    return rect.width > 0 && rect.height > 0 && style.visibility === 'visible' && style.display !== 'none';
}

async function click(selector) {
    await waitFor(visible, `visible ${selector}`, selector);
    await waitFor(selector => !document.querySelector(selector).disabled, `enabled ${selector}`, selector);
    const point = await evaluate(selector => {
        const element = document.querySelector(selector);
        element.scrollIntoView({block: 'center'});
        const rect = element.getBoundingClientRect();
        const x = rect.left + rect.width / 2, y = rect.top + rect.height / 2;
        if (!element.contains(document.elementFromPoint(x, y))) throw new Error(`Obscured control: ${selector}`);
        return {x, y};
    }, selector);
    await send('Input.dispatchMouseEvent', {type: 'mousePressed', button: 'left', clickCount: 1, ...point});
    await send('Input.dispatchMouseEvent', {type: 'mouseReleased', button: 'left', clickCount: 1, ...point});
}

async function screenshot(name) {
    await send('Input.dispatchMouseEvent', {type: 'mouseMoved', x: 0, y: 0});
    await delay(200); // Let theme transitions settle before capturing visual evidence.
    const {data} = await send('Page.captureScreenshot', {format: 'png'});
    fs.writeFileSync(path.join(output, name + '.png'), Buffer.from(data, 'base64'));
}

async function main() {
    await new Promise((resolve, reject) => {
        socket.addEventListener('open', resolve, {once: true});
        socket.addEventListener('error', () => reject(new Error('Cannot connect to Chrome')), {once: true});
    });
    await send('Runtime.enable');
    await send('Page.enable');
    await send('Network.enable');
    await send('Fetch.enable', {patterns: [{urlPattern: 'https://thumbnails.libretro.com/*'}]});
    await send('Emulation.setDeviceMetricsOverride', {width: Number(width), height: Number(height), deviceScaleFactor: 1, mobile: false});
    await send('Page.navigate', {url: baseUrl});
    await waitFor(() => document.readyState === 'complete'
        && document.querySelector('#library-onboarding')?.getAttribute('aria-busy') === 'false', 'home discovery');
    assert.equal(await evaluate(visible, '#home-manual-open'), true);
    assert.equal(await evaluate(visible, '.sidebar'), false);
    assert.equal(await evaluate(visible, '#preview-area'), false);
    await screenshot('01-home');
    assert.equal(await evaluate(visible, '#usb-debug-help'), true);
    await click('#usb-debug-help > summary');
    assert.equal(await evaluate(() => document.querySelectorAll('#usb-debug-help li').length), 4);
    assert.equal(await evaluate(() => document.querySelector('#usb-debug-help').textContent.includes('USB 调试')), true);
    await screenshot('01-usb-help');
    await click('#usb-debug-help > summary');
    await click('#settings-button');
    assert.equal(await evaluate(() => document.querySelectorAll('dialog[open]').length), 1);
    assert.equal(await evaluate(() => document.querySelectorAll('[data-desktop-view]').length), 3);
    await click('[data-desktop-view="data"]');
    await waitFor(() => document.querySelector('#desktop-content h3')?.textContent === '名称数据库', 'name database settings');
    await screenshot('01-name-settings');
    await click('[data-desktop-view="tasks"]');
    await waitFor(() => document.querySelector('#desktop-content')?.textContent.includes('本地列表恢复'), 'tasks and restore settings');
    assert.equal(await evaluate(() => document.querySelector('#desktop-content').textContent.includes('本次运行的任务')), true);
    assert.equal(await evaluate(() => document.querySelector('.bottom-dock, #details-drawer')), null);
    await click('#desktop-content .desktop-entry:nth-of-type(2) details > summary');
    await waitFor(() => document.querySelector('#desktop-content details[open]')?.textContent.includes('测试图片网络失败'), 'task logs and failed image receipts');
    assert.equal(await evaluate(() => document.querySelector('#desktop-content details[open]').textContent.includes('开始补图')), true);
    assert.equal(await evaluate(visible, '#desktop-close'), true);
    await screenshot('01-task-settings');
    await click('#desktop-content button');
    await waitFor(() => document.querySelector('#desktop-content').textContent.includes('测试任务已取消'), 'task cancellation');
    assert.equal(await evaluate(() => document.querySelector('#desktop-content details[open]')?.textContent.includes('测试图片网络失败')), true);
    await click('#desktop-content button');
    await waitFor(() => document.querySelectorAll('#desktop-content [data-job-id]').length === 3
        && !Array.from(document.querySelectorAll('#desktop-content [data-job-id] strong')).some(node => /处理中|等待中/.test(node.textContent)), 'image retry without changing playlists');
    await screenshot('01-tasks-after-retry');
    await click('#desktop-close');

    await click('#home-manual-open');
    await waitFor(visible, 'library path dialog', '#path-settings');
    assert.equal(await evaluate(() => document.querySelectorAll('#path-settings input[type="text"]').length), 2);
    assert.equal(await evaluate(() => document.querySelector('.topbar .mode-switch')), null);
    await screenshot('01-path-settings');
    await evaluate(() => { const input = document.querySelector('#retroarch_root'); input.focus(); input.select(); });
    await send('Input.insertText', {text: libraryPath});
    await click('#scan-device-btn');
    await waitFor(() => document.querySelectorAll('.playlist-system-tab').length === 2
        && !document.querySelector('.playlist-system-tab').disabled, 'two systems');

    const system = '.playlist-system-tab[aria-label="Nintendo - Super Nintendo Entertainment System"]';
    await click(system);
    await waitFor(() => document.querySelector('#workspace-title')?.textContent.includes('SNES')
        && document.querySelector('.game-library-table tbody')?.textContent.includes('Shadowrun (USA)'), 'selected SNES games');
    assert.equal(await evaluate(selector => document.querySelector(selector).getAttribute('aria-pressed'), system), 'true');
    assert.equal(await evaluate(visible, '#game-library'), true);
    assert.equal(await evaluate(visible, '#library-onboarding'), false);
    assert.equal(await evaluate(visible, '#preview-area'), false);
    assert.equal(await evaluate(visible, '#image-directory-notice'), true);
    assert.equal(await evaluate(() => document.querySelector('#game-library-filter-problem').textContent), '需检查 0');
    assert.equal(await evaluate(() => document.querySelector('#game-library-rows td:first-child').textContent), '');
    assert.equal(await evaluate(() => document.querySelectorAll('#game-library-rows button').length), 0);
    await screenshot('02-games');

    await click('#theme-toggle-btn');
    await click('#language-display-btn');
    assert.equal(await evaluate(() => document.querySelector('#image-directory-message').textContent.startsWith('Choose an artwork folder')), true);
    await click('#choose-image-directory');
    assert.equal(await evaluate(() => document.querySelector('label[for="thumbnails_override"]').textContent), 'Artwork folder (optional override)');
    await screenshot('02-dark-en-path-settings');
    await click('#desktop-close');
    await waitFor(() => !document.querySelector('#desktop-dialog').open, 'closed path settings');
    await click('#language-display-btn');
    await click('#theme-toggle-btn');

    await click('#batch-review-button');
    await waitFor(() => document.querySelector('#batch-review-rows').children.length === 2
        && !document.querySelector('#batch-review-refresh').disabled, 'all-system read-only summary');
    assert.equal(await evaluate(() => document.querySelector('#batch-review-apply').disabled), true);
    await click('#batch-download-artwork');
    await waitFor(() => !document.querySelector('#batch-review-apply').disabled
        && document.querySelector('#batch-review-rows').children.length === 2, 'names-only batch summary');
    assert.deepEqual(await evaluate(() => Array.from(document.querySelectorAll('#batch-review-rows tr')).map(row => row.children[1].textContent)), ['1','1']);
    await screenshot('02-all-systems-summary');
    await click('#batch-review-dialog header button');
    await waitFor(() => !document.querySelector('#batch-review-dialog').open, 'cancelled whole-library review');
    assert.equal(await evaluate(visible, '#game-library'), true);
    await click('#theme-toggle-btn');
    await click('#language-display-btn');
    await click('#batch-review-button');
    await waitFor(() => !document.querySelector('#batch-review-apply').disabled, 'English all-system summary');
    assert.equal(await evaluate(() => document.querySelector('#batch-review-title').textContent), 'All-system change summary');
    await screenshot('02-dark-en-all-systems-summary');
    await click('#batch-review-dialog header button');
    await click('#language-display-btn');
    await click('#theme-toggle-btn');
    await click('#preview-button');
    await waitFor(() => !document.querySelector('#option-download-artwork').disabled
        && document.querySelector('#preview-table-body .new-label-text')?.textContent === '暗影狂奔', 'default preview');
    assert.equal(await evaluate(() => document.querySelector('#option-write-names').checked && document.querySelector('#option-download-artwork').checked), true);
    await click('#option-download-artwork');
    await waitFor(() => document.querySelector('#workspace-title')?.textContent === 'SNES · 修复预览'
        && document.querySelector('#preview-table-body .new-label-text')?.textContent === '暗影狂奔'
        && !document.querySelector('#apply-button').disabled, 'actionable translated preview');
    assert.equal(await evaluate(visible, '#preview-area'), true);
    assert.equal(await evaluate(visible, '#apply-button'), true);
    assert.equal(await evaluate(() => document.querySelectorAll('#preview-table-body tr').length), 1);
    assert.equal(await evaluate(() => document.querySelectorAll('#preview-table-body input').length), 0);
    assert.equal(await evaluate(() => document.querySelectorAll('#preview-table-body .replace-artwork').length), 1);
    assert.equal(await evaluate(() => document.querySelectorAll('#preview-table-body .mini-btn, #preview-table-body .link-preview').length), 0);
    assert.equal(await evaluate(() => document.querySelector('#preview-table-body .name-secondary').textContent), 'Shadowrun (USA).sfc');
    assert.equal(await evaluate(() => document.querySelector('#preview-table-body .name-secondary').title), '/roms/snes/Shadowrun (USA).sfc');
    await click('#preview-table-body .name-secondary');
    assert.equal(await evaluate(() => document.querySelector('#inspector-panel')), null);
    await screenshot('03-preview');
    await click('#preview-table-body .new-label-text');
    await send('Input.insertText', {text: '取消的名称'});
    await send('Input.dispatchKeyEvent', {type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27});
    await send('Input.dispatchKeyEvent', {type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27});
    assert.equal(await evaluate(() => document.querySelector('#preview-table-body .new-label-text').textContent), '暗影狂奔');
    await click('#preview-table-body .new-label-text');
    await send('Input.insertText', {text: '暗影狂奔（校对）'});
    await send('Input.dispatchKeyEvent', {type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13});
    await send('Input.dispatchKeyEvent', {type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13});
    assert.equal(await evaluate(() => document.querySelector('#preview-table-body .new-label-text').textContent), '暗影狂奔（校对）');
    await click('#preview-table-body .thumb-source-text');
    await send('Input.insertText', {text: 'Shadowrun (Japan)'});
    await click('#workspace-title');
    assert.equal(await evaluate(() => document.querySelector('#preview-table-body .thumb-source-text').textContent), 'Shadowrun (Japan)');
    assert.equal(await evaluate(() => document.querySelector('#preview-table-body td:last-child').textContent), '本次不处理');
    await screenshot('03-preview-edited');

    await click('#browse-games-button');
    await click('#choose-image-directory');
    assert.equal(await evaluate(() => document.activeElement.id), 'thumbnails_override');
    const override = path.join(libraryPath, '自定义图片');
    fs.mkdirSync(override);
    await send('Input.insertText', {text: override});
    await click('#desktop-close');
    await waitFor(() => !document.querySelector('#desktop-dialog').open
        && document.querySelector('#game-library').getAttribute('aria-busy') === 'false', 'saved image override');
    assert.equal(await evaluate(visible, '#image-directory-notice'), false);
    const gba = '.playlist-system-tab[aria-label="Nintendo - Game Boy Advance"]';
    await click(gba);
    await waitFor(() => document.querySelector('#workspace-title').textContent.includes('GBA')
        && document.querySelector('#game-library').getAttribute('aria-busy') === 'false', 'GBA with shared image override');
    assert.equal(await evaluate(() => document.querySelector('#thumbnails_override').value), override);
    assert.equal(await evaluate(visible, '#image-directory-notice'), false);
    await send('Page.reload');
    await waitFor(() => document.querySelector('#library-onboarding')?.getAttribute('aria-busy') === 'false', 'reloaded home');
    await click('#home-recent button');
    await waitFor(() => document.querySelector('#game-library')?.getAttribute('aria-busy') === 'false'
        && document.querySelector('.game-library-table tbody tr'), 'reopened library');
    assert.equal(await evaluate(() => document.querySelector('#thumbnails_override').value), override);
    assert.equal(await evaluate(visible, '#image-directory-notice'), false);

    const detected = path.join(libraryPath, 'thumbnails');
    fs.mkdirSync(detected);
    await click('#settings-button');
    await evaluate(() => { const input = document.querySelector('#thumbnails_override'); input.focus(); input.select(); });
    await send('Input.dispatchKeyEvent', {type: 'keyDown', key: 'Backspace', code: 'Backspace', windowsVirtualKeyCode: 8});
    await send('Input.dispatchKeyEvent', {type: 'keyUp', key: 'Backspace', code: 'Backspace', windowsVirtualKeyCode: 8});
    await click('#scan-device-btn');
    await waitFor(() => !document.querySelector('#desktop-dialog').open
        && document.querySelector('#game-library').getAttribute('aria-busy') === 'false', 'detected artwork folder');
    const config = await evaluate(async () => (await fetch('/api/config')).json());
    assert.equal(config.thumbnails_override, '');
    assert.equal(config.thumbnails_dir, detected);
    assert.equal(await evaluate(visible, '#image-directory-notice'), false);
    assert.equal(await evaluate(() => document.querySelector('#game-library-rows .game-image-placeholder').textContent), '缺图');
    assert.equal(await evaluate(() => document.querySelectorAll('#game-library-rows .artwork-chip').length), 0);
    await screenshot('04-auto-artwork');
    await click(system);
    await waitFor(() => document.querySelector('#workspace-title').textContent.includes('SNES')
        && document.querySelector('#game-library').getAttribute('aria-busy') === 'false', 'SNES with artwork directory');
    const boxFile = path.join(detected, 'Nintendo - Super Nintendo Entertainment System', 'Named_Boxarts', 'Shadowrun (USA).png');
    const boxBytes = Buffer.from(await evaluate(async () => Array.from(new Uint8Array(await (await fetch('/api/artwork/thumbnail?system=SNES&kind=Named_Boxarts&name=Game.png')).arrayBuffer()))));
    fs.mkdirSync(path.dirname(boxFile), {recursive:true});
    fs.writeFileSync(boxFile, boxBytes);
    await click(gba);
    await waitFor(() => document.querySelector('#game-library').getAttribute('aria-busy') === 'false', 'GBA before artwork reread');
    await click(system);
    await waitFor(() => document.querySelectorAll('#game-library-rows .artwork-chip').length === 3, 'partial artwork expands type markers');
    await screenshot('04-partial-artwork');
    const brokenFile = path.join(detected, 'Nintendo - Super Nintendo Entertainment System', 'Named_Snaps', 'Shadowrun (USA).png');
    fs.mkdirSync(path.dirname(brokenFile), {recursive:true});
    fs.writeFileSync(brokenFile, 'damaged test image');
    await click(gba);
    await waitFor(() => document.querySelector('#game-library').getAttribute('aria-busy') === 'false', 'GBA before damaged artwork reread');
    await click(system);
    await waitFor(() => document.querySelectorAll('#game-library-rows .artwork-chip-invalid').length === 1, 'damaged artwork keeps individual markers');
    assert.equal(await evaluate(() => document.querySelector('#game-library-filter-problem').textContent.endsWith('1')), true);
    await screenshot('04-damaged-artwork');
    await click('#preview-button');
    await waitFor(() => document.querySelector('#preview-table-body .new-label-text')?.textContent === '暗影狂奔', 'fresh preview');
    if (!await evaluate(() => document.querySelector('#option-download-artwork').checked)) {
        await click('#option-download-artwork');
        await waitFor(() => !document.querySelector('#option-write-names').disabled, 'combined preview reanalysis');
    }
    await click('#option-write-names');
    await waitFor(() => !document.querySelector('#option-write-names').disabled
        && document.querySelector('#preview-table-body .new-label-text')?.textContent === 'Shadowrun (USA)', 'artwork-only keeps current name');
    await screenshot('04-artwork-only-preview');
    await click('#option-write-names');
    await waitFor(() => !document.querySelector('#option-download-artwork').disabled, 'names restored');
    await click('#option-download-artwork');
    await waitFor(() => !document.querySelector('#option-write-names').disabled
        && document.querySelector('#preview-table-body .new-label-text')?.textContent === '暗影狂奔', 'names-only regenerated');
    await click('#preview-table-body .replace-artwork');
    await waitFor(visible, 'single-game artwork dialog', '#artwork-dialog');
    await waitFor(() => !document.querySelector('#artwork-search').disabled, 'artwork context loaded');
    assert.equal(await evaluate(visible, '#artwork-upload'), true);
    assert.equal(await evaluate(visible, '#artwork-source'), true);
    assert.equal(await evaluate(() => document.querySelector('#artwork-preview')), null);
    assert.equal(await evaluate(() => document.querySelector('#artwork-confirm').disabled), true);
    await waitFor(() => document.querySelectorAll('#artwork-results .artwork-option').length > 0, 'automatic official gallery candidates');
    assert.equal(await evaluate(() => document.querySelector('#artwork-confirm').disabled), true);
    await screenshot('05-artwork-dialog');
    await click('#artwork-results .artwork-option');
    await waitFor(() => !document.querySelector('#artwork-confirm').disabled, 'explicit candidate selection loads comparison');
    assert.equal(await evaluate(visible, '#artwork-comparison'), true);
    await screenshot('05-candidate-preview');
    await evaluate(() => { const input = document.querySelector('#artwork-source'); input.focus(); input.select(); });
    await send('Input.insertText', {text:'Unmatched example'});
    if (!await evaluate(() => document.querySelector('#artwork-kind-Named_Boxarts').checked)) await click('#artwork-kind-Named_Boxarts');
    await click('#artwork-search');
    await waitFor(visible, 'no official results offers alternate source', '#artwork-secondary');
    assert.equal(await evaluate(() => document.querySelector('#artwork-confirm').disabled), true);
    await screenshot('05-no-official-match');
    await click('#artwork-close');
    assert.deepEqual(fs.readFileSync(boxFile), boxBytes);
    assert.equal(fs.readFileSync(brokenFile, 'utf8'), 'damaged test image');
    await click('#preview-table-body .new-label-text');
    await send('Input.insertText', {text: '暗影狂奔（本地）'});
    await send('Input.dispatchKeyEvent', {type:'keyDown', key:'Enter', code:'Enter', windowsVirtualKeyCode:13});
    await send('Input.dispatchKeyEvent', {type:'keyUp', key:'Enter', code:'Enter', windowsVirtualKeyCode:13});
    await click('#preview-table-body [data-save-override]');
    await waitFor(() => document.querySelector('#apply-button').disabled, 'local correction saved for reanalysis');
    const savedOverrides = await evaluate(async () => (await fetch('/api/overrides/list')).json());
    assert.equal(savedOverrides.entries.some(entry => entry.new_label === '暗影狂奔（本地）'), true);
    await screenshot('06-local-correction');
    assert.deepEqual(errors, [], 'Page errors');
    console.log(`Browser smoke OK (${width}×${height}): home → local library → SNES → translated preview`);
}

main().catch(async error => {
    console.error(error.stack);
    fs.writeFileSync(path.join(output, 'errors.json'), JSON.stringify({error: error.message, pageErrors: errors}, null, 2));
    if (socket.readyState === WebSocket.OPEN) {
        try {
            await screenshot('failure');
            fs.writeFileSync(path.join(output, 'failure.html'), await evaluate(() => document.documentElement.outerHTML));
        } catch (diagnosticError) {
            console.error('Could not capture browser diagnostics:', diagnosticError.message);
        }
    }
    process.exitCode = 1;
}).finally(() => socket.close());
