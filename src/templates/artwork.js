/* This dialog owns one immutable game context, separate from repair selections. */
let artworkDialogState = null;
const artworkElement = id => document.getElementById('artwork-' + id);
const artworkKindOrder = ['Named_Boxarts', 'Named_Snaps', 'Named_Titles'];

function artworkKindText() {
    return artworkKindOrder.map((kind, i) => workbenchText(['封面', '游戏截图', '标题图'][i], ['Box art', 'Screenshot', 'Title screen'][i]));
}

function artworkKindName(kind) {
    const index = artworkKindOrder.indexOf(kind);
    return index < 0 ? '' : artworkKindText()[index];
}

function artworkKindBox(kind) {
    return artworkElement('kind-' + kind);
}

function selectedArtworkKinds() {
    return artworkKindOrder.filter(kind => artworkKindBox(kind).checked);
}

function setArtworkKinds(kinds) {
    for (const kind of artworkKindOrder) artworkKindBox(kind).checked = kinds.includes(kind);
    if (artworkDialogState) artworkDialogState.kindsTouched = true;
}

function artworkKindLabels() {
    for (const kind of artworkKindOrder) artworkElement('kind-name-' + kind).textContent = artworkKindName(kind);
}

function renderArtworkKindStatus(artwork) {
    const states = {exists: ['已有图片', 'Has image'], missing: ['缺少图片', 'Missing'], invalid: ['图片损坏', 'Damaged'],
        unreadable: ['读取失败', 'Unreadable']};
    for (const kind of artworkKindOrder) {
        const status = artwork?.[kind]?.status;
        const element = artworkElement('kind-status-' + kind);
        element.textContent = status ? workbenchText(...(states[status] || states.missing)) : '';
        element.title = artwork?.[kind]?.message || '';
    }
}

// Missing types are the default target; a game that already has all three keeps the box art selected.
function applyArtworkKindDefaults(artwork) {
    const missing = artworkKindOrder.filter(kind => (artwork?.[kind]?.status || 'missing') !== 'exists');
    setArtworkKinds(missing.length ? missing : ['Named_Boxarts']);
    if (artworkDialogState) artworkDialogState.kindsTouched = false;
}

function artworkTierLabel(tier) {
    return {exact: workbenchText('完整名称匹配', 'Exact title match'),
        catalog: workbenchText('中文名库转换', 'Translated by the name catalog'),
        words: workbenchText('包含全部关键词', 'Contains every keyword'),
        fuzzy: workbenchText('名称相近，请核对版本', 'Close name, check the edition')}[tier] || '';
}

function artworkSuggestionDetail(suggestion) {
    const parts = [];
    if (suggestion.chinese_name) parts.push(workbenchText('中文名：', 'Chinese name: ') + suggestion.chinese_name);
    const tier = artworkTierLabel(suggestion.tier);
    if (tier) parts.push(tier);
    if (suggestion.score) parts.push(workbenchText('匹配度 ', 'Match ') + suggestion.score + '%');
    return parts.join(' · ');
}

// Name candidates are choices, never decisions: picking one only fills the search box.
function artworkNameOptions(label, options) {
    artworkElement('names-label').textContent = label;
    artworkElement('names-wrap').hidden = !options.length;
    artworkElement('names').replaceChildren();
    for (const option of options) {
        const button = document.createElement('button');
        button.className = 'btn btn-muted artwork-name-option';
        button.type = 'button';
        const name = document.createElement('span');
        name.textContent = option.name;
        button.appendChild(name);
        if (option.detail) {
            const detail = document.createElement('small');
            detail.textContent = option.detail;
            button.appendChild(detail);
        }
        button.onclick = () => {
            artworkElement('source').value = option.name;
            artworkElement('names-wrap').hidden = true;
            artworkElement('names').replaceChildren();
            artworkElement('identity').textContent = workbenchText('已选择候选名称：', 'Candidate name selected: ') + option.name;
            searchArtwork(false);
        };
        artworkElement('names').appendChild(button);
    }
}

