/* Repair proposals, match classification and writeback reconciliation. */

function preparePreviewChanges(changes) {
    return (changes || []).map(original => {
        const change = { ...original };
        // The server candidates already obey known region, disc and revision constraints.
        // This chooses artwork for preview; it does not assert the ROM's unknown revision.
        if (getRepairMode() !== 'names' && !change.thumbnail_source
                && change.artwork_identity_status === 'resolved' && change.artwork_gallery_status === 'ambiguous'
                && change.artwork_candidates?.length && !change.identity?.requires_review) {
            const ranked = [...change.artwork_candidates].sort((a, b) => {
                const region = name => /\(Japan\)/i.test(name) ? 0 : /\(USA\)/i.test(name) ? 1 : 2;
                return region(a) - region(b) || a.localeCompare(b, 'en', {numeric: true});
            });
            change.thumbnail_source = ranked[0];
            change.artwork_recommended = true;
            change.match_reason = '已推荐匹配封面，可单独更换；确认应用后下载';
        }
        if (getRepairMode() === 'names' && (!change.needs_review || change.artwork_review_only) && (['matched', 'rename', 'ready', 'download'].includes(change.match_status) || change.artwork_review_only)) {
            change.match_status = currentMatchesWriteName(change) ? 'ready' : 'rename';
            change.match_reason = '仅修复名称；此次不下载图片';
        }
        if (getRepairMode() === 'artwork') {
            change.new_label = change.original_item_label || change.original_label;
            change.artwork = null;
            clearCoverState(change);
            if (!change.needs_review && ['matched', 'rename', 'ready', 'download'].includes(change.match_status) && change.thumbnail_source) {
                change.match_status = 'download';
                change.match_reason = '保留当前名称，检查并补全三类图片（已有有效图片会跳过）';
            }
        }
        return { ...change, enabled: shouldAutoSelectChange(change) };
    });
}

function getIncludedChanges() {
    return currentChanges.filter(change => change.enabled !== false && isActionableChange(change));
}

function getChangeIdentity(change) {
    if (!change) return '';
    if (change.proposal_id) return String(change.proposal_id);
    return [
        change.index,
        change.path,
        change.original_item_label,
        change.original_label
    ].map(value => String(value || '').trim()).join('|');
}

function writebackMatchesChange(record, change) {
    if (!record || !change) return false;
    if (record.proposal_id && change.proposal_id) {
        return String(record.proposal_id) === String(change.proposal_id);
    }
    const sameIndex = record.index === undefined || change.index === undefined
        ? true
        : Number(record.index) === Number(change.index);
    const samePath = !record.path || !change.path
        ? true
        : normalizeDownloadKey(record.path) === normalizeDownloadKey(change.path);
    return sameIndex && samePath;
}

function findWritebackRecord(change, records = []) {
    return (records || []).find(record => writebackMatchesChange(record, change)) || null;
}

function markWritebackProblem(change, record, fallbackReason) {
    change.review_confirmed = false;
    change.applied = false;
    change.match_status = 'review';
    change.match_score = 0;
    change.match_source = 'writeback';
    change.match_reason = record?.reason || fallbackReason;
    change.needs_review = true;
    change.enabled = false;
    change.cover_download_status = '';
    change.cover_download_message = '';
}

function rememberAppliedChanges(changes, options) {
    lastAppliedChangeKeys = new Set((changes || []).map(getChangeIdentity).filter(Boolean));
    lastAppliedDownloadEnabled = options?.download_thumbnails !== false;
    lastAppliedWriteNames = options?.write_names !== false;
}

function normalizeDownloadKey(value) {
    return String(value || '').trim().toLowerCase();
}

function normalizeDisplayName(value) {
    return String(value || '').trim().replace(/\s+/g, ' ');
}

function hasChineseDisplayName(value) {
    return /[\u4e00-\u9fff]/.test(String(value || ''));
}

