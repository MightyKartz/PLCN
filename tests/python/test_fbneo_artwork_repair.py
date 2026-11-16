import io
import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from artwork_identity import title_key
from artwork_resolver import valid_png
from libretro_db import LibretroDB
from playlist_analysis import analyze_playlist
from thumbnail_downloader import ThumbnailDownloader
from title_family import resolve_artwork


def test_literal_rom_alias_survives_title_normalization_collision(tmp_path, monkeypatch):
    db = LibretroDB(str(tmp_path))
    monkeypatch.setattr(LibretroDB, 'get_dat_path', lambda self, name: str(Path(self.dat_dir, name + '.dat')))
    Path(db.dat_dir, 'Example.dat').write_text('''game (
name "Dogyuun (World)"
rom ( name dogyuun.zip crc ABCD1234 )
)
game (
name "Dogyuun (Japan)"
rom ( name dogyuunj.zip crc 1234ABCD )
)
''')
    assert db.load_system_dat('Example')
    assert db.get_standard_name('dogyuun') == 'Dogyuun (World)'
    assert db.get_standard_name('DOGYUUN.ZIP') == 'Dogyuun (World)'
    assert db.get_standard_name('dogyuunj') == 'Dogyuun (Japan)'


def test_chinese_labels_do_not_override_arcade_zip_and_collisions_are_stable(tmp_path, monkeypatch):
    dat = tmp_path / 'arcade.dat'
    dat.write_text('\n'.join(f'game (\nname "{name}"\nrom ( name {stem}.zip )\n)' for stem, name in [
        ('dogyuun', 'Dogyuun'), ('gururin', 'Gururin'),
        ('altbeast', 'Altered Beast (set 8) (8751 317-0078)'),
        ('altbeast2', 'Altered Beast (set 2) (MC-8123B 317-0066)')]))
    monkeypatch.setattr(LibretroDB, 'get_dat_path', lambda *args: str(dat))
    monkeypatch.setattr('single_artwork.catalog_names', lambda *args: [
        'Dogyuun', 'Gururin', 'Altered Beast (set 8) (8751 317-0078)',
        'Altered Beast (set 2) (MC-8123B 317-0066)'])
    playlist = tmp_path / 'games.lpl'
    items = [{'path': '/roms/' + stem + '.zip', 'label': label}
             for stem, label in [('dogyuun', '方块小人'), ('gururin', '方块小人'),
                                 ('altbeast', '兽王记'), ('altbeast2', '兽王记')]]
    playlist.write_text(json.dumps({'items': items}))
    rows = analyze_playlist(str(playlist), 'FBNeo - Arcade Games', 'data/rom-name-cn', verify_artwork=True)
    assert title_key(rows[0]['thumbnail_source']) == 'dogyuun'
    assert title_key(rows[1]['thumbnail_source']) == 'gururin'
    assert len({r['new_label'] for r in rows}) == 4
    assert all(not r['identity']['requires_review'] for r in rows)
    assert all(r['artwork_gallery_status'] == 'matched' for r in rows)
    for item, row in zip(items, rows):
        item['label'] = row['new_label']
    playlist.write_text(json.dumps({'items': items}))
    again = analyze_playlist(str(playlist), 'FBNeo - Arcade Games', 'data/rom-name-cn', verify_artwork=True)
    assert [r['new_label'] for r in again] == [r['new_label'] for r in rows]


def test_arcade_gallery_handles_dates_and_release_annotation_changes(monkeypatch):
    names = ['Gekirindan (Ver 2.3O 1995_09_21)', 'Sengoku 3 _ Sengoku Densho 2001 (set 1)',
             'Aero Fighters', 'Aero Fighters 2']
    monkeypatch.setattr('single_artwork.catalog_names', lambda *args: names)
    sources = ['Gekirindan (Ver 2.3O 1995/09/21)', 'Sengoku 3 / Sengoku Densho 2001',
               'Aero Fighters (World / USA + Canada / Korea / Hong Kong / Taiwan) (newer hardware)']
    rows = [dict(system='FBNeo - Arcade Games', thumbnail_source=s, match_source='libretro-dat-rom') for s in sources]
    resolve_artwork(rows, True)
    assert [r['thumbnail_source'] for r in rows] == names[:3]


def test_truncated_arcade_cover_uses_valid_same_game_snapshot(tmp_path, monkeypatch):
    data = io.BytesIO()
    Image.new('RGB', (2, 2), 'green').save(data, format='PNG')
    good = data.getvalue()
    source = 'Super Puzzle Fighter II X (Japan 960531)'
    monkeypatch.setattr('single_artwork.catalog_names', lambda *args: [source])
    downloader = ThumbnailDownloader(str(tmp_path))
    task = ('FBNeo - Arcade Games', source, '超级街霸方块')
    downloader.cover_fallbacks[task] = 'Named_Snaps'
    downloader.session.get = lambda url, **kwargs: SimpleNamespace(
        status_code=200, content=good[:30] if '/Named_Boxarts/' in url else good)
    results = downloader.download_thumbnail(*task)
    assert all(r['status'] == 'success' for r in results)
    assert results[0]['gallery_kind'] == 'Named_Snaps'
    assert '/Named_Boxarts/' in results[0]['path']
    assert all(valid_png(Path(r['path']).read_bytes()) for r in results)


def test_arcade_per_type_revision_fallback_keeps_title_and_manual_choice():
    from gallery_names import matching_artwork_name
    source = 'Rohga Armor Force (Asia_Europe v3.0 set 1)'
    names = ['Rohga Armor Force (Asia_Europe v5.0)', 'Rohga Armor Force II (World)']
    assert matching_artwork_name('FBNeo - Arcade Games', source, names, constraints=[]) == names[0]
    assert matching_artwork_name('FBNeo - Arcade Games', source, names) is None
    assert matching_artwork_name('FBNeo - Arcade Games', source, names[1:], constraints=[]) is None
