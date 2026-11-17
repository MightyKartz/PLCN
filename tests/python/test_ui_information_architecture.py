from pathlib import Path
import re


TEMPLATE_PATH = Path("src/templates/plcn.html")


def read_template():
    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    assets = re.findall(r'(?:src|href)="/assets/([^"/]+)"', html)
    return html + "\n" + "\n".join(
        (TEMPLATE_PATH.parent / name).read_text(encoding="utf-8") for name in assets
    )


def test_primary_labels_are_clear():
    html = read_template()

    assert 'data-i18n="一键补全"' in html
    assert 'id="batch-review-button"' not in html
    assert 'onclick="startCompletion()"' in html
    assert 'library-all-systems' in html
    assert 'selectAllLibrarySystems' in html
    assert 'runAllSystemsCompletion' in html
    assert 'id="batch-run-cancel"' in html
    assert 'id="batch-review-apply"' not in html
    assert 'batch-write-names' not in html
    assert html.index('id="batch-review-status"') < html.index('id="batch-review-rows"')
    assert "全部游戏列表" not in html
    assert "应用已选修复" in html
    assert "修复状态" in html
    assert "封面源英文名" in html
    assert 'data-i18n="推荐中文名"' not in html
    assert 'data-i18n="官方英文名"' not in html
    assert "待补充名称或图片源" in html
    assert "需人工确认" not in html
    assert "UI：中文" in html
    assert "缺封面源" in html
    assert "已手动编辑" in html
    assert "播放列表" not in html
    assert "重新扫描设备" not in html
    assert "离线可用" not in html
    assert "单项修复" not in html
    assert "批量修复" not in html
    assert "一键修复已选项目" not in html
    assert html.count(">确认应用</button>") == 1
    assert 'id="confirm-apply-button"' not in html
    assert "applyChanges(true)" not in html
    assert "repair-mini-stats" not in html
    assert 'data-i18n="置信度"' not in html
    assert "tdConfidence" not in html
    assert "status.title = reason" in html
    assert "getMatchReasonLabel" in html
    assert "apply-summary-panel" in html
    assert "buildApplySummary" in html
    assert "确认应用" in html
    assert "directory-details" in html
    assert "目录详情" in html
    assert "library-browser" in html
    assert "playlist-system-tabs" in html
    assert "playlist-list-panel" not in html
    assert "container.appendChild(panel)" not in html
    assert "has-preview" in html
    assert "selectedLibrarySystem" in html
    assert "buildPlaylistCard" in html
    assert "getPlaylistSystemName" in html
    assert "getSystemAbbreviation" in html
    assert "getCurrentItemLabel" in html
    assert "getCurrentItemMeta" in html
    assert "normalizeDisplayName" in html
    assert "currentMatchesWriteName" in html
    assert "reclassifyEditedChange" in html
    assert "frontend-fallback" not in html
    assert "backend-missing" in html
    assert "manual-edit" in html
    assert "保存为本地修正规则" in html
    assert "/api/overrides/save" in html
    assert "待保存本地修正" in html
    assert "pending_override" in html
    assert "&& isEditedChange(change)" in html
    assert "重新预览后应用" in html
    assert "savedChange.enabled = false" in html
    assert "selectFirstPlaylistForSystem" in html
    assert "setLibraryBrowserVisible" in html
    assert "setLibraryBrowserVisible(false)" not in html
    assert "setLibraryBrowserVisible(true)" in html
    assert html.count('id="scanned-playlists"') == 1
    assert "flex-wrap: nowrap" in html
    assert "sr-only" in html
    assert "iconOnlyButton" in html
    assert "invertVisibleSelection" not in html
    assert "ui-language-icon" in html
    assert "theme-toggle-icon" in html
    assert "getLanguageIconSvg" in html
    assert "getThemeIconSvg" in html
    assert 'data-icon="ui-to-en"' in html
    assert 'data-icon="ui-to-zh"' in html
    assert 'data-icon="theme-to-dark"' in html
    assert 'data-icon="theme-to-light"' in html
    assert 'data-icon="ui-en"' not in html
    assert "M5 19 10 5l5 14" not in html
    assert "M18.5 5v14" not in html
    assert 'width="20" height="20" viewBox="0 0 24 24" preserveAspectRatio="xMidYMid meet"' in html
    assert "inline-size: 20px;" in html
    assert "block-size: 20px;" in html
    assert "stroke-width: 1.75" in html
    assert "shape-rendering: geometricPrecision" in html
    assert "border: 0;" in html
    assert "vector-effect: non-scaling-stroke" in html
    assert "getSystemAbbreviation(groupName)" in html
    assert "selectFirstPlaylistForSystem(groupName)" in html
    assert "'N64'" in html
    assert "'NDS'" in html
    assert "'Wii'" in html
    assert "<colgroup>" in html
    assert "col-current" in html
    assert "min-width: 800px" in html
    assert "overflow-x: auto" in html
    assert '<th style="width:' not in html
    assert 'class="cn-name-col" style=' not in html
    assert 'class="en-name-col" style=' not in html
    assert "getCoverStatusInfo" in html
    assert "getCoverPreviewUrl" in html
    assert "change.cover_preview_url" in html
    assert "/api/thumbnail/preview" in html
    assert "待下载" in html
    assert "已有封面" in html
    assert "无需修复" in html
    assert "仅下载封面" in html
    assert "仅改中文名" in html
    assert "修复并下载" in html
    assert "已完成" in html
    assert 'class="filter-count"' in html
    assert 'id="summary-ready"' not in html
    assert 'id="summary-completed"' not in html
    assert 'data-filter="ready"' in html
    assert 'data-filter="completed"' in html
    assert "shouldAutoSelectChange" in html
    assert "isActionableChange" in html
    assert "refreshPreviewRowState" in html
    assert "buildCoverStatusCell" in html
    assert "getIncludedChanges() {" in html
    assert "change.enabled !== false && isActionableChange(change)" in html
    assert "change.match_status !== 'ready'" not in html
    assert "applyCompletedJobToPreview" in html
    assert "rememberAppliedChanges" in html
    assert "findWritebackRecord" in html
    assert "writeback.applied" in html
    assert "writeback.failed" in html
    assert "writeback.skipped" in html
    assert "findBoxartDownloadResult" in html
    assert "change.applied = Object.values(change.artwork).every" in html
    assert "match_source = 'writeback'" in html
    assert "change.original_item_label = change.new_label || change.original_item_label" in html
    assert "kind: 'completed'" in html
    assert "label: uiText('已完成')" in html
    assert "label: uiText('无需修复')" in html
    assert "label: uiText('仅下载封面')" in html
    assert "label: uiText('仅改中文名')" in html
    assert "label: uiText('修复并下载')" in html
    assert "cover_download_status === 'success'" in html
    assert "cover_download_status === 'failed'" in html
    assert "boxartResult.cover_path || boxartResult.path" in html
    assert "boxartResult.cover_preview_url" in html
    assert "buildPreviewEditor" in html
    assert "手动编辑显示名称" in html
    assert "手动编辑封面源" in html
    assert "已下载" in html
    assert "下载失败" in html
    assert "已跳过下载" in html
    assert "change.thumbnail_source ? '将下载'" not in html
    assert "img.src = buildThumbnailUrl(system, change.thumbnail_source)" not in html
    assert "getDefaultSearchQuery" not in html
    assert "getFileStem" not in html
    assert "normalizeSearchQuery" not in html
    assert "performSearch" not in html
    assert 'id="search-selected-thumb-btn"' not in html
    assert "openArtworkForSelected" not in html
    assert "Select a game before searching." not in html