function hideArtworkComparison() {
    artworkElement('comparison').hidden = true;
    artworkElement('skipped').textContent = '';
    for (const kind of artworkKindOrder) artworkElement('row-' + kind).hidden = true;
}

function openArtworkDialog(item, autoSearch = true) {
    if (workbench.operation) return;
    const [playlist_path, system, thumbnails] = gameLibraryInput();
    if (!thumbnails) { openPathSettings(); return; }
    const key = JSON.stringify(gameLibraryInput());
    artworkDialogState = {context: {playlist_path, system, thumbnails, index: item.index, label: item.label, rom_path: item.rom_path},
        key, fromPreview: workbench.previewKey != null, version: 0, candidate: null, busy: false, searching: false, applying: false, jobId: null, kindsTouched: false, returnFocus: document.activeElement};
    if (!beginWorkbenchOperation('artwork')) { artworkDialogState = null; return; }
    const text = workbenchText;
    artworkElement('title').textContent = !item.image_url ? text('为这个游戏补图', 'Add artwork for this game')
        : missingArtworkKinds(item).length ? text('补齐缺少的图片', 'Fill in the missing artwork')
        : text('更换游戏图片', 'Replace game artwork');
    artworkElement('game').textContent = item.label;
    artworkElement('shared').hidden = true;
    artworkElement('new-label').value = '';
    artworkElement('scope').textContent = text('勾选这次要补的图片类型，可同时修改名称。更换已有图片时会备份旧图；未勾选的类型不会被改动。', 'Choose the artwork types to fill in, with an optional name change. Replaced images are backed up; unchecked types are left untouched.');
    artworkElement('close').textContent = text('关闭', 'Close');
    artworkElement('kind-label').textContent = text('图片类型（可多选）', 'Image types (multiple allowed)');
    artworkKindLabels();
    setArtworkKinds(['Named_Boxarts']);
    artworkDialogState.kindsTouched = false;
    renderArtworkKindStatus(null);
    artworkElement('source-label').textContent = text('搜索官方图库（Libretro）', 'Search the official library (Libretro)');
    artworkElement('source').placeholder = text('输入中/英文游戏名，例如 Ys III 或 伊苏3', 'Enter a Chinese or English title, e.g. Ys III or 伊苏3');
    artworkElement('source').value = '';
    artworkElement('names-wrap').hidden = true;
    artworkElement('names').replaceChildren();
    artworkElement('secondary').hidden = true;
    artworkElement('secondary').textContent = text('搜索备用来源', 'Search alternate source');
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
    if (autoSearch) return discoverArtwork();
}

async function openArtworkImport(item) {
    if (workbench.operation) return;
    openArtworkDialog(item, false);
    const state = artworkDialogState;
    if (!state) return;
    await discoverArtwork(false);
    if (artworkDialogState !== state) return;
    artworkElement('upload').focus();
    artworkElement('upload').scrollIntoView({block:'center'});
    artworkElement('message').textContent = workbenchText('选择本地图片后预览，确认后保存到已勾选的图片类型。', 'Choose a local image to preview, then confirm to save it to the checked types.');
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
    hideArtworkComparison();
    artworkElement('confirm').disabled = true;
    artworkElement('results').replaceChildren();
    artworkElement('message').textContent = '';
}

function artworkBusy(busy) {
    const state = artworkDialogState;
    if (!state) return;
    state.busy = busy;
    for (const id of [...artworkKindOrder.map(kind => 'kind-' + kind), 'source', 'search', 'secondary', 'preview', 'upload', 'new-label']) artworkElement(id).disabled = busy || Boolean(state.jobId);
    artworkElement('results').inert = busy || Boolean(state.jobId);
    artworkElement('close').disabled = state.applying || Boolean(state.jobId);
    artworkElement('confirm').disabled = busy || !state.candidate;
    artworkElement('confirm').textContent = state.applying ? workbenchText('更新中…', 'Updating…')
        : state.jobId ? workbenchText('查询更新结果', 'Check update result') : workbenchText('确认', 'Confirm');
}