function currentMatchesWriteName(change) {
    const current = normalizeDisplayName(change?.original_item_label || change?.original_label);
    const writeName = normalizeDisplayName(change?.new_label);
    return Boolean(current && writeName && current === writeName);
}

function clearCoverState(change) {
    change.thumbnail_exists = false;
    change.local_thumbnail_exists = false;
    change.cover_exists = false;
    change.cover_path = '';
    change.cover_preview_url = '';
    change.cover_download_status = '';
    change.cover_download_message = '';
    change.cover_download_reason = '';
    change.artwork_blocked = false;
    change.artwork_message = '';
}

function findBoxartDownloadResult(change, summary) {
    const details = summary?.details || [];
    const sourceKey = normalizeDownloadKey(change.thumbnail_source);
    const labelKey = normalizeDownloadKey(change.new_label);
    return details.find(item => {
        if (item?.type !== 'Named_Boxarts') return false;
        const itemSource = normalizeDownloadKey(item.source);
        const itemGame = normalizeDownloadKey(item.game);
        return (sourceKey && itemSource === sourceKey) || (labelKey && itemGame === labelKey);
    }) || null;
}

function hasExistingCover(change) {
    return Boolean(change?.thumbnail_exists || change?.local_thumbnail_exists || change?.cover_exists);
}

function isAutoRepairKind(kind) {
    return ['matched', 'download', 'rename'].includes(kind);
}

function isActionableChange(change) {
    return isAutoRepairKind(getMatchInfo(change).kind)
        || (getMatchInfo(change).kind === 'reviewed' && Boolean(String(change.new_label || '').trim()));
}

function shouldAutoSelectChange(change) {
    return change.enabled !== false && isActionableChange(change);
}

function needsCoverDownload(change, info = getMatchInfo(change)) {
    if (change.artwork && change.thumbnail_source) {
        return Object.values(change.artwork).some(item => item.status !== 'exists');
    }
    return ['matched', 'download', 'reviewed'].includes(info.kind) && !hasExistingCover(change) && Boolean(change.thumbnail_source);
}

