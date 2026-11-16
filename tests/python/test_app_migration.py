import json
from pathlib import Path

import pytest

import app_paths
from app_migration import migrate
from app_runtime import InstanceLock
import repair_history
from safe_io import file_digest


def test_old_environment_is_ignored_and_new_override_is_used(tmp_path):
    assert app_paths.user_data_dir('linux', {'PLCN_HOME': str(tmp_path)}, tmp_path) == tmp_path / '.local/share/RetroArchAssistant'
    assert app_paths.user_data_dir('linux', {'RETROARCH_ASSISTANT_HOME': str(tmp_path)}, tmp_path) == tmp_path


def test_migration_relocates_rules_and_receipts_preserving_backup_bytes(tmp_path, monkeypatch):
    old, new = tmp_path / 'old', tmp_path / 'new'
    old.mkdir()
    monkeypatch.setenv('RETROARCH_ASSISTANT_HOME', str(old))
    app_paths.initialize()
    playlist = tmp_path / 'game.lpl'
    original = b'{"items": [{"label": "Original"}]}'
    backup = old / 'playlist-backups/game.bak'
    backup.parent.mkdir()
    backup.write_bytes(original)
    playlist.write_bytes(b'{"items": [{"label": "Changed"}]}')
    ident = repair_history.record_write(playlist, backup, 1)
    (old / 'manual_overrides.json').write_text('[{"name":"中文"}]')
    (old / 'config.json').write_text(json.dumps({'manual_overrides_path': str(old / 'manual_overrides.json')}))
    transaction = old / 'm3u-operations/test'
    transaction.mkdir(parents=True)
    snapshot = transaction / 'metadata-0-before.json'
    snapshot.write_text(json.dumps({'path': str(old / 'original')}))
    digest = file_digest(snapshot)
    (transaction / 'manifest.json').write_text(json.dumps({'backup':str(snapshot), 'backup_digest':digest}))
    (old / 'cache/plcn.db').write_bytes(b'cached database')
    monkeypatch.setenv('RETROARCH_ASSISTANT_HOME', str(new))
    migrate(old)
    assert not old.exists()
    assert json.loads((new / 'config.json').read_text())['manual_overrides_path'] == str(new / 'manual_overrides.json')
    assert json.loads((new / 'manual_overrides.json').read_text())[0]['name'] == '中文'
    manifest = json.loads((new / 'm3u-operations/test/manifest.json').read_text())
    assert manifest['backup'] == str(new / 'm3u-operations/test/metadata-0-before.json')
    assert file_digest(manifest['backup']) == digest
    assert (new / 'cache/library.db').read_bytes() == b'cached database'
    repair_history.restore(ident)
    assert playlist.read_bytes() == original
    assert (new / 'playlist-backups/game.bak').read_bytes() == original


def test_separate_cache_migration(tmp_path, monkeypatch):
    old, cache = tmp_path / 'old', tmp_path / 'old-cache'
    old.mkdir(); cache.mkdir()
    (cache / 'plcn.db').write_bytes(b'db')
    (old / 'config.json').write_text(json.dumps({'cache_path': str(cache / 'data')}))
    new, new_cache = tmp_path / 'new', tmp_path / 'new-cache'
    monkeypatch.setattr(app_paths, 'user_data_dir', lambda: new)
    monkeypatch.setattr(app_paths, 'cache_dir', lambda: new_cache)
    migrate(old, cache)
    assert not cache.exists()
    assert (new_cache / 'library.db').read_bytes() == b'db'
    assert json.loads((new / 'config.json').read_text())['cache_path'] == str(new_cache / 'data')


def test_existing_destination_and_running_source_are_refused(tmp_path, monkeypatch):
    old, new = tmp_path / 'old', tmp_path / 'new'
    old.mkdir(); new.mkdir()
    (new / 'config.json').write_text('{"mine":true}')
    monkeypatch.setenv('RETROARCH_ASSISTANT_HOME', str(new))
    with pytest.raises(ValueError, match='already exists'):
        migrate(old)
    assert json.loads((new / 'config.json').read_text()) == {'mine':True}
    (new / 'config.json').unlink(); new.rmdir()
    lock = InstanceLock(old)
    assert lock.acquire()
    try:
        with pytest.raises(ValueError, match='Quit'):
            migrate(old)
        assert not new.exists()
    finally:
        lock.close()


def test_invalid_live_json_preserves_source(tmp_path, monkeypatch):
    old, new = tmp_path / 'old', tmp_path / 'new'
    old.mkdir(); (old / 'config.json').write_text('broken')
    monkeypatch.setenv('RETROARCH_ASSISTANT_HOME', str(new))
    with pytest.raises(ValueError):
        migrate(old)
    assert (old / 'config.json').read_text() == 'broken'
    assert not new.exists()


def test_separate_cache_can_move_into_portable_profile(tmp_path, monkeypatch):
    old, cache, new = tmp_path / 'old', tmp_path / 'old-cache', tmp_path / 'portable'
    old.mkdir(); cache.mkdir()
    (cache / 'plcn.db').write_bytes(b'cached')
    monkeypatch.setenv('RETROARCH_ASSISTANT_HOME', str(new))
    migrate(old, cache)
    assert (new / 'cache/library.db').read_bytes() == b'cached'
    assert not old.exists() and not cache.exists()
