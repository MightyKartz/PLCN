"""Regression for the bundled Mega Drive title and translated ROM filename."""
import json
from pathlib import Path
import shutil

import pytest

from playlist_analysis import analyze_playlist


@pytest.mark.parametrize('filename,label', [
    ('Bahamut Senki (Japan).md', 'Bahamut Senki (Japan)'),
    ('Bahamut_Senki_MD_CN_v1.0.md', 'Bahamut_Senki_MD_CN_v1.0'),
    ('Bahamut_Senki_MD_CN_v1.0.md', '巴哈姆特战记'),
])
def test_bahamut_senki_uses_correct_chinese_title(tmp_path, monkeypatch, filename, label):
    system = 'Sega - Mega Drive - Genesis'
    source = tmp_path / 'names'
    source.mkdir()
    shutil.copyfile(Path(__file__).resolve().parents[2] / 'data/rom-name-cn' / (system + '.csv'), source / (system + '.csv'))
    monkeypatch.setattr('single_artwork.catalog_names', lambda *args: ['Bahamut Senki (Japan)'])
    playlist = tmp_path / (system + '.lpl')
    playlist.write_text(json.dumps({'items': [{'path': '/Roms/MD/' + filename, 'label': label, 'db_name': system + '.lpl'}]}), encoding='utf-8')
    before = playlist.read_bytes()
    row, = analyze_playlist(str(playlist), system, str(source), verify_artwork=True)
    assert row['new_label'] == '巴哈姆特战记'
    assert row['thumbnail_source'] == 'Bahamut Senki (Japan)'
    assert playlist.read_bytes() == before