function applyCompletedJobToPreview(result) {
    if (!currentChanges.length || !lastAppliedChangeKeys.size) return;

    const summary = result?.download_summary || null;
    const writeback = summary?.writeback || {};
    const appliedRecords = writeback.applied || [];
    const failedRecords = writeback.failed || [];
    const skippedRecords = writeback.skipped || [];
    const hasWriteback = Boolean(summary?.writeback);
    currentChanges.forEach(change => {
        if (!lastAppliedChangeKeys.has(getChangeIdentity(change))) return;

        const failedRecord = findWritebackRecord(change, failedRecords);
        if (failedRecord) {
            markWritebackProblem(change, failedRecord, 'readback_mismatch');
            return;
        }

        const skippedRecord = findWritebackRecord(change, skippedRecords);
        if (skippedRecord) {
            markWritebackProblem(change, skippedRecord, 'skipped');
            return;
        }

        const appliedRecord = findWritebackRecord(change, appliedRecords);
        if (hasWriteback && !appliedRecord) {
            markWritebackProblem(change, null, 'not_applied');
            return;
        }

        if (appliedRecord?.new_label) change.new_label = appliedRecord.new_label;
        change.name_applied = change.name_applied || lastAppliedWriteNames;
        change.applied = !lastAppliedDownloadEnabled;
        change.match_status = change.applied ? 'applied' : 'download';
        change.match_score = 100;
        change.match_source = 'applied';
        change.match_reason = uiText('已写入 playlist');
        change.needs_review = false;
        change.enabled = false;
        change.original_item_label = change.new_label || change.original_item_label;
        if (change.original_item_snapshot) change.original_item_snapshot = {...change.original_item_snapshot, label: change.original_item_label};
        if (appliedRecord?.actual_index !== undefined) change.index = appliedRecord.actual_index;

        if (!change.thumbnail_source) return;

        if (!lastAppliedDownloadEnabled) {
            change.cover_download_status = 'skipped-download';
            return;
        }

        const imageResults = (summary?.details || []).filter(detail => detail.game === change.new_label && detail.system === change.system);
        change.artwork ||= {};
        for (const kind of ['Named_Boxarts', 'Named_Snaps', 'Named_Titles']) {
            const detail = imageResults.find(detail => detail.type === kind);
            if (detail) change.artwork[kind] = {
                status: detail.status === 'success' || (detail.status === 'skipped' && detail.path) ? 'exists' : 'failed',
                path: detail.path || null, message: detail.message || ''
            };
            else change.artwork[kind] ||= {status:'missing'};
        }
        change.applied = Object.values(change.artwork).every(image => image.status === 'exists');
        change.artwork_message = [...new Set(imageResults.filter(detail => detail.status === 'failed').map(detail => detail.message).filter(Boolean))].join(' · ');
        change.artwork_blocked = imageResults.some(detail => detail.reason === 'filename_collision'
            || (detail.reason === 'not_found' && detail.type === 'Named_Boxarts'));
        change.match_status = change.applied ? 'applied' : change.artwork_blocked ? 'review' : 'download';
        change.enabled = !change.applied && !change.artwork_blocked;
        change.needs_review = change.artwork_blocked;
        const boxartResult = findBoxartDownloadResult(change, summary);
        if (!boxartResult) return;

        change.cover_download_status = boxartResult.status;
        change.cover_download_message = boxartResult.message || '';
        change.cover_download_reason = boxartResult.reason || '';
        if (boxartResult.status === 'success' || boxartResult.status === 'skipped') {
            const coverPath = boxartResult.cover_path || boxartResult.path || '';
            change.thumbnail_exists = true;
            change.local_thumbnail_exists = true;
            change.cover_exists = true;
            change.cover_path = coverPath;
            change.cover_preview_url = boxartResult.cover_preview_url || (coverPath ? `/api/thumbnail/preview?path=${encodeURIComponent(coverPath)}` : '');
        }
    });

    updateSummary(currentChanges);
    renderPreviewTable(currentChanges);
}

function matchesFilter(change, query) {
    const info = getMatchInfo(change);
    const matchesQuery = !query || [
        change.original_item_label,
        change.original_label,
        change.new_label,
        change.thumbnail_source,
        change.path
    ].some(value => (value || '').toLowerCase().includes(query));

    if (!matchesQuery) return false;
    if (currentPreviewFilter === 'review') return ['review', 'duplicate'].includes(info.kind);
    if (currentPreviewFilter === 'duplicate') return info.kind === 'duplicate';
    if (currentPreviewFilter === 'matched') return isActionableChange(change);
    if (currentPreviewFilter === 'ready') return info.kind === 'ready';
    if (currentPreviewFilter === 'completed') return info.kind === 'completed';
    if (currentPreviewFilter === 'missing-cover') return ['partial','choose_version','no_source','unidentified','query_failed','failed'].includes(previewArtworkState(change, getRepairMode()));
    if (currentPreviewFilter === 'edited') return isEditedChange(change);
    return true;
}

function isEditedChange(change) {
    return Boolean(
        change.pending_override || change.match_source === 'manual-edit' || change.match_source === 'manual'
    );
}

function reclassifyEditedChange(change, reason) {
    change.review_confirmed = false;
    change.artwork = null;
    change.match_status = 'review';
    change.match_score = 72;
    change.match_source = 'manual-edit';
    change.match_reason = reason;
    change.needs_review = true;
    change.pending_override = true;
    change.enabled = isActionableChange(change);
}

