import csv
import json

import pytest

from playlist_analysis import analyze_playlist


@pytest.mark.parametrize('system', [
    'Nintendo - Super Nintendo Entertainment System', 'Nintendo - Nintendo Entertainment System',
    'Nintendo - Game Boy Advance', 'Sony - PlayStation', 'Sega - Mega Drive - Genesis',
    'Sega - Saturn', 'DOS',
])
def test_chinese_filename_matches_regions_and_revisions_on_every_system(tmp_path, monkeypatch, system):
    source = tmp_path / 'names'
    source.mkdir()
    names = [('Frontier (Japan)', '边境任务'), ('Frontier (Japan) (Rev 1)', '边境任务'),
             ('Frontier (USA)', '边境任务'), ('Frontier II (Japan)', '边境任务2')]
    with (source / (system + '.csv')).open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Name EN', 'Name CN'])
        writer.writerows(names)
    monkeypatch.setattr('single_artwork.catalog_names', lambda *args: [n[0] for n in names])
    playlist = tmp_path / 'games.lpl'
    playlist.write_text(json.dumps({'items': [{'label': '边境任务', 'path': '/roms/边境任务.sfc'}]}), encoding='utf-8')
    before = playlist.read_bytes()
    for _ in range(2):
        row = analyze_playlist(str(playlist), system, str(source), verify_artwork=True)[0]
        assert not row['identity']['requires_review']
        assert not row['identity']['release_verified']
        assert row['new_label'] == '边境任务'
        assert row['thumbnail_source'] == 'Frontier (Japan)'
        assert row['artwork_recommended']
        assert playlist.read_bytes() == before


def test_title_components_aliases_mixed_scripts_and_ambiguity(tmp_path, monkeypatch):
    system = 'Nintendo - Super Nintendo Entertainment System'
    source = tmp_path / 'names'
    source.mkdir()
    names = [('Legend (Japan)', '传说系列 - 三角力量'),
             ('Metal Returns (Japan)', '钢铁战记 - 回归'),
             ('Dai-4-ji Battle (Japan)', '第四次机器人大战'),
             ('Space A (Japan)', '宇宙旅人'), ('Space B (Japan)', '宇宙旅者'),
             ('Chronicle II (Japan)', '编年史2')]
    with (source / (system + '.csv')).open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Name EN', 'Name CN'])
        writer.writerows(names)
    (source / 'name_alias(Chinese).json').write_text(json.dumps({
        'series': {'default': '传说系列', 'alias': ['传说物语']}}), encoding='utf-8')
    monkeypatch.setattr('single_artwork.catalog_names', lambda *args: [n[0] for n in names])
    queries = ['传说物语 三角力量', '钢铁战记Returns', '第4次机器人大战',
               '宇宙旅', '编年史3', '钢铁战记 (Unknown Hack)']
    playlist = tmp_path / 'games.lpl'
    playlist.write_text(json.dumps({'items': [{'label': q, 'path': '/roms/' + q + '.sfc'} for q in queries]}), encoding='utf-8')
    rows = analyze_playlist(str(playlist), system, str(source), verify_artwork=True)
    assert all(not r['identity']['requires_review'] for r in rows[:3])
    assert [r['new_label'] for r in rows[:3]] == queries[:3]
    assert all(r['identity']['requires_review'] for r in rows[3:])


def test_manual_display_title_and_checksum_identity_are_preserved(tmp_path):
    from types import SimpleNamespace
    from chinese_title_match import resolve_chinese_titles

    records = [{'english_name': 'Frontier (Japan)', 'chinese_name': '边境任务'}]
    connection = SimpleNamespace(execute=lambda *args: SimpleNamespace(fetchall=lambda: records))
    db = SimpleNamespace(expand_system_mapping=lambda system: [system], get_connection=lambda: connection)
    translators = {'SNES': SimpleNamespace(rom_name_cn_path=str(tmp_path), db=db)}
    rows = [
        {'system': 'SNES', 'path': '/roms/边境任务.sfc', 'match_source': 'playlist',
         'original_item_label': '我的收藏', 'new_label': '我的收藏'},
        {'system': 'SNES', 'path': '/roms/边境任务.sfc', 'match_source': 'playlist',
         'original_item_label': '边境任务', 'new_label': '边境任务',
         'match_diagnostics': {'evidence_chain': [{'source': 'playlist_crc32',
                                                  'resolved_name': 'Another Game (Japan)'}]}},
    ]
    before = json.dumps(rows)
    resolve_chinese_titles(rows, translators)
    assert json.dumps(rows) == before


def test_unknown_release_uses_available_same_title_artwork_without_claiming_region(monkeypatch):
    from title_family import resolve_artwork

    gallery = ['Frontier (USA, Europe)', 'Frontier II (Japan)']
    monkeypatch.setattr('single_artwork.catalog_names', lambda *args: gallery)
    row = {'system': 'Nintendo - Game Boy Advance', 'translation_match_source': 'title_family',
           'thumbnail_source': 'Frontier (Japan)',
           'chinese_title_sources': ['Frontier (Japan)', 'Frontier (USA)'],
           'chinese_title_constraints': []}
    resolve_artwork([row], True)
    assert row['thumbnail_source'] == 'Frontier (USA, Europe)'
    assert row['artwork_candidates'] == ['Frontier (USA, Europe)']
    row.update(thumbnail_source='Frontier (Japan)', chinese_title_constraints=['japan'])
    resolve_artwork([row], True)
    assert row['thumbnail_source'] is None


