import json
from pathlib import Path

import pytest
import artwork_identity as identity
import single_artwork as art
from database import DatabaseManager


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setenv('PLCN_HOME', str(tmp_path / 'profile'))
    import data_pack
    path = tmp_path / 'names.sqlite3'
    db = DatabaseManager(str(path))
    conn = db.get_connection()
    conn.executemany('INSERT INTO translations (english_name,chinese_name,system) VALUES (?,?,?)', [
        ('Game (USA)', '游戏', 'GBA'), ('Game (Japan)', '游戏', 'GBA'),
        ('Game 2 (Japan)', '游戏2', 'GBA'), ('Wrong Platform', '游戏', 'NES'),
        ('Another Game', '同名游戏', 'GBA'), ('Different Game', '同名游戏', 'GBA')])
    conn.commit(); db.close()
    monkeypatch.setattr(data_pack, 'open_database', lambda source: DatabaseManager(str(path)))
    return {'system': 'GBA', 'label': '游戏', 'rom_path': '/roms/游戏.gba', 'playlist_path': 'test.lpl', 'kind': 'Named_Boxarts'}


def test_resolution_groups_regions_but_never_chooses_other_platform_or_sequel(library):
    result = identity.resolve(library)
    assert result['status'] == 'resolved' and result['query'] == 'Game'
    assert result['names'] == ['Game (Japan)', 'Game (USA)']
    assert identity.resolve({**library, 'rom_path': '/roms/Game (USA).gba'})['query'] == 'Game (USA)'
    result = identity.resolve({**library, 'label': '同名游戏', 'rom_path': '/roms/同名游戏.gba'})
    assert result['status'] == 'ambiguous' and result['query'] == ''


def test_missing_title_english_rom_and_curated_goodboy(library):
    assert identity.resolve({**library, 'label': '未知游戏', 'rom_path': '/未知.gba'})['status'] == 'unresolved'
    assert identity.resolve({**library, 'label': '未知游戏', 'rom_path': '/Known Title (USA).gba'})['query'] == 'Known Title (USA)'
    assert identity.resolve({**library, 'system': 'Nintendo - Game Boy Advance', 'label': '好狗狗星系'})['query'] == 'Goodboy Galaxy'


def test_remembered_source_is_scoped_to_game_system_and_kind(library):
    identity.remember(library, 'Chosen (USA)', 'Named_Boxarts')
    identity.remember(library, 'Chosen (Japan)', 'Named_Snaps')
    result = identity.resolve(library)
    assert result['query'] == 'Chosen (USA)' and result['reason'] == 'remembered'
    assert identity.resolve({**library, 'kind': 'Named_Snaps'})['query'] == 'Chosen (Japan)'
    assert identity.resolve({**library, 'system': 'NES'})['reason'] != 'remembered'
    assert identity.resolve({**library, 'rom_path': '/different.gba'})['reason'] != 'remembered'


def test_automatic_search_keeps_same_title_and_prioritizes_exact_region(library, monkeypatch):
    monkeypatch.setattr(art, 'catalog_names', lambda *args: ['Game 2 (USA)', 'Game (Japan)', 'Game (USA)', 'Game Adventure (USA)'])
    result = art.search({'system': 'GBA', 'query': 'Game (USA)', 'automatic': True})
    assert result['names'] == ['Game (USA)', 'Game (Japan)']
    assert result['candidates'][0]['exact'] is True
    assert art.search({'system':'GBA','query':'Game 2'})['names'] == ['Game 2 (USA)']


def test_archive_member_english_name_takes_precedence_over_outer_chinese_name(library):
    result = identity.resolve({**library, 'rom_path': '/游戏/游戏.zip#Game 2 (Japan).gba'})
    assert result['query'] == 'Game 2 (Japan)'
    result = identity.resolve({**library, 'label': '仙魔大战', 'rom_path': '/游戏/仙魔大战 (日版).zip#Bikkuriman World (Japan).pce'})
    assert result['query'] == 'Bikkuriman World (Japan)'


@pytest.mark.parametrize('number,title', [('3', 'Monshou no Nazo'), ('4', 'Seisen no Keifu'), ('5', 'Thracia 776')])
def test_numbered_chinese_roms_resolve_separately_despite_shared_label(library, number, title):
    context = {**library, 'system': 'Nintendo - Super Nintendo Entertainment System',
               'label': '火焰纹章-纹章之谜', 'rom_path': f'/roms/火焰之纹章{number}.sfc'}
    result = identity.resolve(context)
    assert result['query'] == 'Fire Emblem - ' + title
    assert result['reason'] == 'rom_alias'
    # An independent output-name suffix must not change the ROM identity.
    assert identity.resolve({**context, 'label': f'火焰之纹章{number} (2)'}) == result
    assert identity.resolve({**context, 'system': 'GBA'})['status'] == 'unresolved'


def test_numbered_rom_aliases_keep_numbers_and_do_not_guess_hacks():
    assert identity.rom_search_alias('SNES', '火焰紋章 4 (日版)') == 'Fire Emblem - Seisen no Keifu'
    assert identity.rom_search_alias('SNES', '火焰之纹章34') is None
    assert identity.rom_search_alias('SNES', '火焰之纹章4改版') is None


