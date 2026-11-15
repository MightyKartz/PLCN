"""Reproduce the handheld's translated filenames and incomplete DAT boundary."""
import csv
import hashlib
import json
from pathlib import Path

import pytest

from libretro_db import LibretroDB
from gallery_names import release_candidates
from playlist_analysis import analyze_playlist

ORIGINAL_GET_DAT_PATH = LibretroDB.get_dat_path
ROOT = Path(__file__).resolve().parents[2]


def test_complete_dat_and_supplement_are_both_loaded_and_legacy_cache_is_bypassed(tmp_path, monkeypatch):
    monkeypatch.setattr(LibretroDB, 'get_dat_path', ORIGINAL_GET_DAT_PATH)
    db = LibretroDB(str(tmp_path))
    supplemental = ROOT / 'data/libretro-db/supplemental/Sega - Saturn.dat'
    Path(db.dat_dir, 'Sega - Saturn.dat').write_bytes(supplemental.read_bytes())
    assert Path(db.get_dat_path('Sega - Saturn')) == ROOT / 'data/libretro-db/dat/Sega - Saturn.dat'
    assert db.load_system_dat('Sega - Saturn')
    assert db.get_standard_name('Daikoukai Jidai Gaiden (J) [T+SChi_20090423]') == 'Daikoukai Jidai Gaiden (Japan)'
    assert db.get_standard_name('CN [Dragon_Force]') is None, 'Do not invent a USA region'
    assert db.get_standard_name('Grandia CN') is None, 'Do not invent a disc'
    assert any('Policenauts' in name for names in db.standard_names.values() for name in names)
    manifest = json.loads((ROOT / 'data/libretro-db/sources.json').read_text(encoding='utf-8'))
    for system, info in manifest.items():
        main = ROOT / 'data/libretro-db/dat' / (system + '.dat')
        assert hashlib.sha256(main.read_bytes()).hexdigest() == info['sha256']
        assert info['game_blocks'] > 2000


