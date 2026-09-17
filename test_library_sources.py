import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'src'))
import library_sources as sources


def test_discovery_exposes_authorized_unauthorized_and_offline_devices(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, 'history_path', lambda: tmp_path / 'recent.json')
    def adb(args, timeout=10):
        if args == ['devices', '-l']:
            return 'List of devices attached\nonline device model:RG_476H\nlocked unauthorized\nlost offline\n'
        assert args[1] == 'online', 'Do not probe an unauthorized/offline device'
        return '/sdcard/RetroArch\n'
    result = sources.discover(adb_runner=adb, local_candidates=[])
    assert [d['status'] for d in result['sources']] == ['ready', 'unauthorized', 'offline']
    assert result['sources'][0]['label'] == 'RG 476H'
    assert result['sources'][0]['path'] == 'adb://online/sdcard/RetroArch'
    assert not (tmp_path / 'recent.json').exists(), 'Discovery must not write history'


def test_recent_libraries_deduplicate_and_report_unavailable_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, 'history_path', lambda: tmp_path / 'recent.json')
    directory = tmp_path / 'RetroArch'; directory.mkdir()
    for path in [str(directory), 'adb://offline/sdcard/RetroArch', str(tmp_path / 'gone'), str(directory)]:
        sources.remember({'path': path})
    result = sources.discover(adb_runner=lambda *args, **kwargs: '', local_candidates=[])
    assert [e['status'] for e in result['recent']] == ['ready', 'missing', 'disconnected']
    assert result['recent'][0]['path'] == str(directory)


def test_legacy_recent_config_and_device_without_library(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, 'history_path', lambda: tmp_path / 'recent.json')
    config = tmp_path / 'config.json'; config.write_text(json.dumps({'retroarch_root': str(tmp_path)}))
    def adb(args, timeout=10):
        return 'List of devices attached\nserial device\n' if args == ['devices', '-l'] else ''
    result = sources.discover(config, adb_runner=adb, local_candidates=[])
    assert result['sources'][0]['status'] == 'no_library'
    assert result['recent'][0]['path'] == str(tmp_path)
    assert result['recent'][0]['status'] == 'ready'


def test_history_is_bounded_and_discovery_deduplicates_local_layout(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, 'history_path', lambda: tmp_path / 'recent.json')
    for index in range(8):
        sources.remember({'path': str(tmp_path / str(index))})
    root = tmp_path / 'RetroArch'; (root / 'playlists').mkdir(parents=True)
    result = sources.discover(adb_runner=lambda *args, **kwargs: '', local_candidates=[{'path': str(p), 'exists': True} for p in [root, root / 'playlists']])
    assert len(result['recent']) == 5
    assert len(result['sources']) == 1
