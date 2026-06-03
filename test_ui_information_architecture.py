from pathlib import Path


TEMPLATE_PATH = Path("src/templates/plcn.html")


def read_template():
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def test_primary_labels_are_clear():
    html = read_template()

    assert "当前游戏列表" in html
    assert "全部游戏列表" in html
    assert "应用已选修复" in html
    assert "修复状态" in html
    assert "写入名称" in html
    assert "封面源英文名" in html
    assert 'data-i18n="推荐中文名"' not in html
    assert 'data-i18n="官方英文名"' not in html
    assert "需人工确认" in html
    assert "UI：中文" in html
    assert "缺封面源" in html
    assert "已手动编辑" in html
    assert "播放列表" not in html
    assert "重新扫描设备" not in html
    assert "离线可用" not in html
    assert "单项修复" not in html
    assert "批量修复" not in html
    assert "一键修复已选项目" not in html
    assert html.count(">应用已选修复</button>") == 1
    assert "repair-mini-stats" not in html
    assert 'data-i18n="置信度"' not in html
    assert "tdConfidence" not in html
    assert "status-reason" in html
    assert "getMatchReasonLabel" in html
    assert "apply-summary-panel" in html
    assert "buildApplySummary" in html
    assert "确认应用" in html
    assert "directory-details" in html
    assert "目录详情" in html
    assert "library-browser" in html
    assert "playlist-system-tabs" in html
    assert "playlist-list-panel" in html
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
    assert "previewFirstPlaylistForSystem" in html
    assert "setLibraryBrowserVisible" in html
    assert "setLibraryBrowserVisible(false)" not in html
    assert "setLibraryBrowserVisible(true)" in html
    assert html.count('id="scanned-playlists"') == 1
    assert "flex-wrap: nowrap" in html
    assert "sr-only" in html
    assert "iconOnlyButton" in html
    assert "invertVisibleSelection" in html
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
    assert "inline-size: 20px !important" in html
    assert "block-size: 20px !important" in html
    assert "stroke-width: 1.75" in html
    assert "shape-rendering: geometricPrecision" in html
    assert "border: 0 !important" in html
    assert "vector-effect: non-scaling-stroke" in html
    assert "getSystemAbbreviation(groupName)" in html
    assert "previewFirstPlaylistForSystem(groupName)" in html
    assert "'N64'" in html
    assert "'NDS'" in html
    assert "'Wii'" in html
    assert "<colgroup>" in html
    assert "col-current" in html
    assert "min-width: 960px" in html
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
    assert 'id="summary-ready"' in html
    assert 'id="summary-completed"' in html
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
    assert "findBoxartDownloadResult" in html
    assert "match_status = 'applied'" in html
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
    assert "markChangeEdited(index, '手动编辑显示名称', 'new_label')" in html
    assert "markChangeEdited(index, '手动编辑封面源', 'thumbnail_source')" in html
    assert "已下载" in html
    assert "下载失败" in html
    assert "已跳过下载" in html
    assert "change.thumbnail_source ? '将下载'" not in html
    assert "img.src = buildThumbnailUrl(system, change.thumbnail_source)" not in html
    assert "getDefaultSearchQuery" in html
    assert "getFileStem" in html
    assert "normalizeSearchQuery" in html
    assert "if (defaultQuery) performSearch()" in html
    assert 'id="search-selected-thumb-btn"' in html
    assert "grid-template-columns: minmax(0, 1fr) 34px 34px" in html
    assert "Select a game before searching." in html


def test_inspector_and_details_are_on_demand():
    html = read_template()

    assert '<div class="app-shell inspector-hidden">' in html
    assert 'class="details-drawer"' in html
    assert "toggleDetailsDrawer" in html
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
    assert "top: 66px;" in html
    assert "right: 6px;" in html
    assert "--bottom-dock-height: 104px" in html
    assert "bottom: calc(var(--bottom-dock-height) + 8px)" in html
    assert "width: min(365px, calc(100vw - 24px))" in html
    assert "height: min(220px, calc(100vh - var(--bottom-dock-height) - 92px))" in html
    assert "details-close-btn" in html
    assert "overflow-y: auto" in html
    assert "任务详情" in html
    assert "progress-modal" not in html
    assert "dock-details-section" not in html
    assert "grid-template-rows: 60px minmax(0, 1fr) var(--bottom-dock-height)" in html
    assert ".dock-flow {\n            display: none;" in html
    assert "grid-template-columns: minmax(260px, 286px) minmax(0, 1fr) minmax(300px, 365px)" not in html


def test_search_results_are_clickable_rows():
    html = read_template()

    assert "renderSearchResults" in html
    assert "search-result-row" in html
    assert "search-results-table" in html
    assert "row.addEventListener('click'" in html
    assert "row.addEventListener('keydown'" in html
    assert "onclick=\"selectSearchResult" not in html


def test_dark_theme_active_states_are_restrained():
    html = read_template()

    assert "--dark-active-bg: #18263a" in html
    assert "--dark-active-border: #2f486a" in html
    assert "--dark-selected-bg: #172536" in html
    assert "--dark-selected-rail: #5f8fd4" in html
    assert "--dark-focus-ring: rgba(95, 143, 212, 0.2)" in html
    assert "body[data-theme=\"dark\"] .filter-btn.active" in html
    assert "body[data-theme=\"dark\"] .playlist-system-tab.active" in html
    assert "box-shadow: inset 3px 0 0 var(--dark-selected-rail), inset 0 0 0 1px var(--dark-selected-border)" in html
    assert "body[data-theme=\"dark\"] .mini-btn:hover" in html
    assert "body[data-theme=\"dark\"] .badge.warning" in html
    assert "inset 5px 0 0 var(--primary), inset 0 0 0 2px #4f86d5" not in html