@pytest.fixture
def saturn_library(tmp_path, monkeypatch):
    import single_artwork
    source = tmp_path / 'names'; source.mkdir()
    names = [
        ('Dragon Force (Japan) (4M)', '龙之力量'), ('Dragon Force (USA)', '龙之力量'),
        ('Daikoukai Jidai Gaiden (Japan)', '大航海时代外传'), ('Daikoukai Jidai II (Japan)', '大航海时代2'),
        ('Grandia (Japan) (Disc 1) (1M)', '格兰蒂亚'), ('Grandia (Japan) (Disc 1) (4M)', '格兰蒂亚'),
        ('Grandia (Japan) (Disc 2) (4M)', '格兰蒂亚'),
        ('Super Robot Taisen F (Japan) (Rev A)', '超级机器人大战F'), ('Super Robot Taisen F (Japan) (Rev B)', '超级机器人大战F'),
        ('Super Robot Taisen F - Kanketsu-hen (Japan)', '超级机器人大战F - 完结篇'),
        ('Thor - Seireioukiden (Japan)', '光之继承者'), ('Lunar - Silver Star Story (Japan) (Rev A)', '露娜')]
    with (source / 'Sega - Saturn.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f); writer.writerow(['Name EN', 'Name ZH']); writer.writerows(names)
    monkeypatch.setattr(single_artwork, 'catalog_names', lambda system, kind: [name for name, _ in names])
    def playlist(entries):
        path = tmp_path / 'games.lpl'
        path.write_text(json.dumps({'items':[{'path':'/Roms/SS/' + filename + '.cue', 'label':label, 'db_name':'Sega - Saturn.lpl', 'crc32':'00000000|crc'} for filename, label in entries]}, ensure_ascii=False), encoding='utf-8')
        return path
    return source, playlist


def test_saturn_preview_uses_canonical_sources_without_guessing_versions(saturn_library):
    source, playlist = saturn_library
    entries=[('龙之力量/CN [Dragon_Force]', '龙之力量'),
             ('外传/Daikoukai Jidai Gaiden (J) [T+SChi_20090423]', '大航海时代外传'),
             ('大航海时代2/DK2_SS', 'DK2_SS'),
             ('格兰蒂亚/Grandia CN (Disc 1)', '格兰蒂亚'), ('格兰蒂亚/Grandia CN (Disc 2)', '格兰蒂亚'),
             ('机战/SRWF', '超级机器人大战F'), ('机战F完结/SRWFF', '超级机器人大战F - 完结篇'),
             ('雷神/Thor - Seireioukiden (J)', '光之继承者'),
             ('露娜/Lunar - Silver Star Story (Japan) (Rev A)', '露娜')]
    path = playlist(entries); before = path.read_bytes()
    changes = analyze_playlist(path, 'Sega - Saturn', str(source), verify_artwork=True)
    assert changes[0]['thumbnail_source'] is None
    assert len(changes[0]['artwork_candidates']) == 2
    assert changes[1]['thumbnail_source'] == 'Daikoukai Jidai Gaiden (Japan)'
    assert changes[2]['new_label'] == '大航海时代2'
    assert changes[2]['thumbnail_source'] is None, 'Parent-folder identity must be confirmed'
    assert changes[2]['artwork_candidates'] == ['Daikoukai Jidai II (Japan)']
    assert changes[3]['new_label'] == '格兰蒂亚 (Disc 1)'
    assert changes[4]['new_label'] == '格兰蒂亚 (Disc 2)'
    assert all('(Disc 1)' in candidate for candidate in changes[3]['artwork_candidates'])
    assert all('(Disc 2)' in candidate for candidate in changes[4]['artwork_candidates'])
    assert all('Kanketsu-hen' not in name for name in changes[5]['artwork_candidates'])
    assert changes[6]['thumbnail_source'] == 'Super Robot Taisen F - Kanketsu-hen (Japan)'
    assert changes[7]['thumbnail_source'] == 'Thor - Seireioukiden (Japan)'
    assert changes[8]['match_diagnostics']['conflicts'] == []
    assert path.read_bytes() == before


def test_preview_reports_catalog_failures_instead_of_claiming_no_artwork(saturn_library, monkeypatch):
    import single_artwork
    source, playlist = saturn_library
    path = playlist([('Thor - Seireioukiden (J)', '光之继承者')])
    def failed(*args):
        raise RuntimeError('index unavailable')
    monkeypatch.setattr(single_artwork, 'catalog_names', failed)
    change = analyze_playlist(path, 'Sega - Saturn', str(source), verify_artwork=True)[0]
    assert change['thumbnail_source'] is None
    assert change['artwork_gallery_status'] == 'unavailable'
    assert '查询失败' in change['match_reason']


def test_release_constraints_keep_region_disc_and_revision():
    names = ['Game (Japan) (Disc 1) (Rev A)', 'Game (Japan) (Disc 2) (Rev A)', 'Game (USA) (Disc 1)']
    assert release_candidates('Game CN (J) (Disc 1) [T+SChi_1]', names) == [names[0]]
    assert release_candidates('Game (Japan) (Disc 1) (Rev B)', names) == []


def test_canonical_sources_stay_the_same_before_and_after_names_are_applied(saturn_library):
    source, playlist = saturn_library
    path = playlist([('Daikoukai Jidai Gaiden (J) [T+SChi_20090423]', 'Daikoukai Jidai Gaiden (J) [T+SChi_20090423]'),
                     ('Thor - Seireioukiden (J)', 'Thor - Seireioukiden (J)')])
    first = analyze_playlist(path, 'Sega - Saturn', str(source), verify_artwork=True)
    document = json.loads(path.read_text(encoding='utf-8'))
    for item, proposal in zip(document['items'], first):
        item['label'] = proposal['new_label']
    path.write_text(json.dumps(document), encoding='utf-8')
    second = analyze_playlist(path, 'Sega - Saturn', str(source), verify_artwork=True)
    assert [row['thumbnail_source'] for row in first] == [row['thumbnail_source'] for row in second]
    assert all(row['artwork_gallery_status'] == 'matched' for row in first + second)


def test_remote_preview_sees_missing_screenshot_even_when_cover_exists(saturn_library, monkeypatch):
    import playlist_browser
    source, playlist = saturn_library
    path = playlist([('Thor - Seireioukiden (J)', '光之继承者')])
    uri = 'mtp://device/00010001/RetroArch/thumbnails'
    lookups={kind:{'type':'mtp','uri':uri+'/Sega%20-%20Saturn/'+kind,
                   'filenames':{'光之继承者.png'} if kind != 'Named_Snaps' else set()}
             for kind in ['Named_Boxarts','Named_Snaps','Named_Titles']}
    monkeypatch.setattr(playlist_browser,'open_artwork_reader',lambda *args:(None,lookups,''))
    import playlist_analysis
    monkeypatch.setattr(playlist_analysis,'build_existing_boxart_lookup',lambda *args:lookups['Named_Boxarts'])
    row=analyze_playlist(path,'Sega - Saturn',str(source),uri,verify_artwork=True)[0]
    assert row['cover_exists'] is True
    assert row['artwork']['Named_Snaps']['status']=='missing'
    assert row['match_status']=='download'


def test_confirmed_version_survives_new_preview_with_original_remote_uri(saturn_library, monkeypatch):
    import artwork_identity
    source, playlist = saturn_library
    path = playlist([('龙之力量/CN [Dragon_Force]', '龙之力量')])
    remote = 'mtp://device/00010001/RetroArch/playlists/Sega%20-%20Saturn.lpl'
    document=json.loads(path.read_text(encoding='utf-8')); item=document['items'][0]
    monkeypatch.setenv('PLCN_HOME',str(source.parent/'runtime'))
    artwork_identity.remember({'system':'Sega - Saturn','playlist_path':remote,'rom_path':item['path'],'label':item['label']},'Dragon Force (USA)','Named_Boxarts')
    row=analyze_playlist(path,'Sega - Saturn',str(source),verify_artwork=True,source_playlist_path=remote)[0]
    assert row['thumbnail_source']=='Dragon Force (USA)'
    assert row['artwork_candidates']==['Dragon Force (USA)']


def test_raw_disc_names_and_chinese_disc_labels_resolve_to_same_candidates(saturn_library):
    source, playlist=saturn_library
    path=playlist([('格兰蒂亚/Grandia CN (Disc 1)','Grandia CN (Disc 1)'),('格兰蒂亚/Grandia CN (Disc 2)','Grandia CN (Disc 2)')])
    first=analyze_playlist(path,'Sega - Saturn',str(source),verify_artwork=True)
    document=json.loads(path.read_text(encoding='utf-8'))
    for item,row in zip(document['items'],first):item['label']=row['new_label']
    path.write_text(json.dumps(document), encoding='utf-8')
    second=analyze_playlist(path,'Sega - Saturn',str(source),verify_artwork=True)
    assert [row['artwork_candidates'] for row in first] == [row['artwork_candidates'] for row in second]
    assert first[0]['new_label']=='格兰蒂亚 (Disc 1)'
    assert first[1]['new_label']=='格兰蒂亚 (Disc 2)'


def test_chaos_seed_short_rom_does_not_become_darkseed(tmp_path, monkeypatch):
    import single_artwork
    from translator import Translator
    source = tmp_path / 'names'; source.mkdir()
    titles = [
        ('Darkseed (Japan)', '黑暗种子'),
        ('Senkutsu Katsuryu Taisen - Chaos Seed (Japan) (Disc 1) (Game Disc) (Rev A) (10M)', '仙窟活龙大战'),
        ('Senkutsu Katsuryu Taisen - Chaos Seed (Japan) (Disc 2) (Omake Disc)', '仙窟活龙大战')]
    with (source / 'Sega - Saturn.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream); writer.writerow(['Name EN', 'Name ZH']); writer.writerows(titles)
    translator = Translator(str(source), 'Sega - Saturn')
    assert translator.translate('ChaosSeed') == ('仙窟活龙大战', 'Senkutsu Katsuryu Taisen - Chaos Seed')
    assert translator.translate('Darkseed (Japan)')[0] == '黑暗种子'
    monkeypatch.setattr(single_artwork, 'catalog_names', lambda system, kind: [title for title, _ in titles])
    playlist = tmp_path / 'SS.lpl'
    playlist.write_text(json.dumps({'items':[{'path':'/storage/card/Roms/SS/仙窟活龙大战/ChaosSeed.chd',
        'label':'黑暗种子','db_name':'Sega - Saturn.lpl','crc32':'00000000|crc'}]}, ensure_ascii=False), encoding='utf-8')
    before = playlist.read_bytes()
    row = analyze_playlist(playlist, 'Sega - Saturn', str(source), verify_artwork=True)[0]
    assert row['new_label'] == '仙窟活龙大战'
    assert row['artwork_candidates']
    assert all(title.startswith('Senkutsu Katsuryu Taisen - Chaos Seed') for title in row['artwork_candidates'])
    assert playlist.read_bytes() == before


def test_gulliver_short_disc_names_match_their_own_official_images(tmp_path, monkeypatch):
    import single_artwork
    source = tmp_path / 'names'; source.mkdir()
    names = [f'Kuusou Kagaku Sekai Gulliver Boy (Japan) (Disc {disc})' for disc in (1, 2)]
    with (source / 'Sega - Saturn.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream); writer.writerow(['Name EN', 'Name ZH'])
        writer.writerows((name, '空想科学世界') for name in names)
    monkeypatch.setattr(single_artwork, 'catalog_names', lambda system, kind: names)
    playlist = tmp_path / 'SS.lpl'
    for labels in [('GulliverBoy Disc1', 'GulliverBoy Disc2'), ('空想科学世界', '空想科学世界')]:
        playlist.write_text(json.dumps({'items':[{'path':f'/Roms/SS/空想科学世界/GulliverBoy Disc{disc}.chd',
            'label':label,'db_name':'Sega - Saturn.lpl','crc32':'00000000|crc'} for disc, label in enumerate(labels, 1)]}, ensure_ascii=False), encoding='utf-8')
        before = playlist.read_bytes()
        rows = analyze_playlist(playlist, 'Sega - Saturn', str(source), verify_artwork=True)
        for disc, row in enumerate(rows, 1):
            assert row['new_label'] == f'空想科学世界 (Disc {disc})'
            assert row['thumbnail_source'] == names[disc - 1]
            assert row['artwork_candidates'] == [names[disc - 1]]
        assert playlist.read_bytes() == before
    assert release_candidates('GulliverBoy Disc1', names) == [names[0]]
    assert release_candidates('GulliverBoy Disc2', names) == [names[1]]
