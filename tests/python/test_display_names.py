import io
import json

import pytest
from PIL import Image

from display_names import normalize_proposals
from playlist_analysis import analyze_playlist
from playlist_writeback import apply_changes
from artwork_resolver import artwork_path


@pytest.mark.parametrize('label,path,expected', [
    ('游戏 (Disc 01)', '/roms/Game.cue', '游戏（第1盘）'),
    ('游戏', '/roms/Game [Disc2of3].chd', '游戏（第2盘）'),
    ('游戏（第2盘）', '/roms/Game (Disc 2).cue', '游戏（第2盘）'),
    ('游戏 (A)', '/roms/Game (A).cue', '游戏（A）'),
    ('游戏 (B)', '/roms/Game (B).cue', '游戏（B）'),
    ('游戏v1.0', '/roms/Game (Rev 1).cue', '游戏'),
    ('游戏 (Rev A)', '/roms/Game.cue', '游戏'),
    ('游戏 国际版', '/roms/Game.cue', '游戏 国际版'),
    ('游戏 加强版 外传', '/roms/Game.cue', '游戏 加强版 外传'),
    ('Revival', '/roms/Revival.cue', 'Revival'),
    ('Version 1.0', '/roms/Version 1.0.cue', 'Version 1.0'),
    ('游戏 (Disc 1)', '/roms/Game.m3u', '游戏'),
])
def test_common_display_name_policy_is_idempotent(label, path, expected):
    row = {'system': 'PS1', 'path': path, 'new_label': label}
    normalize_proposals([row])
    assert row['new_label'] == expected
    normalize_proposals([row])
    assert row['new_label'] == expected
    assert row['path'] == path


def test_simultaneous_versions_remain_distinguishable():
    rows = [{'system': 'PS1', 'path': '/roms/Game v' + v + '.cue', 'new_label': '游戏v' + v}
            for v in ['1.0', '1.1']]
    normalize_proposals(rows)
    assert [r['new_label'] for r in rows] == ['游戏（v1.0）', '游戏（v1.1）']
    normalize_proposals(rows)
    assert [r['new_label'] for r in rows] == ['游戏（v1.0）', '游戏（v1.1）']


@pytest.mark.parametrize('download', [False, True])
def test_renaming_reuses_all_artwork_and_remains_identified_on_next_preview(tmp_path, monkeypatch, download):
    source = tmp_path / 'names'; source.mkdir()
    (source / 'Sony - PlayStation.csv').write_text('Name EN,Name CN\nGame (Japan) (Rev 1),游戏v1.0\n', encoding='utf-8')
    playlist = tmp_path / 'PS1.lpl'
    item = {'label': '游戏v1.0', 'path': '/roms/Game (Japan) (Rev 1).cue'}
    playlist.write_text(json.dumps({'items': [item]}))
    images = tmp_path / 'images'
    buffer = io.BytesIO(); Image.new('RGB', (2, 2)).save(buffer, format='PNG')
    for kind in ['Named_Boxarts', 'Named_Snaps', 'Named_Titles']:
        old = artwork_path(images, 'Sony - PlayStation', '游戏v1.0', kind)
        old.parent.mkdir(parents=True, exist_ok=True); old.write_bytes(buffer.getvalue())
    rows = analyze_playlist(str(playlist), 'Sony - PlayStation', str(source), str(images))
    assert rows[0]['new_label'] == '游戏'
    assert rows[0]['display_metadata']['version'] == 'v1.0'
    def unexpected(*args, **kwargs):
        pytest.fail('Existing artwork must be reused without network access')
    monkeypatch.setattr('requests.Session.get', unexpected)
    apply_changes(str(playlist), rows, str(images), download_thumbnails=download)
    for kind in ['Named_Boxarts', 'Named_Snaps', 'Named_Titles']:
        assert artwork_path(images, 'Sony - PlayStation', '游戏', kind).read_bytes() == buffer.getvalue()
        assert artwork_path(images, 'Sony - PlayStation', '游戏v1.0', kind).read_bytes() == buffer.getvalue()
    again = analyze_playlist(str(playlist), 'Sony - PlayStation', str(source), str(images))
    assert again[0]['new_label'] == '游戏'
    assert again[0]['identity']['requires_review'] is False
    assert json.loads(playlist.read_text())['items'][0]['path'] == item['path']


@pytest.mark.parametrize('transport', ['mtp', 'adb'])
@pytest.mark.parametrize('download', [False, True])
def test_remote_rename_reuses_old_label_artwork_without_downloading(tmp_path, monkeypatch, transport, download):
    import mtp_runtime as mtp
    from playlist_transport import apply_playlist
    from playlist_proposals import build_change_proposal
    system = 'Sony - PlayStation'
    item = {'label': '游戏 (Disc 1)', 'path': '/roms/Game (Disc 1).cue'}
    playlist = tmp_path / 'PS1.lpl'
    playlist.write_text(json.dumps({'items': [item]}))
    row = build_change_proposal(0, item, item['label'], '游戏（第1盘）', 'Game (Japan) (Disc 1)', system)
    row['display_metadata'] = {'original_label': item['label']}
    root = 'mtp://device/00010001/RetroArch/thumbnails' if transport == 'mtp' else 'adb://device/RetroArch/thumbnails'
    buffer = io.BytesIO(); Image.new('RGB', (2, 2)).save(buffer, format='PNG')
    files = {}
    def target(*parts):
        return mtp.join(root, *parts) if transport == 'mtp' else root + '/' + '/'.join(parts)
    for kind in ['Named_Boxarts', 'Named_Snaps', 'Named_Titles']:
        files[target(system, kind, item['label'] + '.png')] = buffer.getvalue()
    monkeypatch.setattr('single_artwork.read_target', lambda path: files.get(path))
    published = {}
    def push(local, remote, **kwargs):
        from pathlib import Path
        selected = kwargs.get('include_files')
        for path in Path(local).rglob('*.png'):
            relative = path.relative_to(local)
            if selected is None or str(relative) in selected:
                published[target(*relative.parts)] = path.read_bytes()
    monkeypatch.setattr(mtp, 'push_directory', push)
    monkeypatch.setattr('playlist_transport.push_adb_directory', push)
    def unexpected(*args, **kwargs):
        pytest.fail('Existing remote artwork must be reused without HTTP downloads')
    monkeypatch.setattr('requests.Session.get', unexpected)
    apply_playlist(str(playlist), [row], root,
                   options={'write_names': True, 'download_thumbnails': download, 'backup': True},
                   progress=lambda *args: None, cancel_check=lambda: False)
    for kind in ['Named_Boxarts', 'Named_Snaps', 'Named_Titles']:
        assert published[target(system, kind, '游戏（第1盘）.png')] == buffer.getvalue()
        assert files[target(system, kind, item['label'] + '.png')] == buffer.getvalue()