function artworkKindChanged() {
    const state = artworkDialogState;
    if (!state) return;
    if (!selectedArtworkKinds().length) {
        invalidateArtworkCandidate();
        artworkElement('message').textContent = workbenchText('请至少选择一种图片类型。', 'Choose at least one image type.');
        return;
    }
    invalidateArtworkCandidate();
    artworkElement('message').textContent = workbenchText('图片类型已修改，请重新预览后确认。', 'Image types changed. Preview the images again before confirming.');
}

function artworkSearchChanged() {
    if (artworkDialogState) artworkDialogState.selectedExternal = null;
    invalidateArtworkCandidate();
    artworkElement('names').replaceChildren();
    artworkElement('names-wrap').hidden = true;
    artworkElement('identity').textContent = workbenchText('已修改搜索词，请搜索官方图库。', 'Search term changed. Search the official library.');
}

async function discoverArtwork(searchAfter = true) {
    const state = artworkDialogState;
    if (!state || state.busy || state.jobId) return;
    state.selectedExternal = null;
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
            renderArtworkKindStatus(entryInfo.artwork);
            if (!state.kindsTouched) applyArtworkKindDefaults(entryInfo.artwork);
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
                artworkElement('shared-help').textContent = workbenchText('建议名称取自 ROM 文件名，可修改。请核对英文名与游戏版本；未勾选的类型图片会复制保留，游戏列表会备份。', 'The suggested name comes from the ROM filename and is editable. Check the English title and game version. Unchecked types are copied and the playlist is backed up.');
            }
        }
        const lookup = {...state.context, kind: selectedArtworkKinds()[0] || 'Named_Boxarts'};
        if (state.entryInfo) lookup.label = artworkElement('new-label').value;
        const result = await desktopRequest('/api/artwork/resolve', lookup);
        if (!currentArtworkRequest(state, version)) return;
        const reasons = {remembered: ['上次确认的图片源', 'Previously confirmed source'], confirmed: ['人工确认的名称', 'Confirmed name'],
            curated: ['已知名称', 'Known title'], rom_alias: ['从 ROM 名称识别，请核对候选图片', 'From the ROM name; review the candidate artwork'], database: ['名称库匹配', 'Name catalog match'], alias: ['名称别名匹配', 'Name alias match'], filename: ['从 ROM 名称提取', 'From the ROM title']};
        if (result.status === 'resolved') {
            artworkElement('source').value = result.query;
            const reason = reasons[result.reason] || ['识别名称', 'Identified title'];
            artworkElement('identity').textContent = workbenchText(...reason) + '：' + result.query;
            if (searchAfter) await searchArtwork(true);
        } else if (result.status === 'ambiguous') {
            artworkElement('identity').textContent = workbenchText('找到多个可能的名称，请选择游戏后搜索。', 'Several possible titles found. Choose the game to search.');
            artworkNameOptions(workbenchText('名称库候选（请选择要搜索的游戏）', 'Catalog candidates (choose one to search)'),
                result.names.map(name => ({name, detail: ''})));
        } else if (result.suggestions?.length) {
            artworkElement('identity').textContent = workbenchText('未识别出确切英文名。本地名称库找到以下候选，请核对中文名后选择：', 'No exact English title identified. The local name catalog offers these candidates; check the Chinese name before choosing.');
            artworkNameOptions(workbenchText('中文名库候选（均需人工核对）', 'Name catalog candidates (all need verification)'),
                result.suggestions.map(suggestion => ({name: suggestion.english_name, detail: artworkSuggestionDetail(suggestion)})));
        } else {
            artworkElement('source').value = '';
            artworkElement('identity').textContent = state.context.system === 'DOS'
                ? workbenchText('名称未识别：未找到该 DOS 游戏的英文名。请填写游戏全名搜索，或导入本地图片。', 'Title not identified: no English name found for this DOS game. Enter the full game title or import an image.')
                : workbenchText('尚未识别英文名。请输入英文游戏名搜索，或导入本地图片。', 'English title not identified. Enter a title to search or import an image.');
        }
    } catch (error) {
        if (currentArtworkRequest(state, version)) artworkElement('identity').textContent = workbenchText('名称识别失败：', 'Title lookup failed: ') + error.message;
    } finally { if (currentArtworkRequest(state, version)) state.searching = false; }
}

