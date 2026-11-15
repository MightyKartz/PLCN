"""Lightweight home-screen discovery and a small history of opened libraries."""
import json
import shutil
from adb_runtime import adb_available, usb_android_devices
from pathlib import Path

import app_paths
import retroarch_scanner as scanner
from safe_io import atomic_write_json, file_lock


def history_path():
    return app_paths.user_data_dir() / 'recent-libraries.json'


def read_history(config_path=None):
    try:
        entries = json.loads(history_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        entries = []
    if not isinstance(entries, list):
        entries = []
    entries = [e for e in entries if isinstance(e, dict) and isinstance(e.get('path'), str)][:5]
    if len(entries) < 5 and config_path:
        try:
            path = json.loads(Path(config_path).read_text(encoding='utf-8')).get('retroarch_root')
            if path and not any(e['path'] == path for e in entries):
                entries.append({'path': path, 'label': Path(path).name})
        except (OSError, ValueError, AttributeError):
            pass
    return entries


def remember(payload, config_path=None):
    path = str(payload.get('path') or '').strip()
    if not path or len(path) > 4096 or not (scanner.is_adb_uri(path) or path.startswith('mtp://') or Path(path).is_absolute()):
        raise ValueError('游戏库路径无效')
    entry = {'path': path, 'label': str(payload.get('label') or Path(path).name)[:120]}
    target = history_path()
    with file_lock(target):
        entries = [entry] + [e for e in read_history(config_path) if e['path'] != path]
        atomic_write_json(target, entries[:5])
    return {'saved': True}


def mtp_sources():
    import mtp_runtime as mtp
    try:
        devices = mtp.devices()
    except (RuntimeError, OSError) as error:
        return [], str(error)
    result = []
    for device in devices:
        try:
            scan = mtp.scan(device['path'])
        except (RuntimeError, OSError, ValueError) as error:
            return result, str(error)
        root = scan['root_path']
        if not scan['playlists'] and not mtp.parse(root)[2]:
            root = mtp.join(root, 'RetroArch')
        result.append({**device, 'path': root, 'status': 'ready' if scan['playlists'] else 'no_library'})
    return result, None


def discover(config_path=None, adb_runner=None, local_candidates=None):
    devices = scanner.list_adb_devices(adb_runner=adb_runner, include_unavailable=True)
    by_serial = {d['serial']: d for d in devices}
    sources = []
    for device in devices:
        serial = device['serial']
        state = device['state']
        root, playlists = ('', None)
        if state == 'device':
            root, playlists = scanner._find_adb_root(serial, adb_runner=adb_runner)
            state = 'ready' if playlists else 'no_library'
        sources.append({'path': scanner.adb_uri(serial, root), 'label': device['model'].replace('_', ' ') or serial,
                        'transport': 'adb', 'status': state, 'serial': serial})
    mtp_devices, mtp_error = mtp_sources() if adb_runner is None else ([], None)
    sources.extend(mtp_devices)
    if adb_runner is None and not mtp_devices:
        for device in usb_android_devices():
            if device['serial'] not in by_serial:
                sources.append({'path': '', 'serial': device['serial'], 'label': device['label'],
                                'transport': 'adb', 'status': 'usb_only', 'error': mtp_error})
    seen = set()
    candidates = local_candidates or []
    for candidate in candidates:
        if not candidate.get('exists'):
            continue
        root, playlists = scanner._infer_layout(Path(candidate['path']))
        if not playlists or not playlists.is_dir() or str(root) in seen:
            continue
        seen.add(str(root))
        sources.append({'path': str(root), 'label': root.name, 'transport': 'local', 'status': 'ready'})
    connected_paths = {source['path'].rstrip('/') for source in sources if source['path']}
    recent = []
    for entry in read_history(config_path):
        path = entry['path']
        if path.rstrip('/') in connected_paths:
            continue
        if path.startswith('mtp://'):
            source = next((entry for entry in mtp_devices if entry['path'] == path), None)
            recent.append({**entry, 'transport':'mtp', 'status':'ready' if source else 'disconnected'})
            continue
        if not scanner.is_adb_uri(path):
            continue
        if scanner.is_adb_uri(path):
            serial, _ = scanner.parse_adb_uri(path)
            device = by_serial.get(serial)
            status = 'ready' if device and device['state'] == 'device' else device['state'] if device else 'disconnected'
            transport = 'adb'
        else:
            status = 'ready' if Path(path).exists() else 'missing'
            transport = 'local'
        recent.append({**entry, 'status': status, 'transport': transport})
    return {'sources': sources, 'recent': recent,
            'adb_available': bool(adb_runner or adb_available())}
