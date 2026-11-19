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
let holdOverview = false;
let holdSources = true;
let heldSources = null;
let holdRecent = false;
let heldRecent = null;
let heldOverview = null;
let expectedOverviewFailure = false;

function send(method, params = {}) {
    return new Promise((resolve, reject) => {
        const id = ++sequence;
        const timer = setTimeout(() => {
            pending.delete(id);
            reject(new Error(`CDP timed out: ${method}`));
        }, 30000);
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
        if (url.startsWith(baseUrl + '/') && status >= 400 && !(expectedOverviewFailure && url.includes('/api/library/overview') && status === 503)) errors.push(`HTTP ${status}: ${url}`);
    } else if (message.method === 'Fetch.requestPaused') {
        if (message.params.request.url.includes('/api/library/recent')) {
            if (holdRecent) heldRecent = message.params.requestId;
            else send('Fetch.continueRequest', {requestId:message.params.requestId}).catch(error=>errors.push(error.message));
            return;
        }
        if (message.params.request.url.includes('/api/library/sources')) {
            if (holdSources) heldSources = message.params.requestId;
            else send('Fetch.continueRequest', {requestId:message.params.requestId}).catch(error=>errors.push(error.message));
            return;
        }
        if (message.params.request.url.includes('/api/library/overview')) {
            if (holdOverview) heldOverview = message.params.requestId;
            else send('Fetch.continueRequest', {requestId:message.params.requestId}).catch(error=>errors.push(error.message));
            return;
        }
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
    const deadline = Date.now() + 20000;
    while (Date.now() < deadline) {
        assert.deepEqual(errors, [], 'Page errors');
        const result = await evaluate(fn, ...args);
        if (result) return result;
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
    console.log('Click:', selector);
    await waitFor(visible, `visible ${selector}`, selector);
    await waitFor(selector => !document.querySelector(selector).disabled, `enabled ${selector}`, selector);
    const point = await waitFor(async selector => {
        document.querySelector(selector)?.scrollIntoView({block: 'center', behavior: 'instant'});
        // Match a real pointer: let the scrolled layout paint before hit testing.
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        // A read response may have rendered a new control during those frames.
        const element = document.querySelector(selector);
        if (!element || element.disabled) return null;
        const first = element.getBoundingClientRect();
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        const again = document.querySelector(selector);
        if (!again || again.disabled) return null;
        const rect = again.getBoundingClientRect();
        if (first.x !== rect.x || first.y !== rect.y || first.width !== rect.width || first.height !== rect.height) return null;
        const x = rect.left + rect.width / 2, y = rect.top + rect.height / 2;
        if (!again.contains(document.elementFromPoint(x, y))) return null;
        return {x, y};
    }, `unobscured painted control ${selector}`, selector);
    await send('Input.dispatchMouseEvent', {type: 'mouseMoved', ...point});
    await send('Input.dispatchMouseEvent', {type: 'mousePressed', button: 'left', clickCount: 1, ...point});
    await send('Input.dispatchMouseEvent', {type: 'mouseReleased', button: 'left', clickCount: 1, ...point});
}

async function screenshot(name) {
    console.log('Screenshot:', name);
    await delay(200); // Let theme transitions settle before capturing visual evidence.
    const {data} = await send('Page.captureScreenshot', {format: 'png'});
    fs.writeFileSync(path.join(output, name + '.png'), Buffer.from(data, 'base64'));
    if (name !== 'failure') assert.deepEqual(await evaluate(() => [...document.querySelectorAll('.dialog-icon-button')].filter(button => button.checkVisibility() && (!button.querySelector('svg use') || !button.getAttribute('aria-label') || !button.title)).map(button => button.id || button.outerHTML)), [], 'Visible icon actions retain their SVG, name and tooltip');
}

async function main() {
    await new Promise((resolve, reject) => {
        socket.addEventListener('open', resolve, {once: true});
        socket.addEventListener('error', () => reject(new Error('Cannot connect to Chrome')), {once: true});
    });
    await send('Runtime.enable');
    await send('Page.enable');
    await send('Network.enable');
    await send('Fetch.enable', {patterns: [{urlPattern: 'https://thumbnails.libretro.com/*'}, {urlPattern: '*api/library/overview*'}, {urlPattern: '*api/library/sources*'}, {urlPattern: '*api/library/recent*'}]});
    await send('Emulation.setDeviceMetricsOverride', {width: Number(width), height: Number(height), deviceScaleFactor: 1, mobile: false});
    await send('Page.navigate', {url: baseUrl});
    await waitFor(() => document.readyState === 'complete' && !document.querySelector('#library-onboarding').hidden && !document.querySelector('#library-read-dialog').open, 'home is visible while device discovery is pending');
    await screenshot('00-home-discovery');
    assert.ok(heldSources, 'Device discovery is still pending while home is visible');
    holdSources = false;
    await send('Fetch.continueRequest', {requestId:heldSources});
    await waitFor(() => document.readyState === 'complete'
        && document.querySelector('#library-onboarding')?.getAttribute('aria-busy') === 'false', 'home discovery');
    assert.equal(await evaluate(() => document.querySelector('#home-manual-open, #home-scan-open')), null);
    assert.equal(await evaluate(visible, '.sidebar'), false);
    assert.equal(await evaluate(visible, '#preview-area'), false);
    assert.equal(await evaluate(() => document.querySelector('#home-devices [data-status="usb_only"]')?.textContent.includes('解锁掌机并选择 USB 文件传输')), true);
    assert.equal(await evaluate(() => document.querySelector('#home-devices [data-status="usb_only"] button')), null);
    assert.equal(await evaluate(()=>document.title),'RetroArch 助手');
    assert.equal(await evaluate(()=>document.getElementById('scan-default-btn').textContent.trim()),'');
    assert.equal(await evaluate(()=>document.getElementById('scan-default-btn').getAttribute('aria-label')),'重新检测');
    assert.equal(await evaluate(()=>document.getElementById('home-library-folder')),null);
    await screenshot('01-home');
    assert.equal(await evaluate(()=>document.querySelector('.workbench-nav, #workbench-task')),null);
    assert.equal(await evaluate(()=>document.querySelector('#task-center-button,#task-popover,[data-desktop-view="tasks"]')),null);
    assert.equal(await evaluate(() => document.querySelector('#usb-debug-help, #home-local-open')), null);
    await click('#settings-button');
    assert.equal(await evaluate(() => document.querySelectorAll('dialog[open]').length), 1);
    assert.equal(await evaluate(() => document.querySelectorAll('[data-desktop-view],#data-source-settings').length), 0);
    assert.equal(await evaluate(visible, '#path-settings'), false);
    assert.equal(await evaluate(() => [...document.querySelectorAll('#desktop-dialog button')].filter(button => button.checkVisibility()).every(button => button.querySelector('svg') && button.getAttribute('aria-label'))), true);
    await waitFor(visible,'preferences settings','#preference-settings');
    assert.equal(await evaluate(() => document.activeElement.id), 'desktop-title', 'Opening settings focuses the heading instead of an action');
    await click('#preference-language input[value="en"]');
    assert.equal(await evaluate(()=>document.title),'RetroArch Assistant');
    assert.equal(await evaluate(()=>document.getElementById('desktop-close').getAttribute('aria-label')),'Close');
    assert.equal(await evaluate(()=>localStorage.getItem('plcn-ui-language')),'en');
    await click('#preference-language input[value="zh"]');
    await click('#preference-theme input[value="system"]');
    await send('Emulation.setEmulatedMedia', {features:[{name:'prefers-color-scheme',value:'dark'}]});
    await waitFor(()=>document.body.dataset.theme==='dark','system theme changes while preferences are open');
    await screenshot('01-preferences-dark');
    await click('#preference-theme input[value="light"]');
    assert.equal(await evaluate(()=>document.body.dataset.theme),'light');
    assert.equal(await evaluate(()=>localStorage.getItem('plcn-theme')),'light');
    await send('Emulation.setEmulatedMedia', {features:[]});
    await screenshot('01-preferences');
    assert.equal(await evaluate(() => [...document.querySelectorAll('#preference-settings .preference-row')].every(row => {
        const label = row.firstElementChild.getBoundingClientRect();
        const control = row.lastElementChild.getBoundingClientRect();
        return Math.abs((label.top + label.bottom) / 2 - (control.top + control.bottom) / 2) < 2
            && control.left > label.right && control.right <= row.getBoundingClientRect().right + 1;
    })), true, 'Preference labels and controls share a row without overlap');
    assert.equal(await evaluate(() => getComputedStyle(document.querySelector('#desktop-dialog')).backgroundColor === getComputedStyle(document.querySelector('.sidebar')).backgroundColor), true);
    await click('#desktop-close');

    await click('#workbench-device');
    await waitFor(visible, 'library path dialog', '#path-settings');
    assert.equal(await evaluate(() => document.querySelectorAll('#path-settings input[type="text"]').length), 2);
    assert.equal(await evaluate(() => document.querySelector('.topbar .mode-switch')), null);
    await screenshot('01-path-settings');
    await evaluate(() => { const input = document.querySelector('#retroarch_root'); input.focus(); input.select(); });
    await send('Input.insertText', {text: libraryPath});
    await waitFor(()=>!workbenchOverview.loading,'preceding task refresh');
    holdOverview = true;
    await click('#scan-device-btn');
    for(let attempt=0;!heldOverview&&attempt<150;attempt++)await delay(100);
    assert.ok(heldOverview,'overview request held for loading verification');
    assert.equal(await evaluate(()=>document.querySelector('#library-read-dialog').open),true);
    assert.equal(await evaluate(()=>document.querySelector('.app-shell').getAttribute('aria-busy')),'true');
    await screenshot('01-library-loading');
    await evaluate(()=>toggleTheme());
    await screenshot('01-library-loading-dark');
    await evaluate(()=>toggleTheme());
    expectedOverviewFailure=true;
    await send('Fetch.fulfillRequest',{requestId:heldOverview,responseCode:503,responseHeaders:[{name:'Content-Type',value:'application/json'}],body:Buffer.from(JSON.stringify({error:'验收模拟：设备暂时离线'})).toString('base64')});
    heldOverview=null;holdOverview=false;
    await waitFor(()=>document.querySelector('#library-read-actions').hidden===false,'read failure actions');
    assert.equal(await evaluate(()=>document.activeElement.id),'library-read-retry');
    await screenshot('01-library-read-failure');
    await click('#library-read-retry');
    await waitFor(()=>!document.querySelector('#library-read-dialog').open,'read retry closes overlay');
    const cardCount=await evaluate(()=>document.querySelectorAll('.workbench-cards > button').length);
    assert.equal(await evaluate(()=>document.querySelectorAll('.platform-locations').length),0);
    assert.match(await evaluate(()=>document.querySelector('.overview-subtitle').textContent),/^\d+ 个游戏 · \d+ 个主机$/);
    assert.equal(await evaluate(()=>document.querySelector('.overview-subtitle').textContent.includes('待分类')),false);
    assert.equal(await evaluate(()=>document.querySelector('#automatic-scan-button')),null);
    assert.equal(await evaluate(()=>document.querySelector('.completion-entry').hidden),true);
    await waitFor(()=>document.querySelector('#overview-status'),'artwork status bar after overview load');
    assert.match(await evaluate(()=>document.querySelector('.overview-status-text').textContent),/^\d+ 个游戏缺少封面 · 1 个游戏尚未使用中文名$/);
    assert.equal(await evaluate(()=>document.querySelector('#overview-complete-button').title),'自动补全中文名与封面；补全后仍提示的项目需手动处理');
    assert.deepEqual(await evaluate(()=>Array.from(document.querySelectorAll('.platform-heading strong'),el=>el.textContent).sort()),['Game Boy Advance','Super Nintendo Entertainment System']);
    assert.equal(await evaluate(()=>Array.from(document.querySelectorAll('.platform-fan')).every(fan=>fan.children.length===3)),true);
    await click('#library-all-systems');

    const rectOf = sel => evaluate(s => {
        const r = document.querySelector(s).getBoundingClientRect();
        return {x: Math.round(r.x), y: Math.round(r.y), width: Math.round(r.width), height: Math.round(r.height)};
    }, sel);
    const rectsBefore = {
        topbar: await rectOf('.topbar'),
        panelHeader: await rectOf('.panel-header'),
        previewButton: await rectOf('#preview-button'),
    };
    holdOverview=true;
    await evaluate(()=>refreshWorkbenchOverview());
    for(let attempt=0;!heldOverview&&attempt<150;attempt++)await delay(100);
    assert.ok(heldOverview,'refresh request held');
    assert.equal(await evaluate(()=>document.querySelector('#library-read-dialog').open),false);
    assert.equal(await evaluate(visible,'#library-read-banner'),true);
    assert.deepEqual({
        topbar: await rectOf('.topbar'),
        panelHeader: await rectOf('.panel-header'),
        previewButton: await rectOf('#preview-button'),
    }, rectsBefore, 'refresh banner must not shift layout');
    assert.equal(await evaluate(()=>document.querySelectorAll('.workbench-cards > button').length),cardCount);
    await screenshot('01-library-refresh');
    holdOverview=false;await send('Fetch.continueRequest',{requestId:heldOverview});heldOverview=null;
    await waitFor(()=>document.querySelector('#library-read-banner').hidden,'refresh done');
    holdOverview=true;
    await evaluate(()=>{beginWorkbenchOperation('scan');refreshWorkbenchOverview();});
    await delay(1000);
    assert.equal(heldOverview,null,'overview must not be read while an operation is writing');
    await evaluate(()=>endWorkbenchOperation());
    for(let attempt=0;!heldOverview&&attempt<150;attempt++)await delay(100);
    assert.ok(heldOverview,'deferred overview read starts once the operation ends');
    holdOverview=false;await send('Fetch.continueRequest',{requestId:heldOverview});heldOverview=null;
    await waitFor(()=>!workbenchOverview.loading&&document.querySelector('#library-read-banner').hidden,'deferred refresh done');
    await waitFor(() => document.querySelectorAll('.playlist-system-tab').length === 3
        && !document.querySelector('#library-all-systems').disabled
        && document.querySelector('#overview-complete-button')?.disabled === false, 'all-systems row and scan completion');
    assert.equal(await evaluate(() => document.querySelector('#library-all-systems').getAttribute('aria-pressed')), 'true');
    assert.deepEqual(await evaluate(()=>Array.from(document.querySelectorAll('.playlist-system-tab .system-display-name'),el=>el.textContent)),['全部主机','GBA','SNES']);
    assert.equal(await evaluate(()=>document.querySelector('#library-all-systems .system-game-count').textContent),String(cardCount));
    assert.equal(await evaluate(()=>Array.from(document.querySelectorAll('.playlist-system-tab')).every(row=>row.firstElementChild.tagName.toLowerCase()==='svg'&&row.children.length===3)),true);
    await click('#settings-button');
    await waitFor(visible,'preferences from topbar','#preference-settings');
    await click('#desktop-close');
    await click('#workbench-device');
    await waitFor(visible,'detected library settings','#path-settings');
    assert.equal(await evaluate(visible,'#artwork-directory-settings'),false);
    await click('#desktop-close');

    await waitFor(()=>!document.querySelector('#desktop-dialog').open,'directory settings closed');
    await evaluate(()=>openOperationHistory('completion'));
    await waitFor(()=>document.querySelector('#desktop-content [data-job-id] details'),'completion history from library');
    await click('#desktop-content [data-job-id] details > summary');
    await waitFor(()=>document.querySelector('#desktop-content details[open]')?.textContent.includes('测试图片网络失败'),'failed image details');
    assert.equal(await evaluate(() => document.querySelector('#desktop-dialog .desktop-toolbar')),null);
    assert.equal(await evaluate(()=>document.querySelector('#desktop-content [data-chd-operation],[data-rom-storage-operation]')),null);
    await click('#desktop-content [data-job-id] > button');
    await waitFor(()=>document.querySelectorAll('#desktop-content [data-job-id]').length===2
        && !workbench.operation,'artwork retry without editing any playlists');
    await screenshot('01-completion-history');
    await click('#desktop-close');

    assert.equal(await evaluate(() => document.querySelector('#overview-complete-button').disabled), false);
    assert.equal(await evaluate(() => document.querySelector('#preview-button').disabled), false);
    assert.equal(await evaluate(visible, '#game-library'), false);
    assert.equal(await evaluate(() => document.querySelector('#workspace-title').textContent), '游戏库');
    const gbaCard = '.overview-system-card[data-system="Nintendo - Game Boy Advance"]';
    const originalCovers = await evaluate(() => {
        const {covers} = workbenchOverview.data.playlists
            .find(playlist => playlist.system === 'Nintendo - Game Boy Advance').locations.local;
        const makeCover = (width, height, color, label) => {
            const canvas = document.createElement('canvas');
            canvas.width = width;
            canvas.height = height;
            const context = canvas.getContext('2d');
            context.fillStyle = color;
            context.fillRect(0, 0, width, height);
            return {url: canvas.toDataURL(), label};
        };
        return covers.splice(0, covers.length,
            makeCover(48, 30, '#2461a6', 'First landscape'),
            makeCover(30, 48, '#b7562a', 'Portrait outlier'),
            {url: 'data:image/png,broken', label: 'Unreadable cover'},
            makeCover(48, 30, '#749268', 'Middle landscape'),
            makeCover(48, 30, '#c79a45', 'Last landscape'),
        );
    });
    await evaluate(()=>renderWorkbenchOverview(true));
    await waitFor(selector=>document.querySelectorAll(selector+' .platform-fan img').length===3,
        'three landscape covers selected from five candidates', gbaCard);
    const fan = await evaluate(selector => {
        const card = document.querySelector(selector);
        const art = card.querySelector('.platform-art');
        renderWorkbenchOverview(true);
        const currentArt = document.querySelector(selector +' .platform-art');
        const covers = [...currentArt.querySelectorAll('.platform-cover')];
        return {
            titles: covers.map(slot=>slot.title),
            ratios: covers.map(slot=>slot.offsetWidth / slot.offsetHeight),
            front: getComputedStyle(covers[1]).zIndex,
            reused: art===currentArt,
        };
    }, gbaCard);
    assert.deepEqual(fan.titles, ['First landscape', 'Middle landscape', 'Last landscape']);
    assert.ok(fan.ratios.every(ratio=>Math.abs(ratio-1.6)<0.03));
    assert.equal(fan.front,'1');
    assert.equal(fan.reused,true);

    await send('Emulation.setDeviceMetricsOverride', {width:390,height:530,deviceScaleFactor:1,mobile:false});
    await send('Emulation.setEmulatedMedia', {features:[{name:'prefers-reduced-motion',value:'reduce'}]});
    assert.ok(await evaluate(selector=>{
        const card = document.querySelector(selector);
        const bounds = card.getBoundingClientRect();
        return [...card.querySelectorAll('.platform-cover')].every(slot=>{
            const rect = slot.getBoundingClientRect();
            return rect.left>=bounds.left && rect.right<=bounds.right &&
                getComputedStyle(slot).transitionDuration==='0s';
        });
    }, gbaCard));
    await screenshot('01-cover-fan-narrow');
    await send('Emulation.setEmulatedMedia', {features:[]});
    await send('Emulation.setDeviceMetricsOverride', {width:Number(width),height:Number(height),deviceScaleFactor:1,mobile:false});
    await evaluate(covers => {
        const location = workbenchOverview.data.playlists
            .find(playlist => playlist.system === 'Nintendo - Game Boy Advance').locations.local;
        location.covers = covers;
        renderWorkbenchOverview(true);
    }, originalCovers);
    assert.equal(await evaluate(()=>document.getElementById('manual-scan-button').title),'扫描新增游戏');
    await screenshot('01-system-covers');

    assert.equal(await evaluate(()=>document.querySelector('[aria-label="搜索主机"]')),null);
    const selectedCard = '#library-overview .overview-system-card[data-system="Nintendo - Super Nintendo Entertainment System"]';
    await send('Emulation.setDeviceMetricsOverride', {width:390,height:400,deviceScaleFactor:1,mobile:false});
    const overviewScrollTop = await evaluate(()=>{
        const panel = document.querySelector('.main-panel');
        panel.scrollTop = 90;
        return panel.scrollTop;
    });
    assert.ok(overviewScrollTop>0);
    await evaluate(selector=>document.querySelector(selector).click(),selectedCard);
    assert.equal(await evaluate(()=>document.querySelector('.main-panel').scrollTop),0);
    await click('#back-to-systems');
    assert.equal(await evaluate(()=>document.querySelector('.main-panel').scrollTop),overviewScrollTop);
    assert.equal(await evaluate(selector=>document.activeElement.matches(selector),selectedCard),true);
    await screenshot('01-system-covers-narrow');
    await send('Emulation.setDeviceMetricsOverride', {width:Number(width),height:Number(height),deviceScaleFactor:1,mobile:false});

    await click('.playlist-system-tab[aria-label="Nintendo - Game Boy Advance"]');
    await waitFor(()=>gameLibrary.data?.items.length===1,'GBA cover grid');
    const wideFrame = await evaluate(async () => {
        const grid = document.getElementById('game-library-grid');
        const entry = gameLibrary.data.items[0];
        const canvas = document.createElement('canvas');
        canvas.width = 512;
        canvas.height = 321;
        const imageURL = entry.image_url;
        entry.image_url = canvas.toDataURL();
        renderGameLibrary();
        const image = grid.querySelector('.game-card-art img');
        image.loading = 'eager';
        await image.decode();
        const {width, height} = image.parentElement.getBoundingClientRect();
        const fit = getComputedStyle(image).objectFit;
        entry.image_url = imageURL;
        renderGameLibrary();
        setGameLibraryFilter('missing');
        const card = grid.querySelector('.game-card-art').getBoundingClientRect();
        setGameLibraryFilter('all');
        return {frame: width / height, fit, filteredFrame: card.width / card.height};
    });
    assert.ok(Math.abs(wideFrame.frame-1.6)<0.01);
    assert.equal(wideFrame.fit,'contain');
    assert.equal(wideFrame.filteredFrame,wideFrame.frame);

    const system = '.playlist-system-tab[aria-label="Nintendo - Super Nintendo Entertainment System"]';
    await click(system);
    await waitFor(() => document.querySelector('#workspace-title')?.textContent.includes('SNES')
        && document.querySelector('.game-library-table tbody')?.textContent.includes('Shadowrun (USA)'), 'selected SNES games');
    assert.equal(await evaluate(selector => document.querySelector(selector).getAttribute('aria-pressed'), system), 'true');
    assert.equal(await evaluate(visible, '#game-library'), true);
    assert.equal(await evaluate(visible, '#library-onboarding'), false);
    assert.equal(await evaluate(visible, '#preview-area'), false);
    assert.equal(await evaluate(visible, '#image-directory-notice'), false);
    assert.equal(await evaluate(() => document.querySelector('#game-library-filter-problem').textContent), '需检查 0');
    assert.equal(await evaluate(() => document.querySelector('#game-library-rows .game-image-placeholder').getAttribute('aria-label')), '缺封面');
    assert.equal(await evaluate(visible, '#game-library-grid'), true);
    assert.ok(await evaluate(()=>{
        const card = document.querySelector('#game-library-grid .game-card-art').getBoundingClientRect();
        return Math.abs(card.width / card.height - 2/3)<0.01;
    }));
    assert.equal(await evaluate(()=>document.querySelectorAll('#game-library-grid .game-cover-card').length),1);
    assert.equal(await evaluate(()=>document.querySelector('#game-library-grid .game-card-art').textContent),'缺封面');
    assert.equal(await evaluate(()=>document.querySelector('#workspace-title .workspace-count').textContent),'1 个游戏');
    assert.equal(await evaluate(() => document.querySelector('.completion-entry').hidden), true);
    assert.equal(await evaluate(() => document.querySelector('#game-selection-toolbar').hidden), false);
    assert.equal(await evaluate(() => document.querySelector('#game-selection-toolbar').classList.contains('has-status')), true);
    assert.equal(await evaluate(() => document.querySelector('#game-selection-toolbar .overview-status-text').textContent), '1 款游戏的图片待补全');
    assert.equal(await evaluate(() => document.querySelector('#games-complete-button').textContent), '补全当前列表');
    assert.equal(await evaluate(() => document.querySelector('#games-complete-button').disabled), false);
    assert.equal(await evaluate(() => document.querySelector('#game-library-filter-missing').textContent), '图片待补全 1');
    assert.equal(await evaluate(() => document.querySelector('#game-library-search').placeholder), '搜索 SNES 游戏');
    assert.equal(await evaluate(() => document.querySelector('#game-library-note')), null);
    assert.equal(await evaluate(() => document.querySelector('#games-status')), null);
    await screenshot('02-games');
    await send('Emulation.setDeviceMetricsOverride', {width:390,height:460,deviceScaleFactor:1,mobile:false});
    await send('Emulation.setEmulatedMedia', {features:[{name:'prefers-reduced-motion',value:'reduce'}]});
    const gameScrollTop = await evaluate(()=>{
        const search = document.getElementById('game-library-search');
        search.value = 'Shadowrun';
        search.dispatchEvent(new Event('input'));
        setGameLibraryFilter('missing');
        const panel = document.querySelector('.main-panel');
        panel.scrollTop = 115;
        const previousTop = panel.scrollTop;
        document.querySelector('.game-card-open').click();
        return previousTop;
    });
    assert.ok(gameScrollTop>0);
    await waitFor(()=>Boolean(gameInspector.details),'narrow game details');
    assert.equal(await evaluate(visible,'.game-library-main'),false);
    assert.equal(await evaluate(()=>document.querySelector('.main-panel').scrollTop),0);
    assert.equal(await evaluate(()=>getComputedStyle(document.getElementById('game-inspector')).animationName),'none');
    assert.equal(await evaluate(()=>document.getElementById('inspector-close').textContent),'返回游戏列表');
    assert.equal(await evaluate(()=>document.getElementById('inspector-artwork').textContent),'添加封面');
    await screenshot('02-game-details-narrow');
    await click('#inspector-close');
    assert.equal(await evaluate(()=>document.querySelector('.main-panel').scrollTop),gameScrollTop);
    assert.equal(await evaluate(()=>document.getElementById('game-library-search').value),'Shadowrun');
    assert.equal(await evaluate(()=>gameLibrary.filter),'missing');
    assert.equal(await evaluate(()=>document.activeElement.matches('.game-card-open')),true);
    await send('Emulation.setDeviceMetricsOverride', {width:Number(width),height:Number(height),deviceScaleFactor:1,mobile:false});
    await send('Emulation.setEmulatedMedia', {features:[]});

    await click('#game-library-grid .game-card-open');
    await waitFor(()=>gameInspector.details,'inspector metadata loaded');
    assert.equal(await evaluate(visible,'.game-library-main'),false);
    const detailFields = await evaluate(()=>Array.from(document.querySelectorAll('.inspector-info > dl dt'),node=>node.textContent));
    for (const label of ['文件名称','英文名称','中文名称','主机平台','当前核心','建议核心','大小']) assert.ok(detailFields.includes(label), label);
    assert.equal(await evaluate(visible,'#game-inspector'),true);
    assert.equal(await evaluate(()=>document.querySelectorAll('dialog[open]').length),0);
    assert.equal(await evaluate(()=>Boolean(document.querySelector('#inspector-more'))&&!document.querySelector('#inspector-more').open),true);
    assert.equal(await evaluate(()=>document.querySelector('#inspector-remove')),null);
    assert.ok(await evaluate(()=>document.querySelector('#inspector-locate-file')));
    await screenshot('02-game-inspector');
    await click('#inspector-artwork');
    await waitFor(()=>document.querySelector('#game-inspector #artwork-dialog')?.open,'docked artwork editor');
    assert.equal(await evaluate(()=>document.querySelector('#artwork-dialog').matches(':modal')),false);
    await waitFor(()=>document.querySelectorAll('#artwork-results .artwork-option').length>0,'docked artwork candidates');
    await click('#artwork-results .artwork-option');
    await waitFor(()=>!document.querySelector('#artwork-confirm').disabled,'docked comparison');
    await evaluate(()=>renderGameInspector());
    assert.equal(await evaluate(()=>Boolean(artworkDialogState.candidate)),true);
    await screenshot('02-inline-artwork-comparison');
    await evaluate(()=>{document.querySelector('#game-inspector').scrollTop=0;});
    await screenshot('02-inline-artwork');
    assert.equal(await evaluate(()=>document.querySelector('#game-inspector').scrollWidth<=document.querySelector('#game-inspector').clientWidth),true);
    await evaluate(()=>inspectGame(0));
    assert.equal(await evaluate(()=>artworkDialogState),null);
    assert.equal(await evaluate(()=>workbench.operation),null);
    assert.equal(await evaluate(()=>document.querySelector('#artwork-dialog').open),false);

    await click('#inspector-edit-name');
    await evaluate(()=>{const input=document.querySelector('#inspector-name');input.value='My Shadowrun';input.dispatchEvent(new Event('input',{bubbles:true}));});
    assert.equal(await evaluate(()=>document.querySelector('#inspector-preview-name')),null);
    await click('#inspector-save');
    await waitFor(()=>gameLibrary.data?.items[0]?.label==='My Shadowrun','name saved in playlist');
    await waitFor(()=>gameLibrary.activeIndex===0&&Boolean(gameInspector.details),'inspector retained after name edit');
    assert.equal(await evaluate(()=>gameLibrary.filter),'missing');
    assert.equal(await evaluate(()=>document.getElementById('game-library-search').value),'Shadowrun');
    await evaluate(async()=>{
        const state=await desktopRequest('/api/desktop');
        const edit=state.m3u_operations.find(record=>record.mode==='game_edit');
        const {result}=await runGameJob('/api/m3u/recover',{id:edit.id,action:'restore'},()=>{});
        if(result.status!=='restored')throw new Error('Name recovery failed');
        resetGameLibrary();renderWorkbench();
    });
    await waitFor(()=>gameLibrary.data?.items[0]?.label==='Shadowrun (USA)','name restored');
    await click('#game-view-list');
    assert.ok(await evaluate(visible, '#game-library-table'));
    assert.deepEqual(await evaluate(() => Array.from(document.querySelectorAll('#game-library-table th'), th => th.textContent)), ['', '封面', '游戏名称']);
    assert.deepEqual(await evaluate(() => Array.from(document.querySelector('#game-library-rows tr').cells, td => td.textContent)), ['', '', 'Shadowrun (USA)']);
    assert.equal(await evaluate(() => document.querySelectorAll('#game-library-rows :is(button, input, summary)').length), 2);
    await screenshot('02-compact-game-list');
    await click('#game-library-rows [data-game-details="0"]');
    await waitFor(visible, 'game details opened from list', '#game-inspector');
    await click('#inspector-close');
    assert.equal(await evaluate(() => document.activeElement.dataset.gameDetails), '0');

    await evaluate(()=>toggleTheme());
    await evaluate(()=>toggleUILanguage());
    assert.equal(await evaluate(() => document.querySelector('#image-directory-message').textContent.startsWith('Choose an artwork folder')), true);
    assert.equal(await evaluate(() => document.querySelector('#preview-button').textContent), 'Complete names & artwork');
    assert.equal(await evaluate(() => document.querySelector('#completion-entry-note').textContent), 'Match Chinese names and artwork automatically; preview before applying.');
    assert.deepEqual(await evaluate(()=>Array.from(document.querySelectorAll('#storage-scope button'),button=>button.textContent)),['All storage','Internal','SD card']);
    assert.equal(await evaluate(()=>document.querySelector('.library-browser-header h2').textContent),'Systems');
    await click('.tools-menu > summary');
    assert.doesNotMatch(await evaluate(()=>document.querySelector('.tools-menu').innerText),/\p{Script=Han}/u);
    await evaluate(()=>document.querySelector('.tools-menu').open=false);
    await click('#manual-scan-button');
    await waitFor(()=>document.querySelector('#auto-scan-dialog').open,'scan entry from add-games workspace');
    assert.equal(await evaluate(()=>document.activeElement.id),'auto-scan-title');
    await waitFor(()=>!document.querySelector('#auto-scan-start').disabled,'English scan storage loaded');
    assert.doesNotMatch(await evaluate(()=>document.querySelector('#auto-scan-dialog').innerText),/\p{Script=Han}/u);
    await click('#auto-scan-start');
    await waitFor(()=>document.querySelector('#auto-scan-status').textContent.startsWith('Scan complete:'),'English scan summary');
    await screenshot('02-english-auto-scan');
    await click('#auto-scan-dialog header > button');
    // Import through the native-picker boundary, remove via the batch toolbar,
    // then restore both playlist transactions. ROM copies remain on disk.
    await click('#game-files-button');
    await waitFor(()=>!document.querySelector('#game-files-workspace').hidden,'inline game files workspace');
    assert.equal(await evaluate(()=>document.querySelectorAll('dialog[open]').length),0);
    assert.equal(await evaluate(visible,'#library-browser'),false);
    await click('#game-files-import');
    await waitFor(()=>document.querySelector('#gm-pick-files'),'game import loaded');
    assert.equal(await evaluate(()=>document.querySelector('#gm-preview')),null);
    assert.equal(await evaluate(()=>document.querySelector('#gm-destination-fields').hidden),true);
    assert.equal(await evaluate(()=>document.querySelector('#gm-dialog header button').getAttribute('aria-label')),'Cancel');
    await screenshot('02-game-import-empty');
    await click('#gm-pick-files');
    await waitFor(()=>document.querySelector('#gm-sources')?.textContent.includes('Imported demo.sfc'),'game files selected');
    await waitFor(()=>!gameManagement.busy&&!document.querySelector('#gm-apply').hidden
        && document.querySelector('#gm-apply').textContent==='Import 1 game','auto analysis ready');
    await click('#gm-change-destination');
    assert.equal(await evaluate(()=>document.querySelector('#gm-destination-fields').hidden),false);
    await screenshot('02-game-import-destination');
    await evaluate(libraryPath=>{const input=document.querySelector('#gm-destination');input.value=libraryPath+'/Roms/SNES';input.dispatchEvent(new Event('input',{bubbles:true}));},libraryPath);
    await waitFor(()=>document.querySelector('#gm-apply').disabled,'destination change invalidates analysis');
    await waitFor(()=>!gameManagement.busy&&!document.querySelector('#gm-apply').hidden
        && document.querySelector('#gm-apply').textContent==='Import 1 game','destination re-analysis ready');
    assert.equal(await evaluate(()=>document.querySelectorAll('dialog[open]').length),0);
    await evaluate(()=>{gameManagement.setup.android=true;document.querySelector('#gm-android').value='';gmInvalidate();gmAutoAnalyze();});
    await waitFor(()=>document.querySelector('#gm-android').getAttribute('aria-invalid')==='true','missing Android launch directory guidance');
    assert.equal(await evaluate(()=>document.querySelector('#gm-apply').hidden),false);
    assert.equal(await evaluate(()=>document.querySelector('#gm-apply').disabled),true);
    assert.equal(await evaluate(()=>document.activeElement.id),'gm-android');
    await screenshot('02-game-import-missing-launch-folder');
    await evaluate(()=>{const input=document.querySelector('#gm-android');input.value='/storage/CARD/Roms/SNES';input.dispatchEvent(new Event('input',{bubbles:true}));});
    await waitFor(()=>!gameManagement.busy&&!document.querySelector('#gm-apply').disabled,'launch directory restores import action');
    await screenshot('02-game-import-preview');
    await click('#gm-apply');
    await waitFor(()=>document.querySelector('#gm-status').textContent.startsWith('Added 1 entries')&&!workbench.operation,'import completed');
    await waitFor(()=>gameLibrary.data?.items.length===2,'new game visible');
    assert.equal(await evaluate(()=>document.querySelector('#gm-fields').hidden),true);
    assert.equal(await evaluate(visible,'#gm-view-games'),true);
    assert.equal(await evaluate(visible,'#gm-add-more'),true);
    assert.equal(await evaluate(visible,'#gm-complete-metadata'),true);
    await screenshot('02-game-import-complete');
    assert.equal(fs.readFileSync(path.join(libraryPath,'Roms/SNES/Imported demo.sfc'),'utf8'),'game import fixture');
    await click('#gm-view-games');
    await click('#game-view-grid');
    await click('#game-library-grid [data-game-card="1"] .game-card-open');
    await waitFor(()=>gameInspector.details,'imported game details');
    await click('#inspector-locate-file');
    await waitFor(()=>document.querySelector('.game-files-rows [aria-pressed="true"]')?.textContent.includes('Imported demo.sfc'),'located ROM selected');
    await click('.game-files-toolbar button[aria-label="Delete file"]');
    await waitFor(()=>document.querySelector('.game-file-delete-impact')?.textContent.includes('Imported demo.sfc'),'deletion plan rendered');
    assert.ok(await evaluate(()=>document.querySelector('.game-file-delete-impact').textContent.includes('Imported demo')));
    await click('.game-file-delete-dialog button[aria-label="Close"], .game-file-delete-dialog button.btn-muted');
    await click('.game-files-header button');
    const beforeRomUpdate=fs.readFileSync(path.join(libraryPath,'playlists/Nintendo - Super Nintendo Entertainment System.lpl'));
    await click('#inspector-actions-menu > summary');
    await click('#inspector-update-rom');
    await waitFor(()=>Boolean(gameInspector.romPlan),'ROM update prepared');
    await screenshot('02-rom-update-preview');
    await click('#inspector-rom-confirm');
    await waitFor(()=>!workbench.operation&&Boolean(document.querySelector('#inspector-restore-rom')),'ROM updated with restore entry');
    assert.equal(fs.readFileSync(path.join(libraryPath,'Roms/SNES/Imported demo.sfc'),'utf8'),'new version fixture');
    assert.deepEqual(fs.readFileSync(path.join(libraryPath,'playlists/Nintendo - Super Nintendo Entertainment System.lpl')),beforeRomUpdate);
    await screenshot('02-rom-updated');
    const previousPage = await evaluate(()=>performance.timeOrigin);
    await send('Page.reload');
    await waitFor(previous=>performance.timeOrigin!==previous && document.querySelector('#library-onboarding')?.getAttribute('aria-busy')==='false','app reload before ROM recovery',previousPage);
    await click('#workbench-device');
    await click('#scan-device-btn');
    await click(system);
    await waitFor(()=>gameLibrary.data?.items.some(item=>item.label.includes('Imported demo')),'reopened imported game');
    const importedIndex = await evaluate(()=>gameLibrary.data.items.find(item=>item.label.includes('Imported demo')).index);
    await click(`[data-game-card="${importedIndex}"] .game-card-open`);
    await waitFor(()=>document.querySelector('#inspector-restore-rom'),'durable ROM recovery entry');
    await click('#inspector-actions-menu > summary');
    await click('#inspector-restore-rom');
    await waitFor(()=>!workbench.operation&&gameInspector.details&&!document.querySelector('#inspector-restore-rom'),'previous ROM restored');
    assert.equal(fs.readFileSync(path.join(libraryPath,'Roms/SNES/Imported demo.sfc'),'utf8'),'game import fixture');
    await click('#game-inspector .inspector-close');
    assert.equal(await evaluate(()=>document.querySelector('#game-selection-toolbar').hidden),false);
    assert.equal(await evaluate(()=>document.querySelector('#game-selection-toolbar').classList.contains('has-status')),true);
    await click('#game-library-grid [data-game-card="1"] .game-card-select');
    await waitFor(()=>!document.querySelector('#game-selection-toolbar').hidden,'selection toolbar shown after select');
    await screenshot('02-games-selection');
    await click('#game-selection-complete');
    await waitFor(()=>!document.querySelector('#action-toast').hidden&&!workbench.operation,'selected metadata completion finished');
    await click('#action-toast-details');
    await waitFor(()=>Boolean(workbench.previewKey)&&!workbench.operation,'selected review preview');
    assert.equal(await evaluate(()=>currentChanges.length),1);
    assert.equal(await evaluate(()=>currentChanges[0].index),1);
    await click('#option-write-names');
    await waitFor(()=>Boolean(workbench.previewKey)&&!workbench.operation,'selected scope retained after option change');
    assert.equal(await evaluate(()=>currentChanges.length),1);
    assert.equal(await evaluate(()=>currentChanges[0].index),1);
    await click('#option-write-names');
    await waitFor(()=>Boolean(workbench.previewKey)&&!workbench.operation,'selected name completion restored');
    await evaluate(()=>invalidateWorkbenchPreview());
    await waitFor(()=>gameLibrary.data?.items.length===2,'return to graphical library');
    await click('#game-view-grid');
    await click('#game-library-grid [data-game-card="1"] .game-card-select');
    await click('#game-selection-actions > summary');
    await click('#game-selection-remove');
    await waitFor(()=>!gameManagement.busy&&!document.querySelector('#gm-apply').hidden,'remove preview');
    assert.equal(await evaluate(()=>document.querySelector('#gm-results').querySelectorAll('strong').length),1);
    await screenshot('02-game-removal-preview');
    await click('#gm-apply');
    await waitFor(()=>document.querySelector('#gm-status').textContent.startsWith('Done:')&&!workbench.operation,'removal completed');
    assert.equal(fs.existsSync(path.join(libraryPath,'Roms/SNES/Imported demo.sfc')),true);
    await evaluate(async()=>{
        const state=await desktopRequest('/api/desktop');
        for(const mode of ['game_remove','game_import']){
            const record=state.m3u_operations.find(record=>record.mode===mode);
            const {result}=await gmJob('/api/m3u/recover',{id:record.id,action:'restore'});
            if(result.status!=='restored')throw new Error('Recovery did not restore the playlist');
        }
        resetGameLibrary();renderWorkbench();
    });
    await click('#gm-dialog header button');
    await waitFor(()=>gameLibrary.data?.items.length===1,'original games restored');
    await click('#manual-scan-button');
    await waitFor(()=>document.querySelector('#auto-scan-dialog').open,'auto-scan from add-games workspace');
    await click('#auto-scan-dialog footer button[onclick="openContentScan()"]');
    await waitFor(()=>!document.querySelector('#content-scan-fields').disabled,'English manual setup loaded');
    assert.equal(await evaluate(()=>document.querySelector('#content-scan-title').textContent),'Add games manually');
    assert.doesNotMatch(await evaluate(()=>document.querySelector('#content-scan-dialog footer').innerText),/\p{Script=Han}/u);
    assert.doesNotMatch(await evaluate(()=>document.querySelector('#content-scan-recommendation').textContent),/\p{Script=Han}/u);
    await screenshot('02-english-manual-add');
    await click('#content-scan-close');
    await click('#auto-scan-dialog header > button');
    await screenshot('02-one-click-complete-en');
    await evaluate(() => document.querySelector('#choose-image-directory').click());
    assert.equal(await evaluate(() => document.querySelector('label[for="thumbnails_override"]').textContent), 'Artwork folder (optional override)');
    await screenshot('02-dark-en-path-settings');
    await click('#desktop-close');
    await waitFor(() => !document.querySelector('#desktop-dialog').open, 'closed path settings');
    await evaluate(()=>toggleUILanguage());
    await evaluate(()=>toggleTheme());

    await click('#library-all-systems');
    assert.equal(await evaluate(() => document.querySelector('#library-all-systems').getAttribute('aria-pressed')), 'true');
    assert.equal(await evaluate(() => document.querySelector('#workspace-title').textContent), '游戏库');
    assert.equal(await evaluate(visible, '#game-library'), false);
    const playlistFiles = () => Object.fromEntries(fs.readdirSync(libraryPath + '/playlists')
        .filter(name => name.endsWith('.lpl'))
        .map(name => [name, fs.readFileSync(libraryPath + '/playlists/' + name)]));
    const beforeRun = playlistFiles();
    // The overview response replaces its action button. Start this cancellation
    // scenario after that read settles, rather than clicking a retiring node.
    await waitFor(() => !workbenchOverview.loading && !workbench.operation, 'settled overview before completion');
    await click('#overview-complete-button');
    await waitFor(() => batchRunJobId, 'all-systems run started');
    assert.equal(await evaluate(visible, '#completion-cancel'), true);
    await click('#completion-cancel');
    await waitFor(() => document.querySelector('#action-toast-text').textContent.includes('已取消'), 'cancelled completion toast');
    assert.deepEqual(playlistFiles(), beforeRun);
    await screenshot('02-all-systems-cancelled');
    await click('#action-toast-close');
    assert.equal(await evaluate(visible, '#game-library'), false);
    assert.equal(await evaluate(() => document.querySelector('#library-all-systems').getAttribute('aria-pressed')), 'true');
    await evaluate(() => { runAllSystemsCompletion(); });
    await waitFor(() => document.querySelector('#action-toast-text').textContent.startsWith('已补全'), 'completed all-systems toast');
    assert.equal(await evaluate(visible, '#action-toast-undo'), true);
    assert.equal(await evaluate(visible, '#action-toast-details'), true);
    await screenshot('02-all-systems-done');
    await waitFor(() => !workbench.operation, 'run finished before undo');
    await click('#action-toast-undo');
    await waitFor(() => document.querySelector('#action-toast-text').textContent.startsWith('已撤销'), 'all-systems undo applied');
    await waitFor(() => !workbench.operation, 'undo finished');
    assert.deepEqual(playlistFiles(), beforeRun);
    await click('#action-toast-details');
    await waitFor(() => document.querySelector('#desktop-dialog').open
        && document.querySelector('#desktop-content').textContent.includes('最近补全'), 'details opens recent completion history');
    await evaluate(() => [...document.querySelectorAll('#desktop-content h3')]
        .find(h => h.textContent === '最近补全')?.scrollIntoView({block: 'center'}));
    await screenshot('02-tasks-recent-completions');
    await click('#desktop-close');
    await evaluate(()=>toggleTheme());
    await evaluate(()=>toggleUILanguage());
    await evaluate(() => { runAllSystemsCompletion(); });
    await waitFor(() => document.querySelector('#action-toast-text').textContent.startsWith('Completed'), 'English all-systems toast');
    await screenshot('02-dark-en-all-systems-done');
    await waitFor(() => !workbench.operation, 'English run finished');
    await click('#action-toast-undo');
    await waitFor(() => document.querySelector('#action-toast-text').textContent === 'Undone', 'English undo restores');
    await waitFor(() => !workbench.operation, 'English undo finished');
    assert.deepEqual(playlistFiles(), beforeRun);
    await evaluate(()=>toggleUILanguage());
    await evaluate(()=>toggleTheme());
    await click(system);
    await waitFor(() => document.querySelector('#workspace-title')?.textContent.includes('SNES')
        && document.querySelector('#game-library')?.getAttribute('aria-busy') === 'false'
        && document.querySelector('.game-library-table tbody tr'), 'SNES reselected for preview');
    await evaluate(() => previewTask());
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
    assert.equal(await evaluate(() => document.querySelector('#preview-button').textContent), '重新预览');
    assert.equal(await evaluate(visible, '#completion-entry-note'), false);
    assert.equal(await evaluate(() => document.querySelector('#apply-button').textContent), '确认应用 1 项');
    assert.equal(await evaluate(visible, '#apply-summary-panel'), true);
    assert.equal(await evaluate(() => document.querySelector('#apply-summary-text').textContent.includes('修改名称 1 项')), true);
    assert.equal(await evaluate(() => document.querySelector('#confirm-apply-button')), null);
    assert.equal(await evaluate(() => document.querySelector('#preview-plan-scope').textContent.includes('保留游戏文件与单项核心')), true);
    assert.equal(await evaluate(() => document.querySelector('#preview-table-body .preview-identity').textContent), '精确名称匹配');
    assert.equal(await evaluate(() => {
        const label = document.querySelector('#preview-table-body .preview-identity');
        return label.getBoundingClientRect().bottom <= label.closest('td').getBoundingClientRect().bottom;
    }), true, 'identity evidence must fit within its table cell');
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
    await evaluate(() => document.querySelector('#choose-image-directory').click());
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
    await click('#workbench-device');
    await click('#scan-device-btn');
    await waitFor(() => document.querySelectorAll('.playlist-system-tab').length === 3
        && !document.querySelector('#library-all-systems').disabled, 'reopened library systems');
    await click(system);
    await waitFor(() => document.querySelector('#game-library')?.getAttribute('aria-busy') === 'false'
        && document.querySelector('.game-library-table tbody tr'), 'reopened library');
    assert.equal(await evaluate(() => document.querySelector('#thumbnails_override').value), override);
    assert.equal(await evaluate(visible, '#image-directory-notice'), false);

    const detected = path.join(libraryPath, 'thumbnails');
    fs.mkdirSync(detected);
    await click('#workbench-device');
    await evaluate(() => { const input = document.querySelector('#thumbnails_override'); input.focus(); input.select(); });
    await send('Input.dispatchKeyEvent', {type: 'keyDown', key: 'Backspace', code: 'Backspace', windowsVirtualKeyCode: 8});
    await send('Input.dispatchKeyEvent', {type: 'keyUp', key: 'Backspace', code: 'Backspace', windowsVirtualKeyCode: 8});
    await click('#scan-device-btn');
    await waitFor(dir => !document.querySelector('#desktop-dialog').open
        && currentDeviceScan?.directories?.thumbnails === dir
        && fetch('/api/config').then(r => r.json())
            .then(c => c.thumbnails_override === '' && c.thumbnails_dir === dir), 'detected artwork folder', detected);
    const config = await evaluate(async () => (await fetch('/api/config')).json());
    assert.equal(config.thumbnails_override, '');
    assert.equal(config.thumbnails_dir, detected);
    await click(system);
    await waitFor(() => document.querySelector('#workspace-title').textContent.includes('SNES')
        && document.querySelector('#game-library').getAttribute('aria-busy') === 'false'
        && document.querySelector('.game-library-table tbody tr'), 'SNES with artwork directory');
    assert.equal(await evaluate(visible, '#image-directory-notice'), false);
    assert.equal(await evaluate(() => document.querySelector('#game-library-rows .game-image-placeholder').getAttribute('aria-label')), '缺封面');
    assert.equal(await evaluate(() => document.querySelectorAll('#game-library-rows .artwork-chip').length), 0);
    await click('#game-view-list');
    await screenshot('04-auto-artwork');
    const boxFile = path.join(detected, 'Nintendo - Super Nintendo Entertainment System', 'Named_Boxarts', 'Shadowrun (USA).png');
    const boxBytes = Buffer.from(await evaluate(async () => Array.from(new Uint8Array(await (await fetch('/api/artwork/thumbnail?system=SNES&kind=Named_Boxarts&name=Game.png')).arrayBuffer()))));
    fs.mkdirSync(path.dirname(boxFile), {recursive:true});
    fs.writeFileSync(boxFile, boxBytes);
    await click(gba);
    await waitFor(() => document.querySelector('#game-library').getAttribute('aria-busy') === 'false', 'GBA before artwork reread');
    await click(system);
    await waitFor(() => document.querySelector('#game-library-rows img')?.naturalWidth > 0, 'list shows the available cover thumbnail');
    await screenshot('04-partial-artwork');
    const brokenFile = path.join(detected, 'Nintendo - Super Nintendo Entertainment System', 'Named_Snaps', 'Shadowrun (USA).png');
    fs.mkdirSync(path.dirname(brokenFile), {recursive:true});
    fs.writeFileSync(brokenFile, 'damaged test image');
    await click(gba);
    await waitFor(() => document.querySelector('#game-library').getAttribute('aria-busy') === 'false', 'GBA before damaged artwork reread');
    await click(system);
    await waitFor(() => gameLibrary.data?.items[0]?.artwork_status?.Named_Snaps === 'invalid', 'damaged artwork is detected');
    assert.equal(await evaluate(() => document.querySelector('#game-library-filter-problem').textContent.endsWith('1')), true);
    await screenshot('04-damaged-artwork');
    const snesPlaylistPath = libraryPath + '/playlists/Nintendo - Super Nintendo Entertainment System.lpl';
    const snesBefore = fs.readFileSync(snesPlaylistPath);
    await click('#games-complete-button');
    await waitFor(() => document.querySelector('#action-toast-text').textContent.startsWith('已补全'), 'direct single-system toast');
    assert.equal(await evaluate(visible, '#action-toast-undo'), true);
    await waitFor(() => !workbench.operation, 'direct run finished');
    assert.notDeepEqual(fs.readFileSync(snesPlaylistPath), snesBefore);
    await click('#action-toast-undo');
    await waitFor(() => document.querySelector('#action-toast-text').textContent.startsWith('已撤销'), 'single-system undo toast');
    await waitFor(() => !workbench.operation, 'single-system undo finished');
    assert.deepEqual(fs.readFileSync(snesPlaylistPath), snesBefore);
    await evaluate(() => previewTask());
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
    // A separate optical fixture exercises the real read-only group endpoint and dialog.
    const discRoot = path.join(libraryPath, 'disc-samples', 'RetroArch');
    const discLists = path.join(discRoot, 'playlists'), discRoms = path.join(discRoot, 'Roms');
    fs.mkdirSync(discLists, {recursive:true}); fs.mkdirSync(discRoms, {recursive:true});
    for (const name of ['GulliverBoy Disc1.chd','GulliverBoy Disc2.chd','Game (Disc 1).bin','Game (Disc 2).chd']) fs.writeFileSync(path.join(discRoms,name),'optical metadata test fixture');
    fs.writeFileSync(path.join(discRoms,'Game (Disc 1).cue'),'FILE "Game (Disc 1).bin" BINARY\n');
    fs.writeFileSync(path.join(discRoms,'Game.m3u'),'Game (Disc 2).chd\nGame (Disc 1).cue\n');
    const discPath = path.join(discLists,'Sega - Saturn.lpl');
    fs.writeFileSync(discPath,JSON.stringify({items:['GulliverBoy Disc1.chd','GulliverBoy Disc2.chd','Game.m3u'].map(name=>({path:path.join(discRoms,name),label:name,core_path:'/cores/mednafen_saturn_libretro.so'}))}));
    const discBefore = fs.readFileSync(discPath);
    const discSaves=path.join(discRoot,'saves'),discStates=path.join(discRoot,'states');fs.mkdirSync(discSaves);fs.mkdirSync(discStates);
    fs.writeFileSync(path.join(discRoot,'retroarch.cfg'),
        `savefile_directory = "${discSaves.replaceAll('\\','/')}"\nsavestate_directory = "${discStates.replaceAll('\\','/')}"\nauto_overrides_enable = "false"\ngame_specific_options = "false"\ncore_options_path = "${path.join(discRoot,'core-options.cfg').replaceAll('\\','/')}"\n`);

    await click('#workbench-device');
    await evaluate(root=>{const input=document.querySelector('#retroarch_root');input.value=root;input.dispatchEvent(new Event('input',{bubbles:true}));},discRoot);
    await click('#scan-device-btn');
    await waitFor(()=>!document.querySelector('#desktop-dialog').open && document.querySelectorAll('.playlist-system-tab').length===2,'optical fixture loaded');
    await click('.playlist-system-tab[aria-label="Sega - Saturn"]');
    await waitFor(()=>!document.querySelector('#game-library-discs').disabled,'optical inspection available');
    await click('#game-library-discs');
    await waitFor(()=>document.querySelectorAll('#disc-inspection-groups > details').length===2,'two optical groups');
    assert.equal(await evaluate(()=>document.querySelector('#disc-inspection-summary').textContent.includes('4 张光盘')),true);
    assert.equal(await evaluate(()=>document.querySelector('#disc-inspection-summary').textContent.includes('原列表 3 个入口')),true);
    await click('#disc-inspection-groups > details summary');
    await waitFor(()=>document.querySelectorAll('#disc-inspection-groups .disc-members li').length===2,'disc details expanded');
    await screenshot('07-disc-inspection');
    await click('#disc-inspection-close');
    assert.deepEqual(fs.readFileSync(discPath),discBefore,'inspection must not write the playlist');
    await evaluate(()=>toggleTheme());
    await click('#game-library-discs');
    await waitFor(()=>document.querySelectorAll('#disc-inspection-groups > details').length===2,'optical groups reopened');
    await evaluate(()=>document.querySelector('#disc-inspection-search').focus());
    await send('Input.insertText',{text:'Gulliver'});
    await waitFor(()=>document.querySelectorAll('#disc-inspection-groups > details').length===1,'group search by file');
    await click('#disc-inspection-groups > details summary');
    await waitFor(()=>document.querySelectorAll('#disc-inspection-groups .disc-members li').length===2,'candidate details expanded');
    assert.equal(await evaluate(()=>document.querySelector('#disc-inspection-groups').textContent.includes('候选组')),true);
    await screenshot('07-disc-inspection-dark');
    const originalGameId=await evaluate(()=>discInspection.data.entries[0].game_id);
    await click('#disc-inspection-groups .disc-group-body > button');
    await waitFor(visible,'M3U editor','#m3u-dialog');
    await click('#m3u-discs li:first-child button:last-child');
    await evaluate(()=>{const field=document.querySelector('#m3u-label');field.focus();field.select();});
    await send('Input.insertText',{text:'空想科学世界'});
    const m3uName=await evaluate(()=>document.querySelector('#m3u-filename').value);
    await click('#m3u-preview');
    await waitFor(()=>!document.querySelector('#m3u-apply').disabled,'ready M3U plan');
    assert.equal(await evaluate(()=>document.querySelector('#m3u-content').textContent),'GulliverBoy Disc2.chd\nGulliverBoy Disc1.chd\n');
    assert.deepEqual(fs.readFileSync(discPath),discBefore,'preview does not write');
    await screenshot('08-m3u-plan');
    await click('#m3u-apply');
    await waitFor(()=>!document.querySelector('#m3u-close').disabled && document.querySelector('#m3u-status').textContent.includes('已完成'),'M3U applied');
    assert.equal(JSON.parse(fs.readFileSync(discPath,'utf8')).items.length,2);
    assert.equal(fs.readFileSync(path.join(discRoms,m3uName),'utf8'),'GulliverBoy Disc2.chd\nGulliverBoy Disc1.chd\n');
    await screenshot('08-m3u-applied');
    holdRecent = true;
    await click('#m3u-close');
    for(let attempt=0;!heldRecent&&attempt<150;attempt++)await delay(100);
    assert.ok(heldRecent, 'scan is waiting to save the opened library');
    assert.equal(await evaluate(() => workbench.operation), 'scan');
    assert.equal(await evaluate(() => [...document.querySelectorAll('#scanned-playlists button')].every(button => button.disabled)), true,
        'Rebuilt navigation stays disabled until the scan finishes');
    holdRecent = false;
    await send('Fetch.continueRequest', {requestId:heldRecent});
    heldRecent = null;
    await waitFor(()=>!document.querySelector('#m3u-dialog').open && !document.querySelector('#disc-inspection-dialog').open && !document.querySelector('#library-all-systems').disabled,'library refreshed after M3U');
    await click('.playlist-system-tab[aria-label="Sega - Saturn"]');
    await waitFor(()=>gameLibrary.data?.items.length===2,'two launch entries after grouping');
    assert.equal(await evaluate(()=>gameLibrary.data.items[0].game_id),originalGameId);
    await click('#game-library-discs');await click('#disc-inspection-close-history');
    await waitFor(()=>document.querySelector('[data-m3u-operation] button'),'durable M3U history');
    await click('[data-m3u-operation] button');
    await click('.desktop-confirm button:last-of-type');
    await waitFor(()=>document.querySelector('[data-m3u-operation] strong')?.textContent.includes('已恢复'),'M3U restored');
    assert.deepEqual(fs.readFileSync(discPath),discBefore);
    assert.equal(fs.existsSync(path.join(discRoms,m3uName)),false);
    await waitFor(()=>gameLibrary.data?.items.length===3,'restored library cache refreshed');
    await screenshot('08-m3u-restored');
    await click('#desktop-close');
    await click('#disc-inspection-close');
    await evaluate(()=>toggleTheme());
    await click('#game-library-discs');
    await waitFor(()=>document.querySelectorAll('#disc-inspection-groups > details').length===2,'restored groups inspected');
    await click('#disc-inspection-groups > details:last-child summary');
    await waitFor(()=>document.querySelector('#disc-inspection-groups > details:last-child .disc-group-body > button'),'restored candidate action');
    await click('#disc-inspection-groups > details:last-child .disc-group-body > button');
    await screenshot('08-m3u-editor-light');
    await click('#m3u-close');
    await click('#disc-inspection-close');


    assert.deepEqual(fs.readFileSync(discPath),discBefore);

    // Synthetic optical sectors exercise local CHD copy conversion through the real APIs.
    const rawTrack=path.join(discRoms,'Game (Disc 1).bin'),rawCue=path.join(discRoms,'Game (Disc 1).cue');
    fs.writeFileSync(rawTrack,Buffer.alloc(2352*100));
    fs.writeFileSync(rawCue,'FILE "Game (Disc 1).bin" BINARY\n TRACK 01 MODE1/2352\n INDEX 01 00:00:00\n');
    const rawBefore=fs.readFileSync(rawTrack),cueBefore=fs.readFileSync(rawCue);
    if (!await evaluate(() => document.querySelector('.tools-menu').open)) await click('.tools-menu > summary');
    await click('#storage-entry');
    await evaluate(directory=>{const input=document.querySelector('#storage-workspace');input.value=directory;input.dispatchEvent(new Event('input',{bubbles:true}));},discRoot);
    await click('#storage-analyze');
    await waitFor(()=>!storageTask.busy&&!document.querySelector('#storage-analysis').hidden,'CHD analysis displayed');
    assert.equal(await evaluate(()=>document.querySelectorAll('#storage-rows input:checked').length),1);
    await screenshot('09-chd-analysis-light');
    const canConvert=await evaluate(()=>!document.querySelector('#storage-convert').disabled);
    if(process.env.RETROARCH_ASSISTANT_REQUIRE_CHD==='1')assert.equal(canConvert,true,'Required real chdman must be available');
    if(canConvert){
        await click('#storage-convert');
        await waitFor(()=>!storageTask.busy&&!document.querySelector('#storage-result').hidden,'CHD conversion result');
        assert.equal(await evaluate(()=>document.querySelector('#storage-result').textContent.includes('内容已比对')),true);
        const state=await evaluate(async()=>(await fetch('/api/desktop')).json());
        const operation=state.chd_operations[0];assert.equal(operation.status,'completed');
        assert.equal(fs.existsSync(operation.results[0].output),true);
        assert.equal(operation.results[0].runtime_status,'not_tested');
        await screenshot('09-chd-verified');
    }
    assert.deepEqual(fs.readFileSync(discPath),discBefore,'CHD copy conversion does not change playlist');
    assert.deepEqual(fs.readFileSync(rawTrack),rawBefore);assert.deepEqual(fs.readFileSync(rawCue),cueBefore);
    await click('#storage-close');await evaluate(()=>toggleTheme());if (!await evaluate(() => document.querySelector('.tools-menu').open)) await click('.tools-menu > summary');
    await click('#storage-entry');await click('#storage-analyze');
    await waitFor(()=>!storageTask.busy&&!document.querySelector('#storage-analysis').hidden,'dark CHD analysis');
    await screenshot('09-chd-analysis-dark');
    if(!canConvert) await click('#storage-close');

    if(canConvert){
        const originalM3u=fs.readFileSync(path.join(discRoms,'Game.m3u'));
        assert.equal(await evaluate(()=>document.querySelector('#storage-close-history')),null);
        await evaluate(()=>openOperationHistory('chd'));
        await waitFor(()=>document.querySelector('[data-chd-operation]'),'CHD durable history');
        await screenshot('09-chd-history');
        await click('[data-chd-operation] button');
        await waitFor(()=>document.querySelector('#deploy-dialog').open,'deployment dialog');
        assert.equal(await evaluate(()=>document.querySelector('#deploy-mode').value),'copy');
        await click('#deploy-preview');await waitFor(()=>!document.querySelector('#deploy-apply').disabled,'copy preview ready');
        assert.deepEqual(fs.readFileSync(rawCue),cueBefore);await screenshot('10-chd-copy-preview');
        await click('#deploy-settings > summary');
        await evaluate(()=>{const mode=document.querySelector('#deploy-mode');mode.value='replace';mode.dispatchEvent(new Event('input',{bubbles:true}));});
        await click('#deploy-runtime summary');
        await evaluate(()=>{const version=document.querySelector('#deploy-version');version.value='synthetic browser fixture';version.dispatchEvent(new Event('input',{bubbles:true}));});
        await click('#deploy-tested');await click('#deploy-scope');
        await click('#deploy-preview');await waitFor(()=>!document.querySelector('#deploy-apply').disabled,'replacement preview ready');
        await screenshot('10-chd-replace-preview');
        await click('#deploy-apply');await waitFor(()=>!chdDeployment.busy&&document.querySelector('#deploy-status').textContent.includes('已完成'),'deployment completed');
        assert.equal(fs.existsSync(rawCue),false);assert.equal(fs.existsSync(rawTrack),false);
        assert.equal(fs.existsSync(path.join(discRoms,'Game (Disc 1).chd')),true);
        assert.equal(fs.readFileSync(path.join(discRoms,'Game.m3u'),'utf8').includes('Game (Disc 1).chd'),true);
        await screenshot('10-chd-deployed');
        await click('#deploy-close-history');await waitFor(()=>document.querySelector('[data-chd-deployment]'),'deployment receipt displayed');
        await click('[data-chd-deployment] button');await click('.desktop-confirm button:last-of-type');
        await waitFor(()=>document.querySelector('[data-chd-deployment] strong').textContent.includes('已恢复'),'deployment restored');
        assert.deepEqual(fs.readFileSync(rawCue),cueBefore);assert.deepEqual(fs.readFileSync(rawTrack),rawBefore);
        assert.deepEqual(fs.readFileSync(path.join(discRoms,'Game.m3u')),originalM3u);
        assert.equal(fs.existsSync(path.join(discRoms,'Game (Disc 1).chd')),false);
        await screenshot('10-chd-restored');await click('#desktop-close');await click('#deploy-close');
    }

    // Cartridge directory analysis and real ZIP generation: separate synthetic library.
    const cartRoot=path.join(libraryPath,'rom-samples','RetroArch'),cartLists=path.join(cartRoot,'playlists'),cartRoms=path.join(cartRoot,'Roms');
    fs.mkdirSync(cartLists,{recursive:true});fs.mkdirSync(cartRoms,{recursive:true});
    const cartPaths=[];
    for(const [folder,name] of [['one','同名游戏.gba'],['two','同名游戏.gba'],['three','独立游戏.gba']]){
        const directory=path.join(cartRoms,folder);fs.mkdirSync(directory);const file=path.join(directory,name);fs.writeFileSync(file,Buffer.alloc(100000,cartPaths.length));cartPaths.push(file);
    }
    fs.writeFileSync(path.join(cartRoms,'multi.cue'),'FILE "data.bin" BINARY\n');
    const cartPlaylist=path.join(cartLists,'Nintendo - Game Boy Advance.lpl');
    fs.writeFileSync(cartPlaylist,JSON.stringify({items:cartPaths.map(file=>({path:file,label:path.basename(file),core_path:'/cores/mgba_libretro.so'}))}));
    const cartBefore=fs.readFileSync(cartPlaylist),sourceBefore=cartPaths.map(file=>fs.readFileSync(file));
    await click('#workbench-device');
    await evaluate(root=>{const input=document.querySelector('#retroarch_root');input.value=root;input.dispatchEvent(new Event('input',{bubbles:true}));},cartRoot);
    await click('#scan-device-btn');await waitFor(()=>!document.querySelector('#desktop-dialog').open&&document.querySelector('.playlist-system-tab[aria-label="Nintendo - Game Boy Advance"]'),'cartridge library loaded');
    await click('.playlist-system-tab[aria-label="Nintendo - Game Boy Advance"]');
    if(await evaluate(()=>document.body.dataset.theme==='dark'))await evaluate(()=>toggleTheme());
    if (!await evaluate(() => document.querySelector('.tools-menu').open)) await click('.tools-menu > summary');
    await click('#rom-storage-entry');
    await click('#rom-storage-fields > label:first-of-type button');
    await waitFor(()=>document.querySelector('#rom-storage-source').value.length>0,'native picker returned source');
    await evaluate(directory=>{const input=document.querySelector('#rom-storage-workspace');input.value=directory;input.dispatchEvent(new Event('input',{bubbles:true}));},cartRoot);
    await click('#rom-storage-analyze');
    await waitFor(()=>!romStorage.busy&&!document.querySelector('#rom-storage-analysis').hidden,'directory and cartridge ZIP analysis');
    assert.equal(await evaluate(()=>document.querySelectorAll('#rom-storage-rows [data-layout="conflict"]').length),2);
    assert.equal(await evaluate(()=>document.querySelectorAll('#rom-storage-rows [data-layout="keep"]').length),1);
    assert.equal(await evaluate(()=>document.querySelectorAll('#rom-storage-rows input:checked').length),3);
    await evaluate(()=>document.querySelector('#rom-storage-dialog').scrollTop=0);await screenshot('11-rom-layout-light');
    await click('#rom-storage-convert');await waitFor(()=>!romStorage.busy&&!document.querySelector('#rom-storage-result').hidden,'ZIP computer copies completed');
    assert.deepEqual(fs.readFileSync(cartPlaylist),cartBefore);
    for(let index=0;index<cartPaths.length;index++)assert.deepEqual(fs.readFileSync(cartPaths[index]),sourceBefore[index]);
    const romHistory=await evaluate(async()=> (await (await fetch('/api/desktop')).json()).rom_storage_operations);
    assert.equal(romHistory[0].results.length,3);assert.equal(romHistory[0].device_saved_bytes,0);
    assert.equal(new Set(romHistory[0].results.map(row=>row.output)).size,3);
    assert.equal(romHistory[0].results.every(row=>row.verification==='byte_for_byte'&&fs.existsSync(row.output)),true);
    await screenshot('11-rom-zip-result');await click('#rom-storage-close');
    await evaluate(()=>toggleTheme());if (!await evaluate(() => document.querySelector('.tools-menu').open)) await click('.tools-menu > summary');
    await click('#rom-storage-entry');
    await click('#rom-storage-fields > label:first-of-type button');
    await waitFor(()=>document.querySelector('#rom-storage-source').value.length>0,'source reopened');
    await click('#rom-storage-analyze');await waitFor(()=>!romStorage.busy&&!document.querySelector('#rom-storage-analysis').hidden,'dark directory analysis');
    await evaluate(()=>document.querySelector('#rom-storage-dialog').scrollTop=0);await screenshot('11-rom-layout-dark');
    assert.equal(await evaluate(()=>document.querySelector('#rom-storage-close-history')),null);
    await evaluate(()=>openOperationHistory('romStorage'));await waitFor(()=>document.querySelector('[data-rom-storage-operation]'),'ZIP durable history');
    await screenshot('11-rom-zip-history');await click('#desktop-close');await click('#rom-storage-close');

    // Stage 4B: move a synthetic CHD-only multi-disc set, then restore both operations.
    const layoutRoot=path.join(libraryPath,'layout-samples','RetroArch'),layoutLists=path.join(layoutRoot,'playlists'),layoutRoms=path.join(layoutRoot,'Roms'),layoutNested=path.join(layoutRoms,'多盘游戏');
    for(const directory of [layoutLists,layoutNested,path.join(layoutRoot,'saves'),path.join(layoutRoot,'states')])fs.mkdirSync(directory,{recursive:true});
    const layoutDiscs=['多盘 (Disc 1).chd','多盘 (Disc 2).chd'].map(name=>path.join(layoutNested,name)),layoutM3u=path.join(layoutNested,'多盘.m3u');
    for(const file of layoutDiscs)fs.writeFileSync(file,'synthetic move fixture '+path.basename(file));
    fs.writeFileSync(layoutM3u,layoutDiscs.map(file=>path.basename(file)).join('\n')+'\n');
    const layoutPlaylist=path.join(layoutLists,'Sega - Saturn.lpl');
    fs.writeFileSync(layoutPlaylist,JSON.stringify({items:[{path:layoutM3u,label:'人工多盘名',core_path:'/cores/mednafen_saturn_libretro.so',custom:'keep'}]}));
    const flags=['auto_overrides_enable','game_specific_options','sort_savefiles_enable','sort_savefiles_by_content_enable','savefiles_in_content_dir','sort_savestates_enable','sort_savestates_by_content_enable','savestates_in_content_dir'];
    fs.writeFileSync(path.join(layoutRoot,'core-options.cfg'),'');
    fs.writeFileSync(path.join(layoutRoot,'retroarch.cfg'),flags.map(key=>key+' = "false"').join('\n')+'\n'+
        'savefile_directory = "'+path.join(layoutRoot,'saves').replaceAll('\\','/')+'"\n'+
        'savestate_directory = "'+path.join(layoutRoot,'states').replaceAll('\\','/')+'"\n'+
        'core_options_path = "'+path.join(layoutRoot,'core-options.cfg').replaceAll('\\','/')+'"\n');
    const layoutBefore=new Map([layoutPlaylist,layoutM3u,...layoutDiscs].map(file=>[file,fs.readFileSync(file)]));
    await click('#workbench-device');await evaluate(root=>{const input=document.querySelector('#retroarch_root');input.value=root;input.dispatchEvent(new Event('input',{bubbles:true}));},layoutRoot);
    await click('#scan-device-btn');await waitFor(()=>!document.querySelector('#desktop-dialog').open&&document.querySelector('.playlist-system-tab[aria-label="Sega - Saturn"]'),'layout library loaded');
    await click('.playlist-system-tab[aria-label="Sega - Saturn"]');
    if(Number(width)>1100&&await evaluate(()=>document.body.dataset.theme==='dark'))await evaluate(()=>toggleTheme());
    if (!await evaluate(() => document.querySelector('.tools-menu').open)) await click('.tools-menu > summary');
    await click('#rom-storage-entry');await evaluate(root=>document.querySelector('#rom-storage-source').value=root,layoutRoms);
    await click('#rom-storage-fields > label:first-of-type button');
    await waitFor(()=>document.querySelector('#rom-storage-target').value.length>0,'layout picker selected');
    await evaluate(root=>{const input=document.querySelector('#rom-storage-workspace');input.value=root;input.dispatchEvent(new Event('input',{bubbles:true}));},layoutRoot);
    await click('#rom-storage-analyze');await waitFor(()=>!romStorage.busy&&!document.querySelector('#rom-storage-analysis').hidden,'CHD and M3U layout analyzed');
    assert.equal(await evaluate(()=>document.querySelectorAll('#rom-storage-rows input:checked').length),3);
    assert.equal(await evaluate(()=>document.querySelector('#rom-storage-convert').disabled),true);
    await click('#rom-storage-relocate');await click('#relocate-preview');await waitFor(()=>!document.querySelector('#relocate-apply').disabled,'layout copy preview');
    for(const [file,bytes] of layoutBefore)assert.deepEqual(fs.readFileSync(file),bytes);
    await screenshot('12-layout-copy-preview');await click('#relocate-apply');
    await waitFor(()=>!romRelocation.busy&&document.querySelector('#relocate-status').textContent.includes('已完成'),'copy completed');
    const copies=await evaluate(async()=> (await (await fetch('/api/desktop')).json()).rom_relocations);const copyId=copies[0].id;
    assert.equal(copies[0].mode,'copy');for(const file of [layoutM3u,...layoutDiscs])assert.equal(fs.existsSync(file),true);
    await click('#relocate-settings > summary');
    await evaluate(()=>{const input=document.querySelector('#relocate-mode');input.value='replace';input.dispatchEvent(new Event('input',{bubbles:true}));});
    await evaluate(()=>{const input=document.querySelector('#relocate-version');input.value='synthetic browser fixture';input.dispatchEvent(new Event('input',{bubbles:true}));});
    await click('#relocate-tested');await click('#relocate-scope');await click('#relocate-preview');
    await waitFor(()=>!document.querySelector('#relocate-apply').disabled,'layout move preview ready');await screenshot('12-layout-move-preview');
    await click('#relocate-apply');await waitFor(()=>!romRelocation.busy&&document.querySelector('#relocate-status').textContent.includes('已完成'),'layout move completed');
    const moves=await evaluate(async()=> (await (await fetch('/api/desktop')).json()).rom_relocations);const moveId=moves.find(row=>row.mode==='replace').id;
    for(const file of [layoutM3u,...layoutDiscs])assert.equal(fs.existsSync(file),false);
    assert.equal(fs.readFileSync(path.join(layoutRoms,'多盘.m3u'),'utf8'),layoutDiscs.map(file=>path.basename(file)).join('\n')+'\n');
    assert.equal(JSON.parse(fs.readFileSync(layoutPlaylist,'utf8')).items[0].path.replaceAll('\\','/'),path.join(layoutRoms,'多盘.m3u').replaceAll('\\','/'));
    await screenshot('12-layout-moved');
    await click('#relocate-close-history');
    await waitFor(id=>document.querySelector('[data-rom-relocation="'+id+'"]'),'layout move receipt',moveId);
    if(await evaluate(()=>workbench.operation))await waitFor(()=>!workbench.operation,'background scan finished');
    await evaluate(()=>beginWorkbenchOperation('scan'));
    assert.equal(await evaluate(id=>document.querySelector('[data-rom-relocation="'+id+'"] button').disabled,moveId),true,'idle-gated while operation active');
    await evaluate(()=>endWorkbenchOperation());
    assert.equal(await evaluate(id=>document.querySelector('[data-rom-relocation="'+id+'"] button').disabled,moveId),false,'idle-gated re-enabled');
    await click('[data-rom-relocation="'+moveId+'"] button');await click('.desktop-confirm button:last-of-type');
    await waitFor(id=>document.querySelector('[data-rom-relocation="'+id+'"] strong').textContent.includes('已恢复'),'move restored',moveId);
    await click('[data-rom-relocation="'+copyId+'"] button');await click('.desktop-confirm button:last-of-type');
    await waitFor(id=>document.querySelector('[data-rom-relocation="'+id+'"] strong').textContent.includes('已恢复'),'copy restored',copyId);
    for(const [file,bytes] of layoutBefore)assert.deepEqual(fs.readFileSync(file),bytes);
    for(const file of [layoutM3u,...layoutDiscs])assert.equal(fs.existsSync(path.join(layoutRoms,path.basename(file))),false);
    await screenshot('12-layout-restored');await click('#desktop-close');await click('#relocate-close');

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
            fs.writeFileSync(path.join(output, 'failure-state.json'), JSON.stringify(await evaluate(() => ({
                operation:workbench.operation, previewScope:workbench.previewScope,
                playlist:document.getElementById('playlist_path').value,
                directories:currentDeviceScan?.directories, batchJob:batchRunJobId,
                workspaceOpen:gameManagement.open
            })), null, 2));
        } catch (diagnosticError) {
            console.error('Could not capture browser diagnostics:', diagnosticError.message);
        }
    }
    process.exitCode = 1;
}).finally(() => socket.close());