async function searchArtwork(automatic = false, provider = 'libretro') {
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
    artworkElement('names-wrap').hidden = true;
    artworkElement('names').replaceChildren();
    artworkElement('message').textContent = workbenchText('正在搜索官方图库，可随时导入本地图片…', 'Searching the official library. You can import an image at any time…');
    try {
        state.selectedExternal = null;
        // The gallery index is per type: search the first checked type, and only offer the
        // alternate provider when it can actually supply that type.
        const kind = selectedArtworkKinds()[0] || 'Named_Boxarts';
        artworkElement('secondary').hidden = kind !== 'Named_Boxarts';
        const lookup = {system: state.context.system, kind, query, automatic, provider, label: state.context.label};
        let result = await desktopRequest('/api/artwork/search', lookup);
        if (!currentArtworkRequest(state, version)) return;
        if (!result.total && provider === 'libretro' && kind === 'Named_Boxarts') {
            artworkElement('message').textContent = workbenchText('官方图库未找到，正在搜索备用来源…', 'No official match. Searching the alternate source…');
            result = await desktopRequest('/api/artwork/search', {...lookup, provider: 'wikipedia'});
            if (!currentArtworkRequest(state, version)) return;
        }
        const secondary = result.provider === 'wikipedia';
        const candidates = result.candidates || result.names.map(name => ({name}));
        const downgraded = Boolean(result.total) && candidates.every(candidate => candidate.tier === 'fuzzy');
        const translated = Boolean(result.total) && candidates.every(candidate => candidate.tier === 'catalog');
        artworkElement('message').textContent = result.total
            ? (secondary ? workbenchText('备用配图（非官方图库）：请核对平台、版本和图片类型，选择后预览确认。', 'Alternate artwork (not Libretro): check platform, edition and image type before confirming.')
                : downgraded ? workbenchText(`图库没有完全匹配，以下 ${result.total} 张为名称相近的结果，请核对版本后再选择。`, `No exact match. These ${result.total} images have a close name; check the edition before selecting.`)
                : translated ? workbenchText(`中文名已由本地名称库转换，找到 ${result.total} 张候选图片，请核对中文名与版本。`, `The Chinese title went through the local name catalog. Found ${result.total} candidates; check the Chinese name and edition.`)
                : workbenchText(`找到 ${result.total} 张官方候选图片，选择图片查看对比。`, `Found ${result.total} official images. Select one to compare.`))
            : result.suggestions?.length
                ? workbenchText('官方图库未找到对应图片。本地中文名库有这些候选英文名，请核对后选择：', 'No matching image in the official library. The local name catalog offers these English titles; check them before choosing:')
                : workbenchText('图库未找到：可修改名称搜索，或导入本地图片。', 'No gallery match. Edit the title or import an image.');
        if (!result.total && result.suggestions?.length) {
            artworkNameOptions(workbenchText('中文名库候选（均需人工核对）', 'Name catalog candidates (all need verification)'),
                result.suggestions.map(suggestion => ({name: suggestion.english_name, detail: artworkSuggestionDetail(suggestion)})));
        }
        for (const candidate of candidates) {
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
            const tier = artworkTierLabel(candidate.tier || (candidate.exact ? 'exact' : ''));
            if (tier) {
                const badge = document.createElement('small'); badge.textContent = tier; button.appendChild(badge);
            }
            if (candidate.hint) {
                const hint = document.createElement('small'); hint.className = 'artwork-hint';
                hint.textContent = workbenchText('中文名：', 'Chinese name: ') + candidate.hint.chinese_name
                    + (candidate.hint.score ? ' · ' + workbenchText('匹配度 ', 'Match ') + candidate.hint.score + '%' : '');
                button.appendChild(hint);
            }
            const detail = document.createElement('small');
            detail.textContent = [candidate.provider_label || 'Libretro', candidate.platform, candidate.version].filter(Boolean).join(' · ');
            button.appendChild(detail);
            button.onclick = () => {
                artworkElement('source').value = candidate.name;
                state.selectedExternal = candidate.id ? {id:candidate.id, name:candidate.name, kind} : null;
                previewArtwork();
            };
            const card = document.createElement('div'); card.className = 'artwork-result-card';
            card.appendChild(button);
            artworkElement('results').appendChild(card);
            if (candidate.source_page) {
                const link = document.createElement('a'); link.textContent = workbenchText('查看来源与版本说明', 'View source and edition');
                link.href = candidate.source_page; link.target = '_blank'; link.rel = 'noopener noreferrer';
                card.appendChild(link);
            }
        }
    } catch (error) {
        if (currentArtworkRequest(state, version)) artworkElement('message').textContent = workbenchText('图库搜索失败，可点击“搜索图库”重试：', 'Library search failed. Select Search library to retry: ') + error.message;
    } finally { if (currentArtworkRequest(state, version)) state.searching = false; }
}