function markChangeEdited(index, reason, editedKey = '') {
    const change = currentChanges[index];
    if (!change) return;
    if (editedKey === 'new_label' || editedKey === 'both') { change.name_applied = false; change.identity_name_edited = true; }
    change.applied = false;
    const coverStillTargetsCurrentName = currentMatchesWriteName(change);
    if (editedKey === 'thumbnail_source' || editedKey === 'both' || (editedKey === 'new_label' && !coverStillTargetsCurrentName)) {
        clearCoverState(change);
    } else {
        change.cover_download_status = '';
        change.cover_download_message = '';
    }
    if (editedKey === 'thumbnail_source' || editedKey === 'both') {
        change.artwork_recommended = false;
        change.artwork_query = '';
        change.artwork_gallery_status = '';
    }
    reclassifyEditedChange(change, reason);
}

function getMatchReasonLabel(info, change) {
    if (!change) return info.reason || '';
    if (change.applied || change.match_status === 'applied') return uiText('已写入 playlist');
    if (change.identity?.requires_review && !change.identity_name_edited) return previewIdentityLabel(change) + ' · ' + (change.match_reason || '');
    if (change.name_applied) return workbenchText('名称已写入，图片尚未全部完成。', 'Names saved; artwork is incomplete. ') + (change.artwork_message || '');
    if (change.pending_override || info.source === 'manual-edit') {
        return [uiText('待保存本地修正'), change.match_reason || info.reason || ''].filter(Boolean).join(' · ');
    }
    if (getRepairMode() === 'names' && ['rename', 'ready'].includes(info.kind)) return workbenchText('仅检查显示名称，图片保持不变', 'Only display names are checked; artwork is unchanged');
    if (!change.thumbnail_source && change.artwork_gallery_status === 'not_found') return workbenchText('名称已识别，可搜索图库或导入本地图片', 'Title identified. Search the library or import an image');
    if (!change.thumbnail_source && change.artwork_gallery_status === 'unavailable') return workbenchText('名称已识别，请重试图库查询', 'Title identified. Retry the gallery search');
    if (getRepairMode() === 'artwork') return ['review', 'duplicate'].includes(info.kind)
        ? workbenchText('图片来源需核对，当前名称保持不变', 'Review the artwork source; current names are preserved')
        : workbenchText('检查并补全图片，当前名称保持不变', 'Check and complete artwork; current names are preserved');
    if (info.kind === 'ready') return uiText('中文名、封面源和封面已就绪');
    if (info.kind === 'download') return uiText('中文名和封面源已就绪，仅需下载封面');
    if (info.kind === 'rename') return uiText('封面已存在，仅需写入中文名');
    if (info.kind === 'duplicate') return uiText('发现重复条目');

    const current = getCurrentItemLabel(change);
    const label = change.new_label || '';
    const thumb = change.thumbnail_source || '';
    const hasChinese = hasChineseDisplayName(label);

    if (info.kind === 'review') {
        if (info.source === 'backend-missing') return uiText('后端状态缺失');
        if (!hasChinese) return uiText('缺少中文名');
        if (!thumb) return uiText('缺少封面源');
        if (normalizeDisplayName(current) && normalizeDisplayName(label) && normalizeDisplayName(current) === normalizeDisplayName(label)) return uiText('名称未变化');
        if (info.source === 'backend') return uiText('后端建议需复核');
        return uiText('低置信匹配');
    }

    if (info.kind === 'matched') return uiText('将写入中文名并下载封面');
    return info.reason || '';
}

