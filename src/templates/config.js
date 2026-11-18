/* Configuration, system selection and the built-in file picker. */
let currentTargetInputId = '';
let isDirectoryMode = false;
let currentPath = '.';
let fileListVersion = 0;
let filePickerReturnFocus = null;

let pathSettingsRoot = '';
let legacyThumbnailsSetting = false;

function getThumbnailsDirectory() {
    return document.getElementById('thumbnails_override').value.trim()
        || currentDeviceScan?.directories?.thumbnails || '';
}

function setLibraryRoot(path) {
    if (pathSettingsRoot && pathSettingsRoot !== path) {
        document.getElementById('thumbnails_override').value = '';
        legacyThumbnailsSetting = false;
    }
    pathSettingsRoot = path;
    document.getElementById('retroarch_root').value = path;
}

async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        if (!response.ok) throw new Error(uiText('读取失败'));
        const config = await response.json();
        pathSettingsRoot = config.retroarch_root || '';
        document.getElementById('retroarch_root').value = pathSettingsRoot;
        legacyThumbnailsSetting = config.thumbnails_override === undefined;
        document.getElementById('thumbnails_override').value = config.thumbnails_override
            ?? config.thumbnails_dir ?? config.batch_thumbnails_dir ?? '';
        document.getElementById('rom_name_cn_path').value = config.rom_name_cn_path || 'data/rom-name-cn';
        document.getElementById('playlist_path').value = '';
        document.getElementById('system_name').value = '';
        renderWorkbench();
    } catch (error) {
        showStatus('加载配置失败: ' + error.message, 'error');
    }
}

async function saveConfig(mode = 'single') {
    const thumbnails = getThumbnailsDirectory();
    const config = {
        retroarch_root: document.getElementById('retroarch_root').value.trim(),
        playlist_path: document.getElementById('playlist_path').value,
        system_name: document.getElementById('system_name').value,
        thumbnails_override: document.getElementById('thumbnails_override').value.trim(),
        thumbnails_dir: thumbnails,
        batch_thumbnails_dir: thumbnails,
        rom_name_cn_path: document.getElementById('rom_name_cn_path').value,
        batch_dir: mode === 'batch' ? currentDeviceScan?.directories?.playlists || '' : '',
    };
    try {
        const response = await fetch('/api/config', {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(config),
        });
        if (!response.ok) throw new Error('保存配置失败');
        return true;
    } catch (error) {
        showStatus('保存出错: ' + error.message, 'error');
        return false;
    }
}

async function applyPathSettings(initialPaths) {
    if (workbench.operation) return;
    const root = document.getElementById('retroarch_root').value.trim();
    const artwork = document.getElementById('thumbnails_override').value.trim();
    if (root === initialPaths.root && artwork === initialPaths.artwork) {
        desktopDialog.close();
    } else if (root && root !== initialPaths.root && root !== currentDeviceScan?.root_path) {
        await scanDevice(false);
    } else if (await saveConfig()) {
        desktopDialog.close();
    }
}

function getProcessingOptions() {
    return {
        write_names: document.getElementById('option-write-names').checked,
        download_thumbnails: document.getElementById('option-download-artwork').checked
    };
}

function getRepairMode() {
    const options = getProcessingOptions();
    return !options.write_names ? 'artwork' : !options.download_thumbnails ? 'names' : 'both';
}

async function changePreviewOptions(control) {
    const options = getProcessingOptions();
    if (!options.write_names && !options.download_thumbnails) {
        control.checked = true;
        showStatus(workbenchText('至少保留一个操作', 'Choose at least one operation'), 'info');
        return;
    }
    await previewTask(workbench.previewScope);
}

function openFilePicker(inputId, directoryMode, returnFocus = document.activeElement) {
    filePickerReturnFocus = returnFocus;
    currentTargetInputId = inputId;
    isDirectoryMode = directoryMode;

    document.getElementById('modalTitle').textContent = directoryMode ? workbenchText('选择目录', 'Choose folder') : workbenchText('选择文件', 'Choose file');
    document.getElementById('file-picker-close').setAttribute('aria-label', workbenchText('关闭文件选择器', 'Close file picker'));
    document.getElementById('selectDirBtn').style.display = directoryMode ? 'inline-flex' : 'none';
    document.getElementById('fileModal').showModal();

    const currentVal = document.getElementById(inputId).value;
    loadFileList(currentVal || '.');
}

function closeModal() {
    fileListVersion++;
    document.getElementById('fileModal').close();
}

async function loadFileList(path) {
    const version = ++fileListVersion;
    const listEl = document.getElementById('fileList');
    const selectDir = document.getElementById('selectDirBtn');
    selectDir.disabled = true;
    listEl.textContent = workbenchText('正在读取目录…', 'Loading folder…');
    try {
        const response = await fetch(`/api/fs/list?path=${encodeURIComponent(path)}`);
        const data = await response.json();
        if (version !== fileListVersion || !document.getElementById('fileModal').open) return;

        if (data.error) {
            if (path !== '.') await loadFileList('.');
            else listEl.textContent = data.error;
            return;
        }

        currentPath = data.current_path;
        document.getElementById('currentPath').textContent = currentPath;

        listEl.innerHTML = '';
        selectDir.disabled = false;

        data.items.forEach(item => {
            const li = document.createElement('li');
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'file-item';
            const icon = item.is_dir ? 'DIR' : 'FILE';
            button.innerHTML = `<span class="file-icon">${icon}</span> <span>${escapeHtml(item.name)}</span>`;
            button.disabled = isDirectoryMode && !item.is_dir;

            button.onclick = () => {
                if (item.is_dir) {
                    loadFileList(item.path);
                } else if (!isDirectoryMode) {
                    selectFile(item.path);
                }
            };

            li.appendChild(button); listEl.appendChild(li);
        });
    } catch (error) {
        if (version === fileListVersion && document.getElementById('fileModal').open) listEl.textContent = workbenchText('读取目录失败：', 'Could not read folder: ') + error.message;
        console.error('Error loading file list:', error);
    }
}

function selectFile(path) {
    document.getElementById(currentTargetInputId).value = path;
    if (currentTargetInputId === 'thumbnails_override') legacyThumbnailsSetting = false;
    invalidateWorkbenchPreview();
    closeModal();

    if (currentTargetInputId === 'retroarch_root') {
        scanDevice(false);
    }
    renderWorkbench();
}

function selectCurrentDir() { selectFile(currentPath); }

function handleContextChange(event) {
    if (event.target.matches('[data-input-control]')) {
        if (event.target.id === 'thumbnails_override') legacyThumbnailsSetting = false;
        if (event.target.id === 'retroarch_root') {
            setLibraryRoot(event.target.value.trim());
            currentDeviceScan = null;
            document.getElementById('playlist_path').value = '';
            document.getElementById('system_name').value = '';
            renderDeviceScan(null);
        }
        invalidateWorkbenchPreview();
        renderWorkbench();
    }
}

document.addEventListener('input', handleContextChange);
document.addEventListener('change', handleContextChange);
