/* Repair preview rows, filters and selection summaries. */
let currentChanges = [];
let currentPreviewFilter = 'all';

async function previewTask() {
    const playlistPath = document.getElementById('playlist_path').value;
    const systemName = document.getElementById('system_name').value;
    const thumbnailsDir = getThumbnailsDirectory();
    hideApplySummary();

    if (!playlistPath || !systemName) {
        showStatus('请先选择游戏列表和系统', 'error');
        return;
    }

    if (!beginWorkbenchOperation('preview')) return;
    invalidateWorkbenchPreview();
    const previewKey = workbenchInputKey();
    showStatus('正在分析游戏列表...', 'success');
    setInlineProgress(8, '分析中', '正在分析游戏列表', '当前：生成预览');

    try {
        if (!await saveConfig('single')) throw new Error(uiText('读取失败'));
        const response = await fetch('/api/playlist/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ playlist_path: playlistPath, system_name: systemName, thumbnails_dir: thumbnailsDir })
        });

        const data = await response.json();
        if (data.error) throw new Error(data.error);

        currentChanges = preparePreviewChanges(data.changes || []);
        workbench.previewKey = previewKey;
        lastAppliedChangeKeys = new Set();
        lastDownloadSummary = null;
        setDownloadSummary(null);
        setLibraryBrowserVisible(true);
        setPreviewAreaVisible(true);
        document.getElementById('preview-empty').style.display = currentChanges.length ? 'none' : 'grid';
        document.getElementById('preview-container').style.display = currentChanges.length ? 'block' : 'none';
        updateSummary(currentChanges);
        renderPreviewTable(currentChanges);
        showLogPanel(null);
        showStatus('分析完成，请校对', 'success');
    } catch (error) {
        showStatus('预览失败: ' + error.message, 'error');
        setInlineProgress(0, '失败', '预览失败', '当前：请检查路径和系统');
    } finally {
        endWorkbenchOperation();
    }
}

