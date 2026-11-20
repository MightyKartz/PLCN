/* File browsing works independently of the selected RetroArch library. */
let gameFilesView = null;
let gameFilesClipboard = null;
let fileChanges = {root: '', items: []};

function recordFileChange(root, entry) {
    if (fileChanges.root !== root) fileChanges = {root, items: []};
    fileChanges.items.push(entry);
    renderFileSyncNotice();
}

function dismissFileChanges() {
    fileChanges = {root: fileChanges.root, items: []};
    renderFileSyncNotice();
}

function renderFileSyncNotice() {
    const notice = document.getElementById('game-sync-notice');
    if (!notice) return;
    const root = document.getElementById('retroarch_root')?.value || '';
    const count = fileChanges.root === root ? fileChanges.items.length : 0;
    notice.hidden = !count;
    if (!count) { notice.replaceChildren(); return; }
    notice.replaceChildren(
        wbElement('span', '', workbenchText(`文件管理中有 ${count} 项改动未同步到列表。`, `${count} file change(s) from the file manager are not synced to playlists.`)),
        gmButton('更新列表…', 'Update playlists…', openFileSyncDialog, false),
        gmButton('忽略', 'Dismiss', dismissFileChanges));
}

async function openFileSyncDialog() {
    const items = fileChanges.items, root = fileChanges.root;
    if (!items.length || workbench.operation) return;
    if (!beginWorkbenchOperation('game-file-sync')) {
        showStatus(workbenchText('请等待当前任务完成。', 'Wait for the current task.'), 'error');
        return;
    }
    const tr = workbenchText;
    const dialog = wbElement('dialog', 'desktop-confirm app-dialog game-file-sync-dialog');
    const heading = wbElement('h2', '', tr('同步文件改动到列表', 'Sync file changes to playlists'));
    heading.id = 'game-file-sync-title';
    dialog.setAttribute('aria-labelledby', heading.id);
    const impact = wbElement('div', 'game-file-delete-impact');
    const message = wbElement('p', '', '');
    message.setAttribute('role', 'status');
    const cancel = gmButton('关闭', 'Close', () => dialog.close());
    const confirm = gmButton('更新列表', 'Update playlists', apply, false);
    confirm.disabled = true;
    let previewId;
    dialog.append(heading, impact, message, cancel, confirm);
    document.body.append(dialog);
    dialog.addEventListener('close', () => { endWorkbenchOperation(); dialog.remove(); }, {once:true});
    dialog.showModal();
    cancel.focus();
    runPreview();

    function list(zh, en, entries) {
        if (!entries.length) return;
        const rows = wbElement('ul', '');
        rows.append(...entries.map(entry => wbElement('li', '', entry)));
        impact.append(wbElement('h3', '', tr(zh, en)), rows);
    }

    async function runPreview() {
        try {
            const {id, result} = await runGameJob('/api/game-files/sync-preview', {root, changes: items},
                state => { if (state.connectionError || currentUILanguage !== 'en') message.textContent = state.message; });
            previewId = id;
            list('将改写的列表条目', 'Playlist entries to update',
                 result.renamed.map(entry => entry.playlist + ' · ' + entry.label + ' → ' + entry.new));
            list('将移出的列表条目', 'Playlist entries to remove',
                 result.removed.map(entry => entry.playlist + ' · ' + entry.label));
            list('未匹配到条目的改动', 'Changes with no matching entry', result.unmatched);
            const total = result.renamed.length + result.removed.length;
            message.textContent = total
                ? tr(`将更新 ${result.renamed.length} 条、移出 ${result.removed.length} 条列表条目；修改前会保存列表备份。`,
                     `${result.renamed.length} entries will be updated and ${result.removed.length} removed. Playlists are backed up first.`)
                : tr('没有需要更新的列表条目。', 'No playlist entries need updating.');
            confirm.disabled = !total;
        } catch (error) {
            message.textContent = gmError(error);
        }
    }

    async function apply() {
        if (!previewId) return;
        confirm.disabled = cancel.disabled = true;
        try {
            const {result} = await runGameJob('/api/game-files/sync-apply', {preview_job_id: previewId},
                state => { if (state.connectionError || currentUILanguage !== 'en') message.textContent = state.message; });
            await refreshDeletedPlaylists(result.playlists);
            dismissFileChanges();
            dialog.close();
        } catch (error) {
            message.textContent = gmError(error);
            confirm.disabled = cancel.disabled = false;
        }
    }
}