@pytest.mark.parametrize('label,archive,program,query', [
    ('三国志4', '三国志4', 'SAN486.COM', 'Romance of the Three Kingdoms IV - Wall of Fire'),
    ('三国志5威力加强版', '三国志5X', 'CDX.EXE', 'Romance of the Three Kingdoms V with Power Up Kit'),
    ('三国志英杰传', '三国志英杰传', 'TFDED.COM', 'Three Kingdoms Yingjie Chuan'),
    ('仙剑奇侠传', '仙剑奇侠传', 'JS3.EXE', 'Sword and Fairy'),
    ('炎龙骑士团2黄金城之谜', '炎龙骑士团2黄金城之谜', 'FD2.EXE', 'Flame Dragon 2 - Legend of Golden Castle'),
    ('轩辕剑外传：枫之舞', '轩辕剑外传：枫之舞', 'SWDA.EXE', 'Xuan-Yuan Sword - Dance of the Maple Leaves'),
    ('金庸群侠传', '金庸群侠传', 'Z.COM', 'Jin Yong Qun Xia Chuan'),
])
def test_dos_uses_full_game_names_not_generic_executables(library, label, archive, program, query):
    result = identity.resolve({**library, 'system': 'DOS', 'label': label,
                               'rom_path': f'/DOS/{archive}.zip#{program}'})
    assert result['status'] == 'resolved'
    assert result['query'] == query
    unknown = identity.resolve({**library, 'system': 'DOS', 'label': '未知游戏',
                                'rom_path': f'/DOS/未知游戏.zip#{program}'})
    assert unknown['status'] == 'unresolved'
    assert unknown['query'] == ''


def test_dos_verified_alias_and_english_archive_are_searchable(library):
    context = {**library, 'system': 'DOS', 'label': '大航海时代2',
               'rom_path': '/DOS/大航海时代2.zip#KOUKAI2.COM'}
    assert identity.resolve(context)['query'] == 'Uncharted Waters 2 - New Horizons (1995)'
    assert identity.resolve({**context, 'label': '未知', 'rom_path': '/DOS/大航海时代2.7z#KOUKAI2.COM'})['reason'] == 'curated'
    assert identity.resolve({**context, 'label': '未知', 'rom_path': '/DOS/Uncharted Waters 2 - New Horizons.zip#START.BAT'})['query'] == 'Uncharted Waters 2 - New Horizons'
    assert identity.resolve({**context, 'label': '未知', 'rom_path': '/DOS/大航海时代2加强版.zip#START.BAT'})['status'] == 'unresolved'
    assert identity.resolve({**context, 'label': '三国志4 (威力加强版)', 'rom_path': '/DOS/未知.zip#START.BAT'})['status'] == 'unresolved'
    assert identity.resolve({**context, 'label': '軒轅劍外傳-楓之舞', 'rom_path': '/DOS/未知.zip#START.BAT'})['query'] == 'Xuan-Yuan Sword - Dance of the Maple Leaves'


def test_dos_bulk_preview_preserves_labels_and_does_not_offer_launcher_downloads(library, tmp_path, monkeypatch):
    import plcn
    from types import SimpleNamespace
    monkeypatch.setattr(plcn, 'Translator', lambda *args: SimpleNamespace(db=SimpleNamespace()))
    calls = []
    def catalog(*args):
        calls.append(args)
        return ['Uncharted Waters 2 - New Horizons (1995)', 'Sword and Fairy 2 (1999)']
    monkeypatch.setattr(art, 'catalog_names', catalog)
    path = tmp_path / 'DOS.lpl'
    items = [{'label': label, 'path': f'/DOS/{label}.zip#{exe}', 'db_name': 'DOS.lpl'}
             for label, exe in [('仙剑奇侠传', 'JS3.EXE'), ('大航海时代2', 'KOUKAI2.COM')]]
    path.write_text(json.dumps({'items': items}, ensure_ascii=False), encoding='utf-8')
    before = path.read_bytes()
    changes = plcn.analyze_playlist(str(path), 'DOS', 'unused')
    assert path.read_bytes() == before
    assert [c['new_label'] for c in changes] == [i['label'] for i in items]
    assert changes[0]['thumbnail_source'] is None
    assert changes[0]['artwork_identity_status'] == 'resolved'
    assert changes[0]['artwork_query'] == 'Sword and Fairy'
    assert changes[0]['artwork_gallery_status'] == 'not_found'
    assert changes[0]['match_diagnostics']['conflicts'] == []
    assert '证据冲突' not in changes[0]['match_reason']
    assert changes[1]['thumbnail_source'] == 'Uncharted Waters 2 - New Horizons (1995)'
    assert changes[1]['artwork_gallery_status'] == 'matched'
    assert calls == [('DOS', 'Named_Boxarts')]

    def offline(*args):
        calls.append(args)
        raise RuntimeError('offline')
    calls.clear()
    monkeypatch.setattr(art, 'catalog_names', offline)
    changes = plcn.analyze_playlist(str(path), 'DOS', 'unused')
    assert all(c['artwork_gallery_status'] == 'unavailable' and not c['thumbnail_source'] for c in changes)
    assert all(c['artwork_query'] for c in changes)
    assert len(calls) == 1
    assert path.read_bytes() == before