function renderPreviewTable(changes) {
    const tbody = document.getElementById('preview-table-body');
    tbody.innerHTML = '';
    const query = (document.getElementById('preview-search').value || '').trim().toLowerCase();

    const visibleChanges = changes
        .map((change, index) => ({ change, index }))
        .filter(({ change }) => matchesFilter(change, query));

    visibleChanges.forEach(({ change, index }) => {
        const info = getMatchInfo(change);
        const tr = document.createElement('tr');
        tr.dataset.index = index;
        tr.className = info.rowClass;
        const tdSelect = document.createElement('td');
        tdSelect.className = 'select-cell';
        const canSelect = isActionableChange(change);
        const isSelected = change.enabled !== false && canSelect;
        const rowCheck = document.createElement('button');
        rowCheck.type = 'button';
        rowCheck.className = 'row-check';
        rowCheck.textContent = isSelected ? '✓' : '';
        rowCheck.setAttribute('role', 'checkbox');
        rowCheck.setAttribute('aria-checked', String(isSelected));
        rowCheck.setAttribute('aria-disabled', String(!canSelect));
        rowCheck.setAttribute('aria-label', workbenchText('选择 ', 'Select ') + (change.original_label || uiText('当前')));
        rowCheck.disabled = !canSelect;
        rowCheck.addEventListener('click', (event) => {
            event.stopPropagation();
            toggleChangeEnabled(index, event.currentTarget);
        });
        tdSelect.appendChild(rowCheck);
        tdSelect.addEventListener('click', (event) => {
            event.stopPropagation();
            toggleChangeEnabled(index, rowCheck);
        });
        tr.appendChild(tdSelect);

        const tdOriginal = document.createElement('td');
        tdOriginal.className = 'name-cell library-name-cell';
        const tableThumb = document.createElement('div');
        tableThumb.className = 'table-thumb';
        const coverUrl = getCoverPreviewUrl(change);
        if (coverUrl) {
            const img = document.createElement('img');
            img.alt = '';
            img.loading = 'lazy';
            img.src = coverUrl;
            img.onerror = () => {
                const fallbackUrl = getRemoteCoverUrl(change);
                if (fallbackUrl && fallbackUrl !== coverUrl) {
                    img.onerror = () => {
                        tableThumb.textContent = hasExistingCover(change) ? uiText('本地') : 'IMG';
                    };
                    img.src = fallbackUrl;
                    return;
                }
                tableThumb.textContent = hasExistingCover(change) ? uiText('本地') : 'IMG';
            };
            tableThumb.appendChild(img);
        } else {
            tableThumb.textContent = 'IMG';
        }
        const originalText = document.createElement('div');
        originalText.className = 'name-edit';
        const originalLabel = getCurrentItemLabel(change);
        originalText.appendChild(buildPreviewEditor(change, index, 'new_label', change.new_label || '', uiText('游戏名称')));
        const originalPath = document.createElement('div');
        originalPath.className = 'name-secondary';
        originalPath.textContent = String(change.path || '').split(/[\\/#]/).pop();
        originalPath.title = change.path || '';
        originalText.appendChild(originalPath);
        tdOriginal.appendChild(tableThumb);
        tdOriginal.appendChild(originalText);
        tdOriginal.title = [originalLabel, getCurrentItemMeta(change)].filter(Boolean).join('\n');
        tr.appendChild(tdOriginal);
        tr.appendChild(buildStatusCell(info, index));

        const tdThumb = document.createElement('td');
        tdThumb.className = 'en-name-col';
        const thumbWrap = document.createElement('div');
        thumbWrap.className = 'thumb-cell';
        thumbWrap.appendChild(buildPreviewEditor(change, index, 'thumbnail_source', change.thumbnail_source || change.artwork_query || '', uiText('封面源英文名')));
        const artworkButton = document.createElement('button');
        artworkButton.className = 'btn btn-muted replace-artwork';
        artworkButton.type = 'button';
        artworkButton.textContent = workbenchText('更换图片', 'Change artwork');
        artworkButton.onclick = event => {
            event.stopPropagation();
            openArtworkDialog({index: change.index, label: getCurrentItemLabel(change), rom_path: change.path});
        };
        thumbWrap.appendChild(artworkButton);

        tdThumb.appendChild(thumbWrap);
        tr.appendChild(tdThumb);

        tr.appendChild(buildCoverStatusCell(change));

        tbody.appendChild(tr);
    });

    if (!visibleChanges.length && changes.length) {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = 5;
        td.style.textAlign = 'center';
        td.style.color = 'var(--muted)';
        td.style.padding = '28px';
        td.textContent = uiText('没有符合当前筛选条件的项目。');
        tr.appendChild(td);
        tbody.appendChild(tr);
    }
}

function buildPreviewEditor(change, index, key, value, label) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'preview-edit-text ' + (key === 'new_label' ? 'new-label-text' : 'thumb-source-text');
    button.textContent = value || workbenchText('点击填写', 'Click to enter');
    button.title = label + ': ' + (value || uiText('待补充'));
    button.setAttribute('aria-label', workbenchText('编辑', 'Edit') + ' ' + label + ': ' + getCurrentItemLabel(change));
    button.onclick = event => {
        event.stopPropagation();
        const input = document.createElement('input');
        input.type = 'text';
        input.className = key === 'new_label' ? 'new-label-input' : 'thumb-source-input';
        input.setAttribute('aria-label', label + ': ' + getCurrentItemLabel(change));
        input.value = value;
        input.onclick = event => event.stopPropagation();
        let finished = false;
        const finish = commit => {
            if (finished) return;
            finished = true;
            if (commit && input.value !== value) {
                value = input.value;
                currentChanges[index][key] = value;
                markChangeEdited(index, key === 'new_label' ? '手动编辑显示名称' : '手动编辑封面源', key);
                button.textContent = value || workbenchText('点击填写', 'Click to enter');
                button.title = label + ': ' + (value || uiText('待补充'));
                refreshPreviewRowState(index);
                updateSummary(currentChanges);
            }
            input.replaceWith(button);
        };
        input.onblur = () => finish(true);
        input.onkeydown = event => {
            if (event.key === 'Enter' || event.key === 'Escape') {
                event.preventDefault(); event.stopPropagation();
                finish(event.key === 'Enter'); button.focus();
            }
        };
        button.replaceWith(input);
        input.focus(); input.select();
    };
    return button;
}

function getCoverStatusInfo(change) {
    if (getRepairMode() === 'names') return {className:'skipped', label:workbenchText('本次不处理', 'Not requested'), title:workbenchText('仅修复名称，图片保持不变', 'Names only; artwork is unchanged')};
    if (!change.thumbnail_source) {
        if (hasExistingCover(change)) {
            return {
                className: 'exists',
                label: uiText('已有封面 · 缺源'),
                title: currentUILanguage === 'en' ? 'A local cover exists, but cover source is missing' : '本地封面已存在，但缺少封面源'
            };
        }
        if (change.artwork_gallery_status === 'not_found' || change.artwork_gallery_status === 'unavailable') {
            return {className: 'missing',
                label: change.artwork_gallery_status === 'not_found'
                    ? workbenchText('官方图库无', 'Not in gallery') : workbenchText('图库查询失败', 'Gallery unavailable'),
                title: change.artwork_gallery_status === 'not_found'
                    ? workbenchText('官方图库没有这张图。点击“更换图片”搜索备用图库（维基百科），选中后再应用。', 'The official gallery has no image. Use Change artwork to search the alternate source (Wikipedia); pick one, then apply.')
                    : change.match_reason};
        }
        return {
            className: 'missing',
            label: change.artwork_identity_status === 'unresolved' ? workbenchText('名称未识别', 'Title not identified') : uiText('缺少封面源'),
            title: change.artwork_identity_status === 'unresolved' ? workbenchText('请填写英文游戏全名，或在游戏列表中导入本地图片', 'Enter the full English title, or import artwork from the game list') : uiText('缺少封面源')
        };
    }

    if (change.cover_download_status === 'failed') {
        return {
            className: 'failed',
            label: change.cover_download_reason === 'not_found' ? workbenchText('图库未找到', 'No gallery match')
                : change.cover_download_reason === 'network_error' ? workbenchText('网络连接失败', 'Network error') : uiText('下载失败'),
            title: change.cover_download_message || uiText('下载失败')
        };
    }

    if (change.cover_download_status === 'success') {
        return {
            className: 'downloaded',
            label: uiText('已下载'),
            title: currentUILanguage === 'en' ? 'Cover downloaded in this task' : '本次任务已下载封面'
        };
    }

    if (change.cover_download_status === 'skipped-download') {
        return {
            className: 'skipped',
            label: uiText('已跳过下载'),
            title: uiText('跳过下载')
        };
    }

    if (change.thumbnail_exists || change.local_thumbnail_exists || change.cover_exists) {
        return {
            className: 'exists',
            label: uiText('已有封面'),
            title: currentUILanguage === 'en' ? 'A local cover is already available' : '本地已存在可用封面'
        };
    }

    return {
        className: '',
        label: uiText('待下载'),
        title: currentUILanguage === 'en' ? 'Will download when applying selected fixes' : '应用已选修复时下载封面'
    };
}

function getCurrentItemLabel(change) {
    return change?.original_item_label || change?.original_label || uiText('未命名');
}

function getCurrentItemMeta(change) {
    const parsedName = change?.original_label && change.original_label !== change.original_item_label
        ? change.original_label
        : '';
    return [parsedName, change?.path].filter(Boolean).join(' / ');
}

function buildCoverStatusCell(change) {
    const tdCoverStatus = document.createElement('td');
    const coverInfo = getCoverStatusInfo(change);
    const coverStatus = document.createElement('span');
    coverStatus.className = `cover-status${coverInfo.className ? ` ${coverInfo.className}` : ''}`;
    coverStatus.textContent = coverInfo.label;
    coverStatus.title = coverInfo.title;
    tdCoverStatus.appendChild(coverStatus);
    return tdCoverStatus;
}

function refreshPreviewRowState(index) {
    const change = currentChanges[index];
    const row = document.querySelector(`#preview-table-body tr[data-index="${index}"]`);
    if (!change || !row) return;

    const info = getMatchInfo(change);
    row.className = info.rowClass || '';

    const canSelect = isActionableChange(change);
    const isSelected = change.enabled !== false && canSelect;
    const rowCheck = row.querySelector('.row-check');
    if (rowCheck) {
        rowCheck.textContent = isSelected ? '✓' : '';
        rowCheck.setAttribute('aria-checked', String(isSelected));
        rowCheck.setAttribute('aria-disabled', String(!canSelect));
        rowCheck.disabled = !canSelect;
    }

    const statusCell = row.children[2];
    if (statusCell) statusCell.replaceWith(buildStatusCell(info, index));

    const coverCell = row.children[4];
    if (coverCell) coverCell.replaceWith(buildCoverStatusCell(change));
}

function buildStatusCell(info, index) {
    const tdStatus = document.createElement('td');
    const statusStack = document.createElement('div');
    statusStack.className = 'status-stack';
    const statusMainline = document.createElement('div');
    statusMainline.className = 'status-mainline';
    const status = document.createElement('span');
    status.className = 'status-text';
    status.style.color = info.color;
    status.innerHTML = `<span class="status-dot"></span>${info.label}`;
    const reason = getMatchReasonLabel(info, currentChanges[index]);
    if (reason) {
        status.title = reason;
        status.setAttribute('aria-label', info.label + ' · ' + reason);
    }
    statusMainline.appendChild(status);
    statusStack.appendChild(statusMainline);
    const change = currentChanges[index];
    if (isEditedChange(change)) {
        const save = document.createElement('button');
        save.type = 'button'; save.className = 'save-row-override';
        save.dataset.saveOverride = index;
        save.textContent = workbenchText('记住修正', 'Remember correction');
        save.title = workbenchText('保存为本地修正规则', 'Save as a local correction');
        save.disabled = !canSaveOverride(change);
        save.onclick = () => saveChangeOverride(index);
        statusStack.appendChild(save);
    }
    tdStatus.appendChild(statusStack);
    return tdStatus;
}

function setPreviewFilter(filter, target) {
    currentPreviewFilter = filter;
    document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
    if (target) target.classList.add('active');
    renderPreviewTable(currentChanges);
    renderWorkbench();
}

function toggleChangeEnabled(index, control) {
    const change = currentChanges[index];
    if (!change) return;
    hideApplySummary();
    const nextEnabled = change.enabled === false;
    if (nextEnabled && !isActionableChange(change)) {
        showStatus(
            currentUILanguage === 'en'
                ? 'Complete the Chinese name and cover source before selecting this item.'
                : '请先补齐中文名和封面源，再加入应用队列',
            'error'
        );
        return;
    }
    change.enabled = nextEnabled;
    if (control) {
        if (control.matches('button')) {
            control.setAttribute('aria-checked', String(nextEnabled));
            control.textContent = nextEnabled ? '✓' : '';
        } else {
            control.checked = nextEnabled;
        }
    }
    updateSummary(currentChanges);
}

function updateSummary(changes) {
    let matched = 0;
    let ready = 0;
    let review = 0;
    let duplicate = 0;
    let enabled = 0;
    let downloadable = 0;
    let completed = 0;
    changes.forEach(change => {
        const info = getMatchInfo(change);
        const isIncluded = change.enabled !== false && isActionableChange(change);
        if (isIncluded) enabled += 1;
        if (isIncluded && needsCoverDownload(change, info)) downloadable += 1;
        if (isAutoRepairKind(info.kind)) matched += 1;
        if (info.kind === 'ready') ready += 1;
        if (info.kind === 'review') review += 1;
        if (info.kind === 'duplicate') duplicate += 1;
        if (info.kind === 'completed') completed += 1;
    });

    document.getElementById('dock-plan-count').textContent = currentUILanguage === 'en'
        ? `${enabled} ready · ${review} to review`
        : `${enabled} 可应用 · ${review} 待校对`;
    document.getElementById('dock-download-count').textContent = formatPendingDownloadCount(downloadable);
    document.getElementById('repair-summary-inline').textContent = completed
        ? getAppliedSummaryText(completed)
        : getRepairSummaryText(enabled, matched, review, changes.length, ready, completed);
    updateReviewProgress(changes.length, review, enabled, ready, completed);
    setProgressCardTotals(changes.length || 0, 0);
    renderWorkbench();
}

function getAppliedSummaryText(applied) {
    const failed = Number(lastDownloadSummary?.total?.failed) || 0;
    if (failed) return currentUILanguage === 'en'
        ? `${applied} entries processed · ${failed} images failed`
        : `${applied} 项已处理 · ${failed} 张图片失败，需重新补图`;
    if (!lastAppliedWriteNames) return currentUILanguage === 'en' ? `${applied} items processed; names unchanged` : `${applied} 项图片已处理，名称保持不变`;
    return currentUILanguage === 'en'
        ? `${uiText('修复完成')} · ${applied} ${uiText('项已写回')}`
        : `${uiText('修复完成')} · ${applied} ${uiText('项已写回')}`;
}

function getRepairSummaryText(enabled, matched, review, total, ready = 0, completed = 0) {
    if (!total) return uiText('已选 0 项 · 等待游戏库');
    return currentUILanguage === 'en'
        ? `Selected ${enabled} · ${matched} auto repair · ${ready} no repair needed · ${completed} completed · ${review} need information`
        : `已选 ${enabled} 项 · ${matched} 可自动修复 · ${ready} 无需修复 · ${completed} 已完成 · ${review} 待补充信息`;
}

function updateReviewProgress(total, review, enabled, ready = 0, completed = 0) {
    const progressLabel = document.getElementById('inline-progress-label');
    if (!progressLabel) return;
    const busyStates = ['应用中', '处理中', '完成', '失败', '断开', '启动中'];
    if (busyStates.includes(progressLabel.textContent.trim())) return;

    if (!total) {
        setInlineProgress(0, uiText('待处理'), uiText('等待预览校对'), uiText('当前：未开始'));
        return;
    }

    if (review > 0) {
        setInlineProgress(
            20,
            uiText('待确认'),
            currentUILanguage === 'en' ? `Analyzed ${total}` : `已分析 ${total} 项`,
            currentUILanguage === 'en' ? `Current: ${review} need information` : `当前：${review} 项待补充信息`
        );
    } else {
        if (!enabled && ready + completed >= total) {
            setInlineProgress(
                100,
                uiText('无需处理'),
                currentUILanguage === 'en' ? `Analyzed ${total}` : `已分析 ${total} 项`,
                uiText('当前：无需处理')
            );
            return;
        }
        setInlineProgress(
            35,
            uiText('待应用'),
            currentUILanguage === 'en' ? `Analyzed ${total}` : `已分析 ${total} 项`,
            currentUILanguage === 'en' ? `Current: ${enabled} ready to apply` : `当前：${enabled} 项可应用`
        );
    }
}

function toggleFilterBar() {
    const panel = document.querySelector('.main-panel');
    const button = document.getElementById('filter-toggle-btn');
    const compact = panel.classList.toggle('filters-compact');
    button.setAttribute('aria-expanded', String(!compact));
    button.title = compact ? workbenchText('展开筛选项', 'Show more filters') : workbenchText('收起筛选项', 'Show fewer filters');
    showStatus(compact ? '已收起非当前筛选项' : '已展开全部筛选项', 'info');
}

function canSaveOverride(change) {
    return Boolean(change) && isEditedChange(change)
        && Boolean(normalizeDisplayName(change.new_label))
        && Boolean(normalizeDisplayName(change.thumbnail_source));
}

async function saveChangeOverride(index) {
    const change = currentChanges[index];
    if (!canSaveOverride(change)) return;

    const button = document.querySelector(`[data-save-override="${index}"]`);
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
        showStatus(uiText('本地修正规则已保存'), 'success');
    } catch (error) {
        showStatus('保存本地修正规则失败: ' + error.message, 'error');
    } finally {
        const currentButton = document.querySelector(`[data-save-override="${index}"]`);
        if (currentButton) currentButton.disabled = !canSaveOverride(currentChanges[index]);
    }
}