function closeGameFiles() {
    if (!gameFilesView) return;
    const {shell, workspace, sidebar, stopLayout, opener} = gameFilesView;
    stopLayout();
    gameFilesView = null;
    shell.classList.remove('showing-game-files');
    workspace.hidden = sidebar.hidden = true;
    workspace.replaceChildren();
    sidebar.replaceChildren();
    opener.focus();
}

function openGameFiles(opener, target = null) {
    if (workbench.operation || gameFilesView) return;

    const tr = workbenchText;
    const shell = document.querySelector('.app-shell');
    const workspace = document.getElementById('game-files-workspace');
    const sidebar = document.getElementById('game-files-sidebar');
    const mobileNav = wbElement('div', 'game-files-mobile-nav');
    const view = {shell, workspace, sidebar, opener};
    gameFilesView = view;
    const root = document.getElementById('retroarch_root').value;
    const system = document.getElementById('system_name').value;
    const header = wbElement('header', 'game-files-header');
    const title = wbElement('h2', '', tr('游戏文件', 'Game files'));
    title.id = 'game-files-title';
    title.tabIndex = -1;
    const back = gmButton('返回游戏库', 'Back to library', closeGameFiles);
    wbIconButton(back, 'arrow-left', back.textContent);
    header.append(title, back);

    const navigation = wbElement('nav', 'game-files-navigation');
    navigation.setAttribute('aria-label', tr('存储位置', 'Storage locations'));
    const remote = wbElement('div', 'game-files-storages');
    const storageStatus = wbElement('p', 'game-files-muted');
    storageStatus.setAttribute('role', 'status');
    const refresh = gmButton('重新检测存储', 'Detect storage again', loadStorages);
    const local = gmButton('电脑目录', 'Computer folder', chooseFolder);
    local.id = 'game-files-local';
    local.prepend(wbIcon('folder'));
    navigation.append(wbElement('h3', '', tr('电脑', 'Computer')), local,
        wbElement('h3', '', tr('USB 掌机', 'USB handheld')), remote, storageStatus, refresh);

    const pane = wbElement('section', 'game-files-pane');
    const toolbar = wbElement('div', 'game-files-toolbar');
    const up = gmButton('上级目录', 'Parent folder', () => loadDirectory(current.parent));
    wbIconButton(up, 'arrow-up', up.textContent);
    up.disabled = true;
    const location = wbElement('nav', 'game-files-location', tr('选择要浏览的存储或电脑目录', 'Choose a storage or computer folder'));
    location.setAttribute('aria-label', tr('当前路径', 'Current path'));
    const add = gmButton('添加游戏文件…', 'Add game files…', addFiles, false);
    add.id = 'game-files-add';
    const addFolder = gmButton('添加文件夹…', 'Add folder…', addFolderFiles);
    addFolder.id = 'game-files-add-folder';
    const rename = gmButton('重命名', 'Rename', () => renameFile());
    const remove = gmButton('删除文件', 'Delete file', () => deleteFile());
    const copy = gmButton('复制', 'Copy', () => copyFile());
    const paste = gmButton('粘贴', 'Paste', pasteFiles);
    wbIconButton(rename, 'pencil', rename.textContent);
    wbIconButton(remove, 'trash', remove.textContent);
    wbIconButton(copy, 'copy', copy.textContent);
    wbIconButton(paste, 'clipboard', paste.textContent);
    rename.disabled = remove.disabled = copy.disabled = paste.disabled = add.disabled = addFolder.disabled = true;
    toolbar.append(up, location, rename, remove, copy, paste, addFolder, add);
    const table = wbElement('div', 'game-files-table');
    const rows = wbElement('ul', 'game-files-rows');
    const empty = wbElement('p', 'game-files-empty', tr('从左侧选择要存放游戏的目录', 'Pick a folder on the left to store games'));
    table.append(wbElement('div', 'game-files-column', tr('名称', 'Name')), empty, rows);
    const status = wbElement('p', 'game-files-status');
    status.setAttribute('role', 'status');
    pane.append(toolbar, table, status);
    sidebar.append(navigation);
    workspace.append(header, mobileNav, pane);
    shell.classList.add('showing-game-files');
    workspace.hidden = sidebar.hidden = false;
    title.focus();

    const narrow = matchMedia('(max-width:560px)');
    const placeNavigation = () => (narrow.matches ? mobileNav : sidebar).append(navigation);
    placeNavigation();
    narrow.addEventListener('change', placeNavigation);
    view.stopLayout = () => narrow.removeEventListener('change', placeNavigation);

    let current = null;
    let selected = null;
    let changing = false;
    let lastLocal = '';
    let directoryRequest = 0;
    view.refresh = () => { if (current) loadDirectory(current.path); };
    loadStorages();
    if (target) loadDirectory(target.directory, target.path);
    else if (root && !root.startsWith('adb://')) {
        const initialRequest = directoryRequest;
        desktopRequest('/api/content/setup?root=' + encodeURIComponent(root)).then(({profiles}) => {
            if (gameFilesView !== view || initialRequest !== directoryRequest) return;
            const selected = document.getElementById('playlist_path').value;
            const filename = selected.split(/[\\/]/).pop();
            const name = selected.startsWith('mtp://') ? decodeURIComponent(filename) : filename;
            const directories = new Set(profiles.filter(profile => profile.system === system &&
                (!name || profile.playlist_name === name)).map(profile => profile.directory));
            if (directories.size === 1) loadDirectory([...directories][0]);
        }).catch(error => {
            if (gameFilesView === view && initialRequest === directoryRequest) status.textContent = error.message;
        });
    }

    function updateActionState() {
        rename.disabled = remove.disabled = copy.disabled = !selected || changing;
        paste.disabled = !gameFilesClipboard || gameFilesClipboard.root !== root || !current?.path || changing;
        const mtpDest = current?.path?.startsWith('mtp://');
        const blocked = Boolean(mtpDest && (!root.startsWith('mtp://') || root.split('/')[2] !== current.path.split('/')[2]));
        add.disabled = addFolder.disabled = !current?.path || changing || blocked;
        add.title = addFolder.title = blocked
            ? tr('先在游戏库中打开这台掌机。', 'Open this handheld library first.')
            : tr('把电脑上的文件复制进当前目录。', 'Copy computer files into this folder.');
        empty.hidden = Boolean(current);
    }

    async function loadStorages() {
        refresh.disabled = true;
        storageStatus.textContent = tr('正在检测存储…', 'Detecting storage…');
        try {
            const result = await desktopRequest('/api/game-files/storages');
            if (gameFilesView !== view) return;
            lastLocal ||= result.local;
            remote.replaceChildren(...result.storages.map(storage => {
                const label = storage.label;
                const button = gmButton(label, label, () => loadDirectory(storage.path));
                button.dataset.storage = storage.path;
                button.prepend(wbIcon('device-sd-card'));
                if (current?.path.startsWith(storage.path)) button.setAttribute('aria-current', 'true');
                return button;
            }));
            storageStatus.textContent = result.storage_error ||
                (result.storages.length ? '' : tr('未检测到 USB 文件传输存储。', 'No USB file transfer storage detected.'));
        } catch (error) {
            storageStatus.textContent = error.message;
        } finally {
            refresh.disabled = false;
        }
    }

    async function chooseFolder() {
        local.disabled = true;
        try {
            const result = await desktopRequest('/api/desktop/pick', {kind:'directory', initial:lastLocal});
            if (gameFilesView === view && result.path) await loadDirectory(result.path);
        } catch (error) {
            status.textContent = error.message;
        } finally {
            local.disabled = false;
        }
    }

    function selectFile(item, button) {
        rows.querySelector('[aria-pressed=true]')?.setAttribute('aria-pressed', 'false');
        selected = item;
        button?.setAttribute('aria-pressed', 'true');
        updateActionState();
    }

    function renameFile(item = selected) {
        if (!item || changing) return;
        const directory = current.path;
        const dialog = wbElement('dialog', 'desktop-confirm app-dialog');
        const heading = wbElement('h2', '', tr('重命名', 'Rename'));
        heading.id = 'game-file-change-title';
        dialog.setAttribute('aria-labelledby', heading.id);
        dialog.append(heading, wbElement('p', '', item.name));
        const input = wbElement('input', '');
        input.value = item.name;
        input.setAttribute('aria-label', tr('文件名', 'Filename'));
        dialog.append(input);
        const error = wbElement('p', '', '');
        error.setAttribute('role', 'alert');
        const cancel = gmButton('取消', 'Cancel', () => dialog.close());
        const confirm = gmButton('确认', 'Confirm', submit, false);
        dialog.append(error, cancel, confirm);
        document.body.append(dialog);
        dialog.addEventListener('close', () => dialog.remove(), {once:true});
        dialog.addEventListener('cancel', event => { if (changing) event.preventDefault(); });
        dialog.showModal();
        input.focus();
        input.setSelectionRange(0, Math.max(0, item.name.lastIndexOf('.')));
        input.onkeydown = event => { if (event.key === 'Enter' && !event.isComposing) submit(); };

        async function submit() {
            if (changing) return;
            changing = true;
            cancel.disabled = confirm.disabled = true;
            try {
                const result = await desktopRequest('/api/game-files/file-ops', {action:'rename', path:item.path, root, name:input.value.trim()});
                recordFileChange(root, {action:'rename', path:item.path, to:result.new_path, folder:Boolean(item.directory)});
                dialog.close();
                if (gameFilesView === view) await loadDirectory(directory);
            } catch (failure) {
                error.textContent = gmError(failure);
            } finally {
                changing = false;
                cancel.disabled = confirm.disabled = false;
            }
        }
    }

    function deleteFile(item = selected) {
        if (!item || changing) return;
        const directory = current.path;
        const dialog = wbElement('dialog', 'desktop-confirm app-dialog game-file-delete-dialog');
        const heading = wbElement('h2', '', tr('删除文件', 'Delete item'));
        heading.id = 'game-file-delete-title';
        dialog.setAttribute('aria-labelledby', heading.id);
        const message = wbElement('p', '', '');
        message.setAttribute('role', 'status');
        const cancel = gmButton('关闭', 'Close', () => dialog.close());
        const confirm = gmButton('确认删除', 'Delete', apply, false);
        dialog.append(heading, wbElement('p', '', item.name),
            wbElement('p', '', tr(item.directory ? '文件夹及其内容会移到电脑上的备份目录。' : '文件会移到电脑上的备份目录。',
                                  item.directory ? 'The folder and its contents move to a backup folder on this computer.'
                                                 : 'The file moves to a backup folder on this computer.')),
            message, cancel, confirm);
        document.body.append(dialog);
        dialog.addEventListener('close', () => dialog.remove(), {once:true});
        dialog.addEventListener('cancel', event => { if (changing) event.preventDefault(); });
        dialog.showModal();
        cancel.focus();

        async function apply() {
            if (changing) return;
            if (!beginWorkbenchOperation('game-file-ops')) { message.textContent = tr('请等待当前任务完成。', 'Wait for the current task.'); return; }
            changing = true;
            cancel.disabled = confirm.disabled = true;
            message.textContent = tr('正在备份和删除…', 'Backing up and deleting…');
            try {
                const {result} = await runGameJob('/api/game-files/file-ops', {action:'delete', path:item.path, root},
                    state => { if (state.connectionError || currentUILanguage !== 'en') message.textContent = state.message; });
                recordFileChange(root, {action:'delete', path:item.path, folder:Boolean(item.directory)});
                dialog.close();
                if (gameFilesView === view) {
                    await loadDirectory(directory);
                    status.textContent = tr('已删除。备份：', 'Deleted. Backup: ') + result.backup_directory;
                }
            } catch (error) {
                message.textContent = gmError(error);
                cancel.disabled = confirm.disabled = false;
            } finally {
                changing = false;
                updateActionState();
                endWorkbenchOperation();
            }
        }
    }

    function copyFile(item = selected) {
        if (!item || changing) return;
        gameFilesClipboard = {root, item: {path:item.path, name:item.name, folder:Boolean(item.directory)}};
        updateActionState();
        status.textContent = tr('已复制「' + item.name + '」，切换到目标目录后粘贴。', 'Copied "' + item.name + '". Paste it in the destination folder.');
    }

    async function pasteFiles() {
        if (!gameFilesClipboard || changing || !current?.path) return;
        if (!beginWorkbenchOperation('game-file-ops')) { status.textContent = tr('请等待当前任务完成。', 'Wait for the current task.'); return; }
        const item = gameFilesClipboard.item;
        const directory = current.path;
        changing = true;
        updateActionState();
        status.textContent = tr('正在粘贴…', 'Pasting…');
        try {
            await runGameJob('/api/game-files/file-ops', {action:'copy', path:item.path, directory, root},
                state => { if (state.connectionError || currentUILanguage !== 'en') status.textContent = state.message; });
            if (gameFilesView === view) {
                await loadDirectory(directory);
                status.textContent = tr('已粘贴「' + item.name + '」。', 'Pasted "' + item.name + '".');
            }
        } catch (error) {
            status.textContent = gmError(error);
        } finally {
            changing = false;
            if (gameFilesView === view) updateActionState();
            endWorkbenchOperation();
        }
    }

    function storageLabel(path) {
        for (const button of remote.children) {
            if (button.dataset.storage === path) return button.textContent;
        }
        return '';
    }

    async function loadDirectory(path, selectedPath = null, highlightNames = new Set()) {
        const request = ++directoryRequest;
        status.textContent = tr('正在读取目录…', 'Reading folder…');
        try {
            const result = await desktopRequest('/api/game-files/directory?path=' + encodeURIComponent(path));
            if (gameFilesView !== view || request !== directoryRequest) return;
            current = result;
            selectFile(null);
            const isRemote = result.path.startsWith('mtp://');
            if (!isRemote) lastLocal = result.path;
            if (isRemote) local.removeAttribute('aria-current');
            else local.setAttribute('aria-current', 'true');
            for (const button of remote.children) {
                if (result.path.startsWith(button.dataset.storage)) button.setAttribute('aria-current', 'true');
                else button.removeAttribute('aria-current');
            }
            location.replaceChildren(...result.breadcrumbs.flatMap(({name, path}, index, crumbs) => {
                const label = (index || !isRemote ? name : '') || (isRemote ? storageLabel(path) : '') || name || tr('存储根目录', 'Storage root');
                const currentCrumb = index === crumbs.length - 1;
                const crumb = currentCrumb ? wbElement('span', '', label)
                    : gmButton(label, label, () => loadDirectory(path));
                if (currentCrumb) crumb.setAttribute('aria-current', 'page');
                if (!index) return [crumb];
                const separator = wbElement('span', 'game-files-separator', '›');
                separator.setAttribute('aria-hidden', 'true');
                return [separator, crumb];
            }));
            up.disabled = !result.parent;
            rows.replaceChildren(...result.items.map(item => {
                const row = wbElement('li', 'game-files-row');
                if (highlightNames.has(item.name)) row.classList.add('game-files-new');
                if (item.directory) {
                    const button = gmButton(item.name, item.name, () => loadDirectory(item.path));
                    button.prepend(wbIcon('folder'));
                    const menu = wbElement('details', 'action-menu game-files-row-menu');
                    const summary = wbElement('summary', 'action-menu-trigger');
                    summary.setAttribute('aria-label', tr(item.name + ' 的更多操作', 'More actions for ' + item.name));
                    summary.append(wbIcon('dots'));
                    const drop = wbElement('div', 'action-menu-list');
                    const entry = (zh, en, action) => {
                        const option = wbElement('button', 'action-menu-item', tr(zh, en));
                        option.onclick = () => { menu.open = false; action(item); };
                        drop.append(option);
                    };
                    entry('重命名', 'Rename', renameFile);
                    entry('复制', 'Copy', copyFile);
                    entry('删除…', 'Delete…', deleteFile);
                    menu.append(summary, drop);
                    row.append(button, menu);
                } else {
                    const button = gmButton(item.name, item.name, () => selectFile(item, button));
                    button.setAttribute('aria-pressed', 'false');
                    row.append(button);
                    if (item.path === selectedPath) selectFile(item, button);
                }
                return row;
            }));
            rows.querySelector('[aria-pressed=true]')?.scrollIntoView({block:'nearest'});
            status.textContent = result.items.length
                ? tr(result.items.length + ' 个项目', result.items.length + ' items')
                : tr('此目录没有文件。', 'This folder is empty.');
            updateActionState();
        } catch (error) {
            if (gameFilesView !== view || request !== directoryRequest) return;
            current = null;
            selectFile(null);
            up.disabled = true;
            rows.replaceChildren();
            status.textContent = tr('读取目录失败：', 'Could not read the folder: ') + error.message;
            updateActionState();
        }
    }

    async function addFiles() {
        if (!current?.path || changing) return;
        try {
            const result = await desktopRequest('/api/desktop/pick', {kind:'files', initial:lastLocal});
            if (gameFilesView === view && result.paths?.length) await submitAdd(result.paths);
        } catch (error) {
            status.textContent = error.message;
        }
    }

    async function addFolderFiles() {
        if (!current?.path || changing) return;
        try {
            const result = await desktopRequest('/api/desktop/pick', {kind:'directory', initial:lastLocal});
            if (gameFilesView === view && result.path) await submitAdd([result.path]);
        } catch (error) {
            status.textContent = error.message;
        }
    }

    async function submitAdd(sources) {
        if (!current?.path || changing || !sources.length) return;
        if (!beginWorkbenchOperation('game-file-ops')) { status.textContent = tr('请等待当前任务完成。', 'Wait for the current task.'); return; }
        const directory = current.path;
        changing = true;
        updateActionState();
        status.textContent = tr('正在复制…', 'Copying…');
        try {
            const {result} = await runGameJob('/api/game-files/file-ops', {action:'add', sources, directory, root},
                state => { if (state.connectionError || currentUILanguage !== 'en') status.textContent = state.message; });
            if (gameFilesView === view) {
                await loadDirectory(directory, null, new Set(result.copied));
                status.textContent = addSummary(result);
            }
        } catch (error) {
            status.textContent = gmError(error);
        } finally {
            changing = false;
            if (gameFilesView === view) updateActionState();
            endWorkbenchOperation();
        }
    }

    function addSummary(result) {
        const parts = [];
        const list = names => names.length > 4 ? names.slice(0, 4).join('、') + ' 等 ' + names.length + ' 项' : names.join('、');
        if (result.copied.length) parts.push(tr('已复制：', 'Copied: ') + list(result.copied));
        if (result.skipped.length) parts.push(tr('已跳过（同名已存在）：', 'Skipped (same name exists): ') + list(result.skipped));
        if (result.failed.length) parts.push(tr('失败：', 'Failed: ') + list(result.failed.map(entry => entry.name)));
        if (result.remaining.length) parts.push(tr('未完成：', 'Not finished: ') + list(result.remaining));
        return parts.length ? parts.join(tr('；', '; ')) : tr('没有可复制的内容。', 'Nothing to copy.');
    }
}

async function refreshDeletedPlaylists(paths) {
    if (!paths.length) return;
    const active = paths.includes(gameLibraryInput()[0]);
    if (active) retryGameLibrary();
    await refreshLibraryPlaylists(paths);
}
