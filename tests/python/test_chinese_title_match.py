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
    with (source / (system + '.csv')).open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Name EN', 'Name CN'])
        writer.writerows(names)
    monkeypatch.setattr('single_artwork.catalog_names', lambda *args: [n[0] for n in names])
    playlist = tmp_path / 'games.lpl'
    playlist.write_text(json.dumps({'items': [{'label': '边境任务', 'path': '/roms/边境任务.sfc'}]}))
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
    with (source / (system + '.csv')).open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Name EN', 'Name CN'])
        writer.writerows(names)
    (source / 'name_alias(Chinese).json').write_text(json.dumps({
        'series': {'default': '传说系列', 'alias': ['传说物语']}}))
    monkeypatch.setattr('single_artwork.catalog_names', lambda *args: [n[0] for n in names])
    queries = ['传说物语 三角力量', '钢铁战记Returns', '第4次机器人大战',
               '宇宙旅', '编年史3', '钢铁战记 (Unknown Hack)']
    playlist = tmp_path / 'games.lpl'
    playlist.write_text(json.dumps({'items': [{'label': q, 'path': '/roms/' + q + '.sfc'} for q in queries]}))
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