def test_legacy_overlays_removed_and_task_details_live_in_settings():
    html = read_template()

    assert 'id="inspector-panel"' not in html
    assert 'inspector.js' not in html
    assert 'workflow-strip' not in html
    assert 'selectPreviewRow' not in html
    assert 'id="organize-menu"' not in html
    assert 'id="option-write-names"' in html
    assert 'id="option-download-artwork"' in html
    assert 'id="batch-review-dialog"' in html
    assert '/api/batch/preview' in html
    assert 'preview_job_id: started.job_id' in html
    assert 'saveChangeOverride(index)' in html
    assert 'class="details-drawer"' not in html
    assert 'class="bottom-dock"' not in html
    assert 'renderTaskDetails' in html
    assert 'task-result-table' in html
    assert 'data-i18n="查看任务"' in html
    assert 'id="artwork-preview"' not in html
    assert "toggleDetailsDrawer" not in html
    assert "toggleTheme" in html
    assert "toggleUILanguage" in html
    assert "isEditedChange" in html
    assert "确认应用" in html
    assert "confirmChange" not in html
    assert "confirmSelectedChange" not in html
    assert "confirm-row-btn" not in html
    assert "confirm-selected-btn" not in html
    assert "确认当前项" not in html
    assert "修复状态 / 确认" not in html
    assert "manual-confirmed" not in html
    assert "change.confirmed" not in html
    assert "position: fixed;" in html
    assert "overflow-y: auto" in html
    assert "progress-modal" not in html
    assert "dock-details-section" not in html
    assert "grid-template-columns: minmax(260px, 286px) minmax(0, 1fr) minmax(300px, 365px)" not in html


def test_legacy_name_search_workbench_is_removed():
    html = read_template()

    assert 'id="search-modal"' not in html
    assert 'id="docs-modal"' not in html
    assert "openProjectDocs" not in html
    assert "closeProjectDocs" not in html
    assert "database-status-chip" not in html
    assert "dat-status-chip" not in html
    assert "loadStats" not in html
    assert "openSearchModal" not in html
    assert "search-results-table" not in html
    assert "openArtworkForSelected" not in html
    assert "openArtworkDialog({index: change.index" in html


def test_dark_theme_active_states_are_restrained():
    html = read_template()

    assert "--dark-active-bg: #18263a" in html
    assert "--dark-active-border: #2f486a" in html
    assert "--dark-selected-bg: #172536" in html
    assert "--dark-selected-rail: #5f8fd4" in html
    assert "--dark-focus-ring: rgba(95, 143, 212, 0.2)" in html
    assert "body[data-theme=\"dark\"] .filter-btn.active" in html
    assert "body[data-theme=\"dark\"] .playlist-system-tab.active" in html
    assert ".preview-table tr.selected" not in html
    assert "body[data-theme=\"dark\"] .badge.warning" in html
    assert "inset 5px 0 0 var(--primary), inset 0 0 0 2px #4f86d5" not in html
