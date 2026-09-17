/* This dialog owns one immutable game context, separate from repair selections. */
let artworkDialogState = null;
const artworkElement = id => document.getElementById('artwork-' + id);

function openArtworkDialog(item, autoSearch = true) {
    if (workbench.operation) return;
    const [playlist_path, system, thumbnails] = gameLibraryInput();
    if (!thumbnails) { openPathSettings(); return; }
    const key = JSON.stringify(gameLibraryInput());
    artworkDialogState = {context: {playlist_path, system, thumbnails, index: item.index, label: item.label, rom_path: item.rom_path},
        key, version: 0, candidate: null, busy: false, searching: false, applying: false, jobId: null, returnFocus: document.activeElement};
    if (!beginWorkbenchOperation('artwork')) { artworkDialogState = null; return; }
    const text = workbenchText;
    artworkElement('title').textContent = item.image_url ? text('更换游戏图片', 'Replace game artwork') : text('为这个游戏补图', 'Add artwork for this game');
    artworkElement('game').textContent = item.label;
    artworkElement('shared').hidden = true;
    artworkElement('new-label').value = '';
    artworkElement('scope').textContent = text('更新这个游戏的一种图片，可同时修改名称。更换已有图片时会备份旧图。', 'Update one artwork type for this game, with an optional name change. Replaced images are backed up.');
    artworkElement('close').textContent = text('关闭', 'Close');
    artworkElement('kind-label').textContent = text('图片类型', 'Image type');
    Array.from(artworkElement('kind').options).forEach((option, i) => { option.textContent = text(['封面', '游戏截图', '标题图'][i], ['Box art', 'Screenshot', 'Title screen'][i]); });
    artworkElement('kind').value = 'Named_Boxarts';
    artworkElement('source-label').textContent = text('搜索官方图库', 'Search official artwork library');
    artworkElement('source').placeholder = text('输入英文游戏名搜索图库', 'Search the library by English game name');
    artworkElement('source').value = '';
    artworkElement('search').textContent = text('搜索图库', 'Search library');
    artworkElement('preview').textContent = text('预览图片', 'Preview image');
    artworkElement('upload-label').textContent = text('或导入本地图片（PNG / JPEG / WebP，最多 12 MiB）', 'Or import a local image (PNG / JPEG / WebP, up to 12 MiB)');
    artworkElement('upload').value = '';
    artworkElement('message').textContent = '';
    artworkElement('results').replaceChildren();
    artworkElement('confirm').textContent = text('确认', 'Confirm');
    invalidateArtworkCandidate();
    artworkElement('dialog').showModal();
    artworkElement('source').focus();
    artworkElement('identity').textContent = '';
    artworkElement('names').replaceChildren();
    artworkElement('current-label').textContent = text('当前图片', 'Current image');
    artworkElement('candidate-label').textContent = text('候选图片', 'Candidate image');
    if (autoSearch) return discoverArtwork();
}

function currentArtworkRequest(state, version) {
    return artworkDialogState === state && state.version === version && state.key === JSON.stringify(gameLibraryInput());
}

function invalidateArtworkCandidate() {
    const state = artworkDialogState;
    if (!state || state.applying) return;
    state.version++;
    state.candidate = null;
    state.searching = false;
    state.jobId = null;
    artworkElement('candidate').hidden = true;
    artworkElement('comparison').hidden = true;
    artworkElement('confirm').disabled = true;
    artworkElement('results').replaceChildren();
    artworkElement('message').textContent = '';
}

function artworkBusy(busy) {
    const state = artworkDialogState;
    if (!state) return;
    state.busy = busy;
    for (const id of ['kind', 'source', 'search', 'preview', 'upload', 'new-label']) artworkElement(id).disabled = busy || Boolean(state.jobId);
    artworkElement('results').inert = busy || Boolean(state.jobId);
    artworkElement('close').disabled = state.applying || Boolean(state.jobId);
    artworkElement('confirm').disabled = busy || !state.candidate;
    artworkElement('confirm').textContent = state.applying ? workbenchText('更新中…', 'Updating…')
        : state.jobId ? workbenchText('查询更新结果', 'Check update result') : workbenchText('确认', 'Confirm');
}

