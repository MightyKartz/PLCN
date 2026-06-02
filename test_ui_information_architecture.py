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
    assert "待下载" in html
    assert "已有封面" in html
    assert "change.thumbnail_source ? '将下载'" not in html
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
    assert "confirmChange" in html
    assert "isEditedChange" in html
    assert "确认当前项" in html
    assert "position: fixed;" in html
    assert "top: 66px;" in html
    assert "right: 6px;" in html
    assert "bottom: 164px" in html
    assert "width: min(365px, calc(100vw - 24px))" in html
    assert "height: min(220px, calc(100vh - 248px))" in html
    assert "details-close-btn" in html
    assert "overflow-y: auto" in html
    assert "任务详情" in html
    assert "progress-modal" not in html
    assert "dock-details-section" not in html
    assert "grid-template-rows: 60px minmax(0, 1fr) 156px" in html
    assert "grid-template-columns: minmax(260px, 286px) minmax(0, 1fr) minmax(300px, 365px)" not in html


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
