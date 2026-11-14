/* Selected-game details, manual corrections and artwork entry points. */

function selectPreviewRow(index) {
    selectedChangeIndex = index;
    document.querySelectorAll('#preview-table-body tr').forEach(row => {
        row.classList.toggle('selected', Number(row.dataset.index) === index);
    });
    document.querySelector('.app-shell')?.classList.remove('inspector-hidden');
    updateInspector(currentChanges[index]);
}

function openArtworkForSelected() {
    const change = currentChanges[selectedChangeIndex];
    if (!change) {
        showStatus(currentUILanguage === 'en' ? 'Select a game first.' : '请先选择一个游戏', 'error');
        return;
    }
    openArtworkDialog({index: change.index, label: getCurrentItemLabel(change), rom_path: change.path});
}

function updateInspector(change) {
    if (!change) {
        clearInspector();
        return;
    }
    const info = getMatchInfo(change);
    const coverUrl = getCoverPreviewUrl(change);
    const coverSource = getCoverPreviewSourceLabel(change);
    const cover = document.getElementById('cover-preview');
    const coverImage = document.getElementById('cover-image');

    document.getElementById('cover-title').textContent = change.new_label || change.original_label || '未命名';
    document.getElementById('cover-subtitle').textContent = coverSource;
    document.getElementById('inspector-caption').textContent = getCurrentItemLabel(change);
    document.getElementById('inspector-original').textContent = getCurrentItemMeta(change) || getCurrentItemLabel(change);
    const hasChineseDisplayName = /[\u4e00-\u9fff]/.test(change.new_label || '');
    document.getElementById('inspector-cn').textContent = hasChineseDisplayName
        ? change.new_label
        : change.new_label
            ? (currentUILanguage === 'en'
                ? `No Chinese name found; using standard English: ${change.new_label}`
                : `未找到中文名，暂用标准英文：${change.new_label}`)
            : uiText('未匹配中文名');
    document.getElementById('inspector-dat').textContent = change.thumbnail_source || '未匹配标准英文名';
    document.getElementById('inspector-url').textContent = coverSource;
    document.getElementById('inspector-label').value = change.new_label || '';
    document.getElementById('inspector-thumb').value = change.thumbnail_source || '';
    document.getElementById('inspector-confidence').textContent = `${info.label} · ${info.reason}`;
    if (change.artwork) {
        const kinds = { Named_Boxarts: '封面', Named_Snaps: '游戏截图', Named_Titles: '标题图' };
        const statuses = { exists: '已存在', reusable: '可复用', invalid: '文件损坏', missing: '待下载', missing_source: '缺少来源', failed: '失败' };
        document.getElementById('inspector-confidence').textContent += ' · ' + Object.entries(change.artwork)
            .map(([kind, item]) => `${kinds[kind] || kind}：${statuses[item.status] || item.status}`).join(' / ');
    }
    document.getElementById('confirm-reviewed').disabled = !['review', 'duplicate'].includes(change.match_status) || !String(change.new_label || '').trim();
    const searchButton = document.getElementById('search-selected-thumb-btn');
    if (searchButton) searchButton.disabled = false;
    const saveOverrideButton = document.getElementById('save-local-override');
    if (saveOverrideButton) saveOverrideButton.disabled = !canSaveSelectedOverride(change);

    cover.classList.remove('has-image');
    coverImage.removeAttribute('src');
    coverImage.alt = getCurrentItemLabel(change);
    if (coverUrl) {
        coverImage.onload = () => cover.classList.add('has-image');
        coverImage.onerror = () => cover.classList.remove('has-image');
        coverImage.src = coverUrl;
    }
}

function clearInspector() {
    document.getElementById('confirm-reviewed').disabled = true;
    selectedChangeIndex = -1;
    const cover = document.getElementById('cover-preview');
    const coverImage = document.getElementById('cover-image');
    document.querySelector('.app-shell')?.classList.add('inspector-hidden');
    document.querySelectorAll('#preview-table-body tr').forEach(row => row.classList.remove('selected'));
    cover.classList.remove('has-image');
    coverImage.removeAttribute('src');
    coverImage.alt = '';
    document.getElementById('cover-title').textContent = '等待选择';
    document.getElementById('cover-subtitle').textContent = '预览行会显示匹配链路';
    document.getElementById('inspector-caption').textContent = '未选择游戏';
    document.getElementById('inspector-original').textContent = '尚未分析';
    document.getElementById('inspector-cn').textContent = '等待匹配';
    document.getElementById('inspector-dat').textContent = '等待标准名';
    document.getElementById('inspector-url').textContent = '等待封面源';
    document.getElementById('inspector-label').value = '';
    document.getElementById('inspector-thumb').value = '';
    document.getElementById('inspector-confidence').textContent = '--';
    const searchButton = document.getElementById('search-selected-thumb-btn');
    if (searchButton) searchButton.disabled = true;
    const saveOverrideButton = document.getElementById('save-local-override');
    if (saveOverrideButton) saveOverrideButton.disabled = true;
}