def test_catalog_chinese_alias_preserves_user_name_and_resolves_artwork():
    from pathlib import Path
    from types import SimpleNamespace
    from chinese_title_match import resolve_chinese_titles

    records = [{'english_name': 'Hagane (Japan)', 'chinese_name': '修罗战士 - 钢'}]
    connection = SimpleNamespace(execute=lambda *args: SimpleNamespace(fetchall=lambda: records))
    db = SimpleNamespace(expand_system_mapping=lambda system: [system], get_connection=lambda: connection)
    source = Path(__file__).resolve().parents[2] / 'data' / 'rom-name-cn'
    translators = {'SNES': SimpleNamespace(rom_name_cn_path=str(source), db=db)}
    row = {'system': 'SNES', 'path': '/roms/钢忍.smc', 'match_source': 'playlist',
           'original_item_label': '钢忍', 'original_label': '钢忍', 'new_label': '钢忍'}
    resolve_chinese_titles([row], translators)
    assert row['new_label'] == '钢忍'
    assert row['thumbnail_source'] == 'Hagane (Japan)'
    assert row['translation_match_source'] == 'title_family'


@pytest.mark.parametrize('system,matched', [('Sega - Mega Drive - Genesis', True),
                                           ('Nintendo - Super Nintendo Entertainment System', False)])
def test_full_title_alias_is_platform_scoped_and_keeps_regional_sequel_numbers(tmp_path, monkeypatch, system, matched):
    source = tmp_path / 'names'
    source.mkdir()
    with (source / (system + '.csv')).open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Name EN', 'Name CN'])
        writer.writerow(['Shadow III (USA)', '影子大师3'])
    (source / 'title_aliases.json').write_text(json.dumps([
        {'system': 'Sega - Mega Drive - Genesis', 'english_name': 'Shadow III (USA)',
         'chinese_name': '超级暗影2', 'aliases': ['超级暗影3']},
        {'system': 'Sega - Mega Drive - Genesis', 'english_name': 'New Homebrew',
         'chinese_name': '新作', 'aliases': ['新作别名']}
    ]), encoding='utf-8')
    monkeypatch.setattr('single_artwork.catalog_names', lambda *args: ['Shadow III (USA)'])
    playlist = tmp_path / 'games.lpl'
    names = ['超级暗影3', '超级暗影3外传', '新作别名']
    playlist.write_text(json.dumps({'items': [{'label': n, 'path': '/roms/' + n + '.bin'} for n in names]}), encoding='utf-8')
    rows = analyze_playlist(str(playlist), system, str(source), verify_artwork=True)
    assert rows[0]['identity']['requires_review'] is not matched
    assert rows[1]['identity']['requires_review']
    assert rows[2]['identity']['requires_review'] is not matched
    assert [r['new_label'] for r in rows] == names
    if matched:
        assert rows[0]['thumbnail_source'] == 'Shadow III (USA)'
        assert rows[2]['thumbnail_source'] is None
        assert rows[2]['artwork_query'] == 'New Homebrew'
        assert rows[2]['artwork_gallery_status'] == 'not_found'
        assert not rows[0]['identity']['release_verified']


def test_invalid_full_title_alias_rejected_at_data_boundary(tmp_path):
    from types import SimpleNamespace
    from chinese_title_match import resolve_chinese_titles

    (tmp_path / 'title_aliases.json').write_text('[{"system": "MD", "aliases": [123]}]', encoding='utf-8')
    row = {'system': 'MD', 'path': '/roms/旧译名.bin', 'match_source': 'playlist'}
    with pytest.raises(ValueError, match='完整标题别名'):
        resolve_chinese_titles([row], {'MD': SimpleNamespace(rom_name_cn_path=str(tmp_path))})


def test_declared_same_game_variants_are_recommended_without_claiming_rom_version(tmp_path, monkeypatch):
    system = 'Nintendo - Game Boy Color'
    source = tmp_path / 'names'
    source.mkdir()
    with (source / (system + '.csv')).open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Name EN', 'Name CN'])
        writer.writerows([['Monster II - Boy (Japan)', '怪兽仙境2 - 男孩版'],
                          ['Monster II - Girl (Japan)', '怪兽仙境2 - 女孩版']])
    (source / 'title_aliases.json').write_text(json.dumps([
        {'system': system, 'english_name': 'Monster II - Boy (Japan)',
         'english_names': ['Monster II - Girl (Japan)'],
         'chinese_name': '怪兽篇2', 'aliases': ['怪兽篇2']}]), encoding='utf-8')
    monkeypatch.setattr('single_artwork.catalog_names', lambda *args: ['Monster II - Boy (Japan)', 'Monster II - Girl (Japan)'])
    playlist = tmp_path / 'games.lpl'
    playlist.write_text(json.dumps({'items': [{'label': '怪兽篇2', 'path': '/roms/怪兽篇2.gbc'}]}), encoding='utf-8')
    row = analyze_playlist(str(playlist), system, str(source), verify_artwork=True)[0]
    assert not row['identity']['requires_review']
    assert not row['identity']['release_verified']
    assert row['new_label'] == '怪兽篇2'
    assert row['artwork_candidates'] == ['Monster II - Boy (Japan)', 'Monster II - Girl (Japan)']
    assert row['thumbnail_source'] in row['artwork_candidates']
