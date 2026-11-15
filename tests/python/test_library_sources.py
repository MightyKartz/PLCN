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
    assert [e['status'] for e in result['recent']] == ['disconnected']
    assert result['recent'][0]['path'].startswith('adb://')


def test_legacy_recent_config_and_device_without_library(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, 'history_path', lambda: tmp_path / 'recent.json')
    config = tmp_path / 'config.json'; config.write_text(json.dumps({'retroarch_root': str(tmp_path)}))
    def adb(args, timeout=10):
        return 'List of devices attached\nserial device\n' if args == ['devices', '-l'] else ''
    result = sources.discover(config, adb_runner=adb, local_candidates=[])
    assert result['sources'][0]['status'] == 'no_library'
    assert result['recent'] == []


def test_history_is_bounded_and_discovery_deduplicates_local_layout(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, 'history_path', lambda: tmp_path / 'recent.json')
    for index in range(8):
        sources.remember({'path': str(tmp_path / str(index))})
    root = tmp_path / 'RetroArch'; (root / 'playlists').mkdir(parents=True)
    result = sources.discover(adb_runner=lambda *args, **kwargs: '', local_candidates=[{'path': str(p), 'exists': True} for p in [root, root / 'playlists']])
    assert result['recent'] == []
    assert len(sources.read_history()) == 5
    assert len(result['sources']) == 1


def test_usb_connected_without_adb_is_visible_and_local_paths_are_not_probed(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, 'history_path', lambda: tmp_path / 'recent.json')
    sources.remember({'path': str(tmp_path / 'Desktop/lpl')})
    monkeypatch.setattr(sources.scanner, 'list_adb_devices', lambda **kwargs: [])
    monkeypatch.setattr(sources, 'usb_android_devices', lambda: [{'serial':'usb-device','label':'Moorechip'}])
    def unexpected():
        raise AssertionError('Home discovery must not scan local directories')
    monkeypatch.setattr(sources.scanner, 'default_scan_candidates', unexpected)
    state = sources.discover()
    assert state['recent'] == []
    assert state['sources'][0]['status'] == 'usb_only'
    assert state['sources'][0]['serial'] == 'usb-device'


def test_connected_mtp_library_appears_once_and_history_survives_disconnect(tmp_path, monkeypatch):
    path = 'mtp://device/00010001/RetroArch'
    monkeypatch.setattr(sources, 'history_path', lambda: tmp_path / 'recent.json')
    sources.remember({'path':path, 'label':'内部共享存储空间'})
    sources.remember({'path':'adb://old/sdcard/RetroArch', 'label':'RG 476H'})
    monkeypatch.setattr(sources.scanner, 'list_adb_devices', lambda **kwargs: [])
    monkeypatch.setattr(sources, 'usb_android_devices', lambda: [])
    monkeypatch.setattr(sources, 'mtp_sources', lambda: ([{'path':path, 'label':'内部共享存储空间', 'transport':'mtp', 'status':'ready'}], None))
    result = sources.discover()
    assert [entry['path'] for entry in result['sources']] == [path]
    assert [entry['path'] for entry in result['recent']] == ['adb://old/sdcard/RetroArch']
    assert len(sources.read_history()) == 2, 'Discovery must not delete history'
    monkeypatch.setattr(sources, 'mtp_sources', lambda: ([], None))
    result = sources.discover()
    recent = next(entry for entry in result['recent'] if entry['path'] == path)
    assert recent['label'] == '内部共享存储空间'
    assert recent['status'] == 'disconnected'


def test_connected_adb_library_does_not_repeat_in_recent(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, 'history_path', lambda: tmp_path / 'recent.json')
    sources.remember({'path':'adb://online/sdcard/RetroArch/', 'label':'Old label'})
    def adb(args, timeout=10):
        return 'List of devices attached\nonline device model:RG_476H\n' if args == ['devices', '-l'] else '/sdcard/RetroArch\n'
    result = sources.discover(adb_runner=adb)
    assert result['sources'][0]['label'] == 'RG 476H'
    assert result['recent'] == []


def test_mtp_without_existing_playlist_offers_creation(tmp_path,monkeypatch):
    import mtp_runtime as mtp
    monkeypatch.setattr(mtp,'devices',lambda:[{'path':'mtp://device/00010001/','label':'Internal','transport':'mtp'}])
    monkeypatch.setattr(mtp,'scan',lambda path:{'root_path':path,'playlists':[]})
    result,error=sources.mtp_sources()
    assert error is None
    assert result[0]['status']=='no_library'
    assert result[0]['path']=='mtp://device/00010001/RetroArch'