function artworkSearchChanged() {
    invalidateArtworkCandidate();
    artworkElement('names').replaceChildren();
    artworkElement('identity').textContent = workbenchText('已修改搜索词，请搜索官方图库。', 'Search term changed. Search the official library.');
}

async function discoverArtwork() {
    const state = artworkDialogState;
    if (!state || state.busy || state.jobId) return;
    invalidateArtworkCandidate();
    const version = state.version;
    state.searching = true;
    artworkElement('names').replaceChildren();
    artworkElement('identity').textContent = workbenchText('正在识别英文名…', 'Identifying the English title…');
    try {
        if (!state.entryInfo) {
            const entryInfo = await desktopRequest('/api/artwork/context', state.context);
            if (!currentArtworkRequest(state, version)) return;
            state.entryInfo = entryInfo;
            artworkElement('shared').hidden = false;
            artworkElement('shared-games').replaceChildren();
            artworkElement('new-label-title').textContent = workbenchText('游戏名称', 'Game name');
            artworkElement('new-label').value = state.context.label;
            artworkElement('shared-message').textContent = workbenchText('当前 ROM：', 'Current ROM: ') + (state.context.rom_path.split('/').pop());
            artworkElement('shared-help').textContent = workbenchText('可同时修改游戏名称；改名会备份游戏列表。图片更新会同步已有的 ROM 文件名图片。', 'You can also rename this game; the playlist is backed up. Existing ROM-named artwork is updated too.');
            if (state.entryInfo.shared?.length) {
                artworkElement('shared-message').textContent = workbenchText('以下条目共用同一个图片名称，请先核对当前 ROM：', 'These entries share an artwork name. Check the selected ROM:');
                artworkElement('shared-games').replaceChildren();
                for (const entry of state.entryInfo.shared) {
                    const row = document.createElement('li');
                    row.textContent = (entry.index === state.context.index ? workbenchText('当前：', 'Selected: ') : '') + entry.rom_name;
                    artworkElement('shared-games').appendChild(row);
                }
                artworkElement('new-label-title').textContent = workbenchText('当前游戏的独立名称', 'Independent name for this game');
                artworkElement('new-label').value = state.entryInfo.suggested_label;
                artworkElement('scope').textContent = workbenchText('确认后只修改当前条目的名称并保存独立图片；原共用图片继续供其他条目使用。', 'Confirm to rename this entry and save independent artwork. Other entries keep the shared image.');
                artworkElement('shared-help').textContent = workbenchText('建议名称取自 ROM 文件名，可修改。请核对英文名与游戏版本；其他类型图片会复制保留，游戏列表会备份。', 'The suggested name comes from the ROM filename and is editable. Check the English title and game version. Other artwork types are copied and the playlist is backed up.');
            }
        }
        const lookup = {...state.context, kind: artworkElement('kind').value};
        if (state.entryInfo) lookup.label = artworkElement('new-label').value;
        const result = await desktopRequest('/api/artwork/resolve', lookup);
        if (!currentArtworkRequest(state, version)) return;
        const reasons = {remembered: ['上次确认的图片源', 'Previously confirmed source'], confirmed: ['人工确认的名称', 'Confirmed name'],
            curated: ['已知名称', 'Known title'], rom_alias: ['从 ROM 名称识别，请核对候选图片', 'From the ROM name; review the candidate artwork'], database: ['名称库匹配', 'Name catalog match'], alias: ['名称别名匹配', 'Name alias match'], filename: ['从 ROM 名称提取', 'From the ROM title']};
        if (result.status === 'resolved') {
            artworkElement('source').value = result.query;
            const reason = reasons[result.reason] || ['识别名称', 'Identified title'];
            artworkElement('identity').textContent = workbenchText(...reason) + '：' + result.query;
            await searchArtwork(true);
        } else if (result.status === 'ambiguous') {
            artworkElement('identity').textContent = workbenchText('找到多个可能的名称，请选择游戏后搜索。', 'Several possible titles found. Choose the game to search.');
            for (const name of result.names) {
                const button = document.createElement('button');
                button.className = 'btn btn-muted'; button.type = 'button'; button.textContent = name;
                button.onclick = () => { artworkElement('source').value = name; artworkElement('names').replaceChildren(); searchArtwork(true); };
                artworkElement('names').appendChild(button);
            }
        } else {
            artworkElement('identity').textContent = workbenchText('尚未识别英文名。请输入英文游戏名搜索，或导入本地图片。', 'English title not identified. Enter a title to search or import an image.');
        }
    } catch (error) {
        if (currentArtworkRequest(state, version)) artworkElement('identity').textContent = workbenchText('名称识别失败：', 'Title lookup failed: ') + error.message;
    } finally { if (currentArtworkRequest(state, version)) state.searching = false; }
}