function closeInspector() {
    clearInspector();
}

function updateSelectedFromInspector(key, value) {
    if (selectedChangeIndex < 0 || !currentChanges[selectedChangeIndex]) return;
    currentChanges[selectedChangeIndex][key] = value;
    markChangeEdited(selectedChangeIndex, key === 'new_label' ? '手动编辑显示名称' : '手动编辑封面源', key);
    renderPreviewTable(currentChanges);
    selectPreviewRow(selectedChangeIndex);
    updateSummary(currentChanges);
}

function confirmReviewedChange() {
    const change = currentChanges[selectedChangeIndex];
    if (!change || !String(change.new_label || '').trim()) return;
    change.review_confirmed = true;
    change.enabled = true;
    hideApplySummary();
    renderPreviewTable(currentChanges);
    updateSummary(currentChanges);
    selectPreviewRow(selectedChangeIndex);
    showStatus('已加入应用队列，提交前仍可检查变更摘要', 'success');
}

function canSaveSelectedOverride(change = currentChanges[selectedChangeIndex]) {
    return selectedChangeIndex >= 0
        && Boolean(change)
        && isEditedChange(change)
        && Boolean(normalizeDisplayName(change.new_label))
        && Boolean(normalizeDisplayName(change.thumbnail_source));
}

async function saveSelectedOverride() {
    const index = selectedChangeIndex;
    const change = currentChanges[index];
    if (!canSaveSelectedOverride(change)) return;

    const button = document.getElementById('save-local-override');
    if (button) button.disabled = true;

    const system = change.system || document.getElementById('system_name').value || '';
    const payload = {
        system,
        change: {
            system,
            path: change.path || '',
            crc32: change.crc32 || '',
            new_label: change.new_label || '',
            thumbnail_source: change.thumbnail_source || ''
        }
    };

    try {
        const response = await fetch('/api/overrides/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.error) throw new Error(data.error || '保存本地修正规则失败');

        const saved = data.entry || payload.change;
        const savedChange = currentChanges[index];
        if (!savedChange) return;
        savedChange.system = saved.system || system || savedChange.system;
        savedChange.new_label = saved.new_label || savedChange.new_label;
        savedChange.thumbnail_source = saved.thumbnail_source || savedChange.thumbnail_source;
        savedChange.match_source = 'manual_override';
        savedChange.match_status = 'review';
        savedChange.match_score = 100;
        savedChange.match_reason = uiText('本地修正规则已保存，重新预览后应用');
        savedChange.needs_review = true;
        savedChange.pending_override = false;
        savedChange.enabled = false;

        updateSummary(currentChanges);
        renderPreviewTable(currentChanges);
        selectPreviewRow(index);
        showStatus(uiText('本地修正规则已保存'), 'success');
    } catch (error) {
        showStatus('保存本地修正规则失败: ' + error.message, 'error');
    } finally {
        const currentButton = document.getElementById('save-local-override');
        if (currentButton) currentButton.disabled = !canSaveSelectedOverride();
    }
}

function refreshCoverPreview() {
    if (selectedChangeIndex < 0 || !currentChanges[selectedChangeIndex]) return;
    updateInspector(currentChanges[selectedChangeIndex]);
}

async function openThumbnailFolder() {
    const dir = getThumbnailsDirectory();

    if (!dir) {
        showStatus('请先设置缩略图保存路径', 'error');
        return;
    }

    if (dir.startsWith('adb://')) {
        showStatus('这是 ADB 实机目录，不能用本机文件管理器直接打开', 'info');
        return;
    }

    try {
        const response = await fetch('/api/fs/open', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: dir })
        });
        const data = await response.json();
        if (!response.ok || data.error) throw new Error(data.error || '打开目录失败');
        showStatus('已在系统文件管理器打开缩略图目录', 'success');
    } catch (error) {
        showStatus('打开目录失败: ' + error.message, 'error');
    }
}