function showArtworkComparison(state, result, version) {
    const images = result.images || [result];
    let pending = 0;
    for (const kind of artworkKindOrder) {
        const row = artworkElement('row-' + kind);
        const image = images.find(item => (item.kind || 'Named_Boxarts') === kind);
        row.hidden = !image;
        if (!image) continue;
        const name = artworkKindName(kind);
        artworkElement('current-label-' + kind).textContent = workbenchText('当前图片', 'Current image') + (name ? ' · ' + name : '');
        artworkElement('candidate-label-' + kind).textContent = workbenchText('候选图片', 'Candidate image') + (name ? ' · ' + name : '');
        const current = artworkElement('current-image-' + kind);
        const empty = artworkElement('current-empty-' + kind);
        current.hidden = !image.current_image_url;
        empty.hidden = Boolean(image.current_image_url);
        empty.textContent = image.current_status === 'invalid'
            ? workbenchText('当前图片损坏', 'Current image is damaged') : workbenchText('暂无此类型图片', 'No image of this type');
        current.alt = state.context.label;
        current.onerror = () => { current.hidden = true; empty.hidden = false; empty.textContent = workbenchText('当前图片读取失败', 'Current image could not be loaded'); };
        if (image.current_image_url) current.src = image.current_image_url;
        artworkElement('candidate-caption-' + kind).textContent = [image.source, `${image.width} × ${image.height}`,
            image.provenance?.provider_label, image.provenance?.platform, image.provenance?.version].filter(Boolean).join(' · ');
        artworkElement('target-' + kind).textContent = (image.replacing ? workbenchText('更换并备份旧图：', 'Replace and back up: ') : workbenchText('新增图片：', 'Add image: ')) + image.target;
        const candidate = artworkElement('candidate-image-' + kind);
        candidate.alt = state.context.label;
        pending++;
        candidate.onload = () => {
            if (!currentArtworkRequest(state, version)) return;
            pending--;
            ready();
        };
        candidate.onerror = () => {
            if (!currentArtworkRequest(state, version)) return;
            pending--;
            state.candidate = null;
            artworkElement('confirm').disabled = true;
            artworkElement('message').textContent = workbenchText('候选图片无法显示，请重新预览。', 'Could not display the candidate. Preview it again.');
        };
        candidate.src = image.image_url;
    }
    artworkElement('comparison').hidden = !images.length;
    const separator = workbenchText('、', ', ');
    const skipped = result.skipped || [];
    const skippedNames = skipped.map(entry => artworkKindName(entry.kind) || entry.label).filter(Boolean);
    artworkElement('skipped').textContent = skipped.length
        ? workbenchText(`官方图库没有收录：${skippedNames.join(separator)}。这些类型不会写入。`, `Not in the official library: ${skippedNames.join(separator)}. Those types will not be written.`)
        : '';
    function ready() {
        if (pending || !currentArtworkRequest(state, version)) return;
        state.candidate = result;
        artworkElement('confirm').disabled = state.busy;
        const names = images.map(image => artworkKindName(image.kind) || image.label).filter(Boolean).join(separator);
        artworkElement('message').textContent = result.new_label
            ? workbenchText(`确认后将当前条目改名为「${result.new_label}」，保存这些独立图片：${names}。`, `Confirm to rename this entry to “${result.new_label}” and save independent artwork: ${names}.`)
            : workbenchText(`将写入：${names}。请核对图片和目标位置，确认后写入。`, `Will write: ${names}. Review the images and destinations before confirming.`);
    }
    if (!pending) ready();
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
    const kinds = selectedArtworkKinds();
    if (!kinds.length) {
        artworkElement('message').textContent = workbenchText('请至少选择一种图片类型。', 'Choose at least one image type.');
        return;
    }
    const version = state.version;
    const external = state.selectedExternal;
    // The alternate provider only supplies box art; every other checked type would fail.
    const externalKinds = external && external.name === artworkElement('source').value ? ['Named_Boxarts'] : null;
    const selection = externalKinds ? {candidate_id: external.id} : {source: artworkElement('source').value};
    artworkBusy(true);
    artworkElement('message').textContent = workbenchText('正在准备候选图片…', 'Preparing the candidate images…');
    try {
        const result = await desktopRequest('/api/artwork/preview', {...state.context, kinds: externalKinds || kinds,
            ...(state.entryInfo ? {new_label: artworkElement('new-label').value.trim()} : {}),
            ...(upload || selection)});
        if (!currentArtworkRequest(state, version)) return;
        showArtworkComparison(state, result, version);
    } catch (error) {
        if (currentArtworkRequest(state, version)) artworkElement('message').textContent = error.message;
    } finally { if (artworkDialogState === state) artworkBusy(false); }
}