async function searchArtwork(automatic = false) {
    const state = artworkDialogState;
    if (!state || state.busy || state.jobId) return;
    invalidateArtworkCandidate();
    const query = artworkElement('source').value.trim();
    if (query.length < 2) {
        artworkElement('message').textContent = workbenchText('请输入至少两个字符的游戏名称，再搜索图库。', 'Enter a game title with at least two characters before searching.');
        artworkElement('source').focus();
        return;
    }
    const version = state.version;
    state.searching = true;
    artworkElement('message').textContent = workbenchText('正在搜索官方图库，可随时导入本地图片…', 'Searching the official library. You can import an image at any time…');
    try {
        const result = await desktopRequest('/api/artwork/search', {system: state.context.system, kind: artworkElement('kind').value, query, automatic});
        if (!currentArtworkRequest(state, version)) return;
        artworkElement('message').textContent = result.total
            ? workbenchText(`找到 ${result.total} 张候选图片，显示前 ${result.names.length} 张。选择图片查看对比。`, `Found ${result.total} images; showing ${result.names.length}. Select one to compare.`)
            : workbenchText('官方图库暂无匹配图片。可修改英文名重新搜索，或导入本地图片。', 'No matching official artwork. Edit the English title to search again, or import an image.');
        for (const candidate of result.candidates || result.names.map(name => ({name}))) {
            const button = document.createElement('button');
            button.className = 'btn btn-muted artwork-option'; button.type = 'button';
            if (candidate.image_url) {
                const image = document.createElement('img'); image.loading = 'lazy'; image.alt = candidate.name;
                const unavailable = document.createElement('span'); unavailable.hidden = true;
                unavailable.textContent = workbenchText('缩略图加载失败，点击重试预览', 'Thumbnail unavailable. Select to retry preview.');
                image.onerror = () => { image.hidden = true; unavailable.hidden = false; };
                image.src = candidate.image_url;
                button.appendChild(image); button.appendChild(unavailable);
            }
            const title = document.createElement('span'); title.textContent = candidate.name;
            button.appendChild(title);
            if (candidate.exact) {
                const badge = document.createElement('small'); badge.textContent = workbenchText('完整名称匹配', 'Exact title match'); button.appendChild(badge);
            }
            button.onclick = () => { artworkElement('source').value = candidate.name; previewArtwork(); };
            artworkElement('results').appendChild(button);
        }
    } catch (error) {
        if (currentArtworkRequest(state, version)) artworkElement('message').textContent = workbenchText('图库搜索失败，可点击“搜索图库”重试：', 'Library search failed. Select Search library to retry: ') + error.message;
    } finally { if (currentArtworkRequest(state, version)) state.searching = false; }
}

