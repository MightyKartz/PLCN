"""Lightweight home-screen discovery and a small history of opened libraries."""
import json
import shutil
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
    if not path or len(path) > 4096 or not (scanner.is_adb_uri(path) or Path(path).is_absolute()):
        raise ValueError('游戏库路径无效')
    entry = {'path': path, 'label': str(payload.get('label') or Path(path).name)[:120]}
    target = history_path()
    with file_lock(target):
        entries = [entry] + [e for e in read_history(config_path) if e['path'] != path]
        atomic_write_json(target, entries[:5])
    return {'saved': True}


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
    seen = set()
    candidates = scanner.default_scan_candidates() if local_candidates is None else local_candidates
    for candidate in candidates:
        if not candidate.get('exists'):
            continue
        root, playlists = scanner._infer_layout(Path(candidate['path']))
        if not playlists or not playlists.is_dir() or str(root) in seen:
            continue
        seen.add(str(root))
        sources.append({'path': str(root), 'label': root.name, 'transport': 'local', 'status': 'ready'})
    recent = []
    for entry in read_history(config_path):
        path = entry['path']
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
            'adb_available': bool(adb_runner or shutil.which('adb'))}
