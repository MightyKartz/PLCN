/* File browsing works independently of the selected RetroArch library. */
let gameFilesView = null;

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
    const add = gmButton('添加文件', 'Add files', () => {
        openGameImport(current?.path || '');
    }, false);
    add.id = 'game-files-import';
    wbIconButton(add, 'file-plus', add.textContent);
    const rename = gmButton('重命名', 'Rename', renameFile);
    const remove = gmButton('删除文件', 'Delete file', deleteFile);
    wbIconButton(rename, 'pencil', rename.textContent);
    wbIconButton(remove, 'trash', remove.textContent);
    rename.disabled = remove.disabled = true;
    toolbar.append(up, location, rename, remove, add);
    updateImportAction();
    const table = wbElement('div', 'game-files-table');
    const rows = wbElement('ul', 'game-files-rows');
    table.append(wbElement('div', 'game-files-column', tr('名称', 'Name')), rows);
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

    function updateImportAction(path = '') {
        const mtp = root.startsWith('mtp://');
        const storageDevice = value => value.split('/')[2];
        const compatible = !path || (mtp
            ? path.startsWith('mtp://') && storageDevice(path) === storageDevice(root)
            : !path.startsWith('mtp://'));
        add.disabled = !root || root.startsWith('adb://') || !compatible;
        add.title = add.disabled
            ? tr('现有导入流程需要打开对应的 RetroArch 游戏库。', 'Open the matching RetroArch library to import files.')
            : add.getAttribute('aria-label');
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
        rename.disabled = remove.disabled = !item || changing;
    }

    function renameFile() {
        if (!selected || changing) return;
        const item = selected;
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
                await desktopRequest('/api/game-files/change', {action:'rename', path:item.path, root, name:input.value.trim()});
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

    function deleteFile() {
        if (!selected || changing) return;
        const item = selected;
        const directory = current.path;
        const dialog = wbElement('dialog', 'desktop-confirm app-dialog game-file-delete-dialog');
        const heading = wbElement('h2', '', tr('删除游戏文件', 'Delete game files'));
        heading.id = 'game-file-delete-title';
        dialog.setAttribute('aria-labelledby', heading.id);
        const impact = wbElement('div', 'game-file-delete-impact');
        const message = wbElement('p', '', '');
        message.setAttribute('role', 'status');
        const cancel = gmButton('关闭', 'Close', () => dialog.close());
        const confirm = gmButton('确认删除', 'Delete files', apply, false);
        confirm.disabled = true;
        const clean = document.createElement('input');
        clean.type = 'checkbox';
        let previewId;
        let affectedLists = [];
        dialog.append(heading, wbElement('p', '', item.name), impact, message, cancel, confirm);
        document.body.append(dialog);
        dialog.addEventListener('close', () => dialog.remove(), {once:true});
        dialog.addEventListener('cancel', event => { if (changing) event.preventDefault(); });
        dialog.showModal();
        cancel.focus();
        preview();

        function list(zh, en, items) {
            if (!items.length) return;
            const rows = wbElement('ul', '');
            rows.append(...items.map(item => wbElement('li', '', item)));
            impact.append(wbElement('h3', '', tr(zh, en)), rows);
        }

        async function job(route, payload, busyMessage) {
            if (!beginWorkbenchOperation('game-file-delete')) throw new Error(tr('请等待当前任务完成。', 'Wait for the current task.'));
            changing = true;
            cancel.disabled = true;
            message.textContent = busyMessage;
            try {
                return await runGameJob(route, payload, state => {
                    if (state.connectionError || currentUILanguage !== 'en') message.textContent = state.message;
                });
            } finally {
                gameManagement.job = null;
                changing = false;
                cancel.disabled = false;
                endWorkbenchOperation();
            }
        }

        async function preview() {
            try {
                const {id, result} = await job('/api/game-files/delete-preview', {root, path:item.path},
                    tr('正在检查游戏列表与文件引用…', 'Checking playlists and file references…'));
                previewId = id;
                affectedLists = result.playlists;
                const displayPath = path => path.startsWith('mtp://') ? decodeURIComponent(path) : path;
                list('将删除的文件', 'Files to delete', result.files.map(displayPath));
                list('将移出的游戏列表条目', 'Playlist entries to remove',
                     result.entries.map(entry => entry.playlist + ' · ' + entry.label));
                list('仍被引用，将保留的文件', 'Referenced files to keep', result.shared.map(displayPath));
                if (result.covers.length) {
                    const option = wbElement('label', 'game-file-delete-option');
                    option.append(clean, document.createTextNode(tr('同时清理下列未使用的封面', 'Also clean up these unused covers')));
                    impact.append(option);
                    list('可选封面', 'Optional covers', result.covers.map(displayPath));
                }
                message.textContent = tr('请先退出 RetroArch。助手会先备份，再更新列表和删除文件。', 'Quit RetroArch first. The assistant backs up files before updating playlists and deleting files.');
                confirm.disabled = false;
            } catch (error) {
                message.textContent = gmError(error);
            }
        }

        async function apply() {
            if (changing || !previewId) return;
            confirm.disabled = true;
            try {
                const {result} = await job('/api/game-files/delete-apply',
                    {preview_job_id:previewId, clean_covers:clean.checked}, tr('正在备份和删除…', 'Backing up and deleting…'));
                await refreshDeletedPlaylists(result.playlists);
                if (gameFilesView === view) {
                    await loadDirectory(directory);
                    status.textContent = tr('删除完成。备份：', 'Deleted. Backup: ') + result.backup_directory;
                }
                dialog.close();
            } catch (error) {
                message.textContent = gmError(error);
                try { await refreshDeletedPlaylists(affectedLists); }
                catch (refreshError) { message.textContent += ' · ' + gmError(refreshError); }
                if (gameFilesView === view) await loadDirectory(directory);
            }
        }
    }

    async function loadDirectory(path, selectedPath = null) {
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
                const label = name || tr('存储根目录', 'Storage root');
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
            updateImportAction(result.path);
            rows.replaceChildren(...result.items.map(item => {
                const row = wbElement('li', 'game-files-row');
                if (item.directory) {
                    const button = gmButton(item.name, item.name, () => loadDirectory(item.path));
                    button.prepend(wbIcon('folder'));
                    row.append(button);
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
        } catch (error) {
            if (gameFilesView === view && request === directoryRequest) status.textContent = error.message;
        }
    }
}

async function refreshDeletedPlaylists(paths) {
    if (!paths.length) return;
    const active = paths.includes(gameLibraryInput()[0]);
    if (active) retryGameLibrary();
    await refreshLibraryPlaylists(paths);
}