async function previewArtwork(upload = null, pendingState = artworkDialogState) {
    const state = artworkDialogState;
    if (!state || state !== pendingState || state.busy) return;
    invalidateArtworkCandidate();
    if (!upload && !artworkElement('source').value.trim()) {
        artworkElement('message').textContent = workbenchText('请先搜索并选择候选图片，或导入本地图片。', 'Search and select a candidate image, or import a local image first.');
        artworkElement('source').focus();
        return;
    }
    const version = state.version;
    artworkBusy(true);
    artworkElement('message').textContent = workbenchText('正在准备候选图片…', 'Preparing the candidate image…');
    try {
        const result = await desktopRequest('/api/artwork/preview', {...state.context, kind: artworkElement('kind').value,
            ...(state.entryInfo ? {new_label: artworkElement('new-label').value.trim()} : {}),
            ...(upload || {source: artworkElement('source').value})});
        if (!currentArtworkRequest(state, version)) return;
        const image = artworkElement('candidate-image');
        image.alt = state.context.label;
        image.onload = () => {
            if (!currentArtworkRequest(state, version)) return;
            state.candidate = result;
            artworkElement('confirm').disabled = state.busy;
            artworkElement('message').textContent = result.new_label
                ? workbenchText(`确认后将当前条目改名为「${result.new_label}」，保存这张独立图片。`, `Confirm to rename this entry to “${result.new_label}” and save independent artwork.`)
                : workbenchText('请核对图片和目标位置，确认后写入。', 'Review the image and destination before confirming.');
        };
        image.onerror = () => {
            if (!currentArtworkRequest(state, version)) return;
            state.candidate = null;
            artworkElement('confirm').disabled = true;
            artworkElement('message').textContent = workbenchText('候选图片无法显示，请重新预览。', 'Could not display the candidate. Preview it again.');
        };
        image.src = result.image_url;
        artworkElement('candidate-caption').textContent = `${result.source} · ${result.width} × ${result.height}`;
        artworkElement('target').textContent = (result.replacing ? workbenchText('更换并备份旧图：', 'Replace and back up: ') : workbenchText('新增图片：', 'Add image: ')) + result.target;
        artworkElement('candidate').hidden = false;
        artworkElement('comparison').hidden = false;
        const current = artworkElement('current-image');
        current.hidden = !result.current_image_url;
        artworkElement('current-empty').hidden = Boolean(result.current_image_url);
        artworkElement('current-empty').textContent = result.current_status === 'invalid'
            ? workbenchText('当前图片损坏', 'Current image is damaged') : workbenchText('暂无此类型图片', 'No image of this type');
        current.alt = state.context.label;
        current.onerror = () => { current.hidden = true; artworkElement('current-empty').hidden = false; artworkElement('current-empty').textContent = workbenchText('当前图片读取失败', 'Current image could not be loaded'); };
        if (result.current_image_url) current.src = result.current_image_url;
    } catch (error) {
        if (currentArtworkRequest(state, version)) artworkElement('message').textContent = error.message;
    } finally { if (artworkDialogState === state) artworkBusy(false); }
}

function artworkIndependentNameChanged() {
    invalidateArtworkCandidate();
    artworkElement('message').textContent = workbenchText('名称已修改，请重新预览图片后确认。', 'Name changed. Preview the image again before confirming.');
}

async function importArtwork(file) {
    const state = artworkDialogState;
    if (!state || !file || state.busy) return;
    invalidateArtworkCandidate();
    artworkElement('names').replaceChildren();
    artworkElement('identity').textContent = workbenchText('已选择本地图片。', 'Local image selected.');
    const version = state.version;
    if (file.size > 12 * 1024 * 1024) { artworkElement('message').textContent = workbenchText('图片不能超过 12 MiB。', 'Image exceeds 12 MiB.'); return; }
    artworkBusy(true);
    try {
        const upload = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result).split(',')[1]);
            reader.onerror = () => reject(new Error(workbenchText('无法读取图片文件。', 'Could not read the image.')));
            reader.readAsDataURL(file);
        });
        if (!currentArtworkRequest(state, version)) return;
        artworkBusy(false);
        await previewArtwork({upload, filename: file.name}, state);
    } catch (error) {
        if (currentArtworkRequest(state, version)) { artworkElement('message').textContent = error.message; artworkBusy(false); }
    }
}