function artworkIndependentNameChanged() {
    invalidateArtworkCandidate();
    artworkElement('message').textContent = workbenchText('名称已修改，请重新预览图片后确认。', 'Name changed. Preview the images again before confirming.');
}

async function importArtwork(file) {
    const state = artworkDialogState;
    if (!state || !file || state.busy) return;
    invalidateArtworkCandidate();
    artworkElement('names').replaceChildren();
    artworkElement('names-wrap').hidden = true;
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
    artworkElement('message').textContent = workbenchText('正在写入并校验图片…', 'Writing and verifying the images…');
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
                const written = job.result?.images?.length ? job.result.images : (job.result?.target ? [job.result] : []);
                if (!written.length) { state.jobId = null; throw new Error(job.error || workbenchText('图片任务已取消。', 'Image update cancelled.')); }
                const item = gameLibrary.data?.items.find(item => item.index === state.context.index && item.label === state.context.label && item.rom_path === state.context.rom_path);
                if (item && state.key === gameLibrary.key) {
                    if (job.result.new_label) item.label = job.result.new_label;
                    const primary = written.find(image => image.kind === 'Named_Boxarts') || written[0];
                    const names = written.map(image => artworkKindName(image.kind)).filter(Boolean).join(workbenchText('、', ', '));
                    const updated = names ? workbenchText(`已更新${names}图片`, `Updated ${names} artwork`) : workbenchText('图片已更新', 'Image updated');
                    item.image_url = primary.image_url;
                    item.image_path = primary.target;
                    item.image_status = 'exists';
                    item.image_message = '';
                    item.artwork_result = job.result.new_label ? workbenchText('已设置独立名称和图片，列表已备份', 'Independent name and artwork saved; playlist backed up')
                        : job.result.backup ? updated + workbenchText('，旧图已备份', '; previous images backed up') : updated;
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
                // A single-image write may rename the row. Discard proposals
                // based on its old identity before returning to the game list.
                if (state.fromPreview) invalidateWorkbenchPreview();
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
