"""CLI boundaries dispatch to the same service used by HTTP handlers."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import app_paths
import retroarch_assistant as plcn


@pytest.mark.parametrize('batch', [False, True], ids=['single', 'batch'])
def test_cli_arguments_override_config_and_preserve_manual_overrides(tmp_path, monkeypatch, batch):
    monkeypatch.setenv('RETROARCH_ASSISTANT_HOME', str(tmp_path / 'home'))
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'playlist_path': 'old.lpl', 'system_name': 'old',
                                  'thumbnails_dir': 'old-images', 'rom_name_cn_path': 'old-source',
                                  'manual_overrides_path': 'overrides.json'}), encoding='utf-8')
    monkeypatch.setattr(plcn, 'CONFIG_FILE', str(config))
    calls = []
    monkeypatch.setattr(plcn, 'process_directory' if batch else 'process_playlist', lambda *args: calls.append(args))
    args = ['retroarch-assistant', '--thumbnails-dir', 'images', '--rom-name-cn-path', 'source']
    args += ['--batch-dir', 'playlists'] if batch else ['--playlist', 'game.lpl', '--system', 'NES']
    monkeypatch.setattr(sys, 'argv', args)
    plcn.main()
    expected = ('playlists', 'images', 'source', 'overrides.json') if batch else (
        'game.lpl', 'NES', 'images', 'source', 'overrides.json')
    assert calls == [expected]


@pytest.mark.parametrize('module', ['playlist_service', 'playlist_writeback', 'playlist_artwork'])
def test_core_import_does_not_load_cli_or_http_server(tmp_path, module):
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2] / 'src'), RETROARCH_ASSISTANT_HOME=str(tmp_path))
    result = subprocess.run([sys.executable, '-c',
                             f"import {module}, sys; assert 'server' not in sys.modules; assert 'retroarch_assistant' not in sys.modules"
                             + ("; assert 'playlist_analysis' not in sys.modules; assert 'translator' not in sys.modules"
                                if module != 'playlist_service' else '')],
                            env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_cli_directory_pipeline_analyzes_writes_and_skips_unknown_system(tmp_path, monkeypatch):
    import playlist_service
    from thumbnail_downloader import ThumbnailDownloader
    monkeypatch.setenv('RETROARCH_ASSISTANT_HOME', str(tmp_path / 'home'))
    directory = tmp_path / 'playlists'
    directory.mkdir()
    source = tmp_path / 'source'
    source.mkdir()
    system = 'Nintendo - Nintendo Entertainment System'
    (source / (system + '.csv')).write_text('Name EN,Name CN\nGame,游戏\n', encoding='utf-8')
    playlist = directory / (system + '.lpl')
    playlist.write_text(json.dumps({'items': [{'label':'Game', 'path':'/roms/Game.nes', 'db_name':system + '.lpl'}]}), encoding='utf-8')
    empty = directory / 'Unknown.lpl'
    empty.write_text('{"items": []}', encoding='utf-8')
    original = playlist.read_bytes()
    empty_original = empty.read_bytes()
    downloads = []
    def download(_self, tasks, **_kwargs):
        downloads.extend(tasks)
        return ThumbnailDownloader.empty_summary()
    monkeypatch.setattr(ThumbnailDownloader, 'download_batch', download)
    playlist_service.process_directory(str(directory), str(tmp_path / 'images'), str(source))
    assert json.loads(playlist.read_text(encoding='utf-8'))['items'][0]['label'] == '游戏'
    assert empty.read_bytes() == empty_original
    assert downloads and all(task == (system, 'Game', '游戏') for task in downloads)
    backups = list((app_paths.user_data_dir() / 'playlist-backups').glob('*.bak-*'))
    assert len(backups) == 1 and backups[0].read_bytes() == original