function getMatchInfo(change) {
    if (change.match_status) {
        const statusMap = {
            matched: { label: uiText('修复并下载'), badgeClass: 'success', rowClass: '', color: 'var(--green)', fallbackScore: 96 },
            download: { label: uiText('仅下载封面'), badgeClass: 'success', rowClass: '', color: 'var(--green)', fallbackScore: 94 },
            rename: { label: uiText('仅改中文名'), badgeClass: 'success', rowClass: '', color: 'var(--green)', fallbackScore: 96 },
            ready: { label: uiText('无需修复'), badgeClass: 'ready', rowClass: 'row-ready', color: 'var(--muted)', fallbackScore: 100 },
            review: { label: uiText('待补充信息'), badgeClass: 'warning', rowClass: 'row-warning', color: 'var(--amber)', fallbackScore: 72 },
            duplicate: { label: uiText('重复需处理'), badgeClass: 'danger', rowClass: 'row-danger', color: 'var(--red)', fallbackScore: 99 },
            applied: { kind: 'completed', label: uiText('已完成'), badgeClass: 'success', rowClass: '', color: 'var(--green)', fallbackScore: 100 }
        };
        const action = repairActionStatus(change, getRepairMode());
        const actionKind = action === 'incomplete' ? 'review' : action;
        const status = statusMap[actionKind] || statusMap.review;
        const nameReady = currentMatchesWriteName(change) && hasChineseDisplayName(change.new_label);
        const score = Number(change.match_score);
        return {
            kind: status.kind || actionKind,
            confidence: Number.isFinite(score) ? Math.max(0, Math.min(100, Math.round(score))) : status.fallbackScore,
            label: change.identity?.requires_review && !change.identity_name_edited ? previewIdentityLabel(change)
                : nameReady && ['download', 'incomplete'].includes(action) ? workbenchText('名称完成 · 图片待补全', 'Names saved · Artwork pending')
                : action === 'incomplete' ? (change.artwork_identity_status === 'resolved' || (change.identity && !change.identity.requires_review)
                ? workbenchText('待补充图片', 'Artwork needed') : workbenchText('待补充名称或图片源', 'Name or artwork source missing')) : status.label,
            badgeClass: status.badgeClass,
            rowClass: status.rowClass,
            color: nameReady && ['download', 'incomplete'].includes(action) ? 'var(--amber)' : status.color,
            reason: change.match_reason || status.label,
            source: change.match_source || 'backend'
        };
    }

    return {
        kind: 'review',
        confidence: 0,
        label: uiText('待补充信息'),
        badgeClass: 'warning',
        rowClass: 'row-warning',
        color: 'var(--amber)',
        reason: uiText('后端状态缺失'),
        source: 'backend-missing'
    };
}

function getCoverPreviewUrl(change) {
    if (!change) return '';
    if (change.cover_preview_url) return change.cover_preview_url;
    if (hasExistingCover(change) && change.cover_path) {
        return `/api/thumbnail/preview?path=${encodeURIComponent(change.cover_path)}`;
    }
    if (change.artwork_candidates?.length && !['unavailable', 'not_found'].includes(change.artwork_gallery_status)) {
        const source = change.thumbnail_source || change.artwork_candidates[0];
        if (change.artwork_candidates.includes(source)) {
            return '/api/artwork/thumbnail?system=' + encodeURIComponent(change.system)
                + '&kind=' + encodeURIComponent(change.artwork_source_confirmed ? 'Named_Boxarts' : change.artwork_cover_fallback || 'Named_Boxarts') + '&name=' + encodeURIComponent(source);
        }
    }
    return getRemoteCoverUrl(change);
}

function getCoverPreviewSourceLabel(change) {
    if (!change) return '等待封面源';
    if (change.cover_preview_url || (hasExistingCover(change) && change.cover_path)) {
        return change.cover_path || uiText('本地');
    }
    return getRemoteCoverUrl(change) || '等待封面源';
}

function getRemoteCoverUrl(change) {
    const source = change?.thumbnail_source;
    if (!source) return '';
    const system = document.getElementById('system_name').value || change.system || '';
    return buildThumbnailUrl(system, source, change.artwork_source_confirmed ? 'Named_Boxarts' : change.artwork_cover_fallback || 'Named_Boxarts');
}

function buildThumbnailUrl(system, source, kind = 'Named_Boxarts') {
    const filename = sanitizeFilename(source) + '.png';
    return `https://thumbnails.libretro.com/${encodeURIComponent(system)}/${encodeURIComponent(kind)}/${encodeURIComponent(filename)}`;
}

function sanitizeFilename(name) {
    return (name || '').replace(/[&*/:`<>?\\|"\x00-\x1f]/g, '_');
}
