import csv
import json

import pytest

from playlist_analysis import analyze_playlist


@pytest.mark.parametrize('system', [
    'Nintendo - Nintendo Entertainment System', 'Nintendo - Super Nintendo Entertainment System',
    'Nintendo - Game Boy Color', 'Nintendo - Game Boy Advance', 'Sony - PlayStation',
    'Sega - Mega Drive - Genesis', 'FBNeo - Arcade Games',
])
def test_candidates_use_default_on_every_system_and_keep_existing_label(tmp_path, monkeypatch, system):
    source = tmp_path / 'names'; source.mkdir()
    with (source / (system + '.csv')).open('w', newline='') as f:
        writer = csv.writer(f);writer.writerow(['Name EN', 'Name CN'])
        writer.writerows([['Frontier (Japan)', '边境任务'], ['Frontier (USA)', '边境任务']])
    monkeypatch.setattr('single_artwork.catalog_names', lambda *args: ['Frontier (Japan)', 'Frontier (USA)'])
    path = tmp_path / 'games.lpl'
    path.write_text(json.dumps({'items': [{'path': '/roms/边境使命.bin', 'label': '边境使命'}]}))
    before = path.read_bytes()
    row = analyze_playlist(str(path), system, str(source), verify_artwork=True)[0]
    assert row['identity']['state'] == 'recommended'
    assert not row['identity']['requires_review']
    assert not row['identity']['release_verified']
    assert row['new_label'] == '边境使命'
    assert row['thumbnail_source'] == 'Frontier (Japan)'
    assert path.read_bytes() == before


def test_default_does_not_override_conflicts_or_confirmed_rules():
    from default_recommendations import resolve
    rows = [{'path': '/game.bin', 'match_source': 'manual_override'},
            {'path': '/game.bin', 'match_source': 'playlist', 'match_diagnostics': {'conflicts': [{'reason': 'CRC mismatch'}]}}]
    before = json.dumps(rows)
    resolve(rows, {})
    assert json.dumps(rows) == before


@pytest.mark.parametrize('system', ['Sega - Saturn', 'DOS'])
def test_specialized_system_candidates_follow_the_same_default_policy(tmp_path, system):
    from types import SimpleNamespace
    from default_recommendations import resolve
    from preview_identity import identity_state
    records = [{'english_name': 'Frontier (Japan)', 'chinese_name': '边境任务'}]
    connection = SimpleNamespace(execute=lambda *args: SimpleNamespace(fetchall=lambda: records))
    db = SimpleNamespace(expand_system_mapping=lambda system: [system], get_connection=lambda: connection)
    row = {'system': system, 'path': '/roms/边境使命.bin', 'original_label': '边境使命',
           'original_item_label': '边境使命', 'new_label': '边境使命', 'match_source': 'playlist',
           'thumbnail_source': '边境使命', 'translation_match_source': 'fuzzy_candidate'}
    resolve([row], {system: SimpleNamespace(db=db)})
    assert row['thumbnail_source'] == 'Frontier (Japan)'
    assert row['new_label'] == '边境使命'
    assert identity_state(row)['state'] == 'recommended'
    assert not identity_state(row)['requires_review']