async function confirmArtwork() {
    const state = artworkDialogState;
    if (!state || state.busy || !state.candidate || state.key !== JSON.stringify(gameLibraryInput())) return;
    state.applying = true;
    artworkBusy(true);
    artworkElement('message').textContent = workbenchText('正在写入并校验图片…', 'Writing and verifying the image…');
    try {
        if (!state.jobId) {
            const job = await desktopRequest('/api/artwork/apply', {token: state.candidate.token});
            state.jobId = job.job_id;
        }
        while (artworkDialogState === state) {
            const result = await desktopRequest('/api/desktop');
            const job = result.jobs.find(job => job.id === state.jobId);
            if (!job) throw new Error(workbenchText('无法取得任务状态，请重试查询。', 'Could not retrieve the task. Retry to check it.'));
            if (['completed', 'cancelled', 'failed'].includes(job.status)) {
                state.jobId = null;
                if (!job.result?.target) { state.jobId = null; throw new Error(job.error || workbenchText('图片任务已取消。', 'Image update cancelled.')); }
                const item = gameLibrary.data?.items.find(item => item.index === state.context.index && item.label === state.context.label && item.rom_path === state.context.rom_path);
                if (item && state.key === gameLibrary.key) {
                    if (job.result.new_label) item.label = job.result.new_label;
                    item.image_url = job.result.image_url;
                    item.image_path = job.result.target;
                    item.image_status = 'exists';
                    item.image_message = '';
                    item.artwork_result = job.result.backup ? workbenchText('图片已更新，旧图已备份', 'Image updated; previous image backed up')
                        : workbenchText('图片已更新', 'Image updated');
                    if (job.result.new_label) item.artwork_result = workbenchText('已设置独立名称和图片，列表已备份', 'Independent name and artwork saved; playlist backed up');
                    item.artwork_backup = job.result.playlist_backup || job.result.backup || '';
                    if (job.result.memory_warning) item.artwork_result += ' · ' + job.result.memory_warning;
                    gameLibrary.notice = item.label + '：' + item.artwork_result;
                    // Read the same authoritative image selection used on page reload.
                    // A screenshot update must not temporarily replace the row's box art.
                    await loadGameLibrary(gameLibraryInput(), state.key);
                }
                state.candidate = null;
                state.updated = true;
                state.applying = false;
                artworkBusy(false);
                closeArtworkDialog();
                return;
            }
            await new Promise(resolve => setTimeout(resolve, 800));
        }
    } catch (error) {
        artworkElement('message').textContent = error.message;
        const item = gameLibrary.data?.items.find(item => item.index === state.context.index && item.label === state.context.label);
        if (item && gameLibrary.key === state.key) { item.artwork_result = error.message; renderGameLibrary(); }
    } finally {
        if (artworkDialogState === state) { state.applying = false; artworkBusy(false); }
    }
}

function closeArtworkDialog() {
    if (artworkDialogState?.applying || artworkDialogState?.jobId) return;
    const state = artworkDialogState;
    artworkElement('dialog').close();
    finishArtworkDialog(state);
}

function finishArtworkDialog(state) {
    if (!state || artworkDialogState !== state || artworkElement('dialog').open) return;
    artworkDialogState = null;
    if (workbench.operation === 'artwork') endWorkbenchOperation();
    const button = state.key === gameLibrary.key ? document.getElementById('game-artwork-action-' + state.context.index) : null;
    if (button) {
        button.focus({preventScroll: true});
        if (state.updated) button.scrollIntoView({block: 'nearest'});
    } else if (state.returnFocus?.isConnected) state.returnFocus.focus();
    else document.getElementById('game-library-filter-' + (gameLibrary.filter || 'all'))?.focus();
}
artworkElement('dialog').addEventListener('cancel', event => {
    if (artworkDialogState?.applying || artworkDialogState?.jobId) event.preventDefault();
});
artworkElement('dialog').addEventListener('close', () => {
    finishArtworkDialog(artworkDialogState);
});
