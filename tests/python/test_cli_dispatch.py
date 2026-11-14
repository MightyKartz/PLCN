"""CLI boundaries dispatch to the same service used by HTTP handlers."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import app_paths
import plcn


@pytest.mark.parametrize('batch', [False, True], ids=['single', 'batch'])
def test_cli_arguments_override_config_and_preserve_manual_overrides(tmp_path, monkeypatch, batch):
    monkeypatch.setenv('PLCN_HOME', str(tmp_path / 'home'))
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'playlist_path': 'old.lpl', 'system_name': 'old',
                                  'thumbnails_dir': 'old-images', 'rom_name_cn_path': 'old-source',
                                  'manual_overrides_path': 'overrides.json'}), encoding='utf-8')
    monkeypatch.setattr(plcn, 'CONFIG_FILE', str(config))
    calls = []
    monkeypatch.setattr(plcn, 'process_directory' if batch else 'process_playlist', lambda *args: calls.append(args))
    args = ['plcn', '--thumbnails-dir', 'images', '--rom-name-cn-path', 'source']
    args += ['--batch-dir', 'playlists'] if batch else ['--playlist', 'game.lpl', '--system', 'NES']
    monkeypatch.setattr(sys, 'argv', args)
    plcn.main()
    expected = ('playlists', 'images', 'source', 'overrides.json') if batch else (
        'game.lpl', 'NES', 'images', 'source', 'overrides.json')
    assert calls == [expected]


def test_core_import_does_not_load_cli_or_http_server(tmp_path):
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2] / 'src'), PLCN_HOME=str(tmp_path))
    result = subprocess.run([sys.executable, '-c',
                             "import playlist_service, sys; assert 'server' not in sys.modules; assert 'plcn' not in sys.modules"],
                            env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
