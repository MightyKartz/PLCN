import csv
import json

from playlist_analysis import analyze_playlist


def preview(tmp_path, monkeypatch, names, entries):
    source = tmp_path / 'names'
    source.mkdir()
    with (source / 'Sony - PlayStation.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Name EN', 'Name CN'])
        writer.writerows(names)
    monkeypatch.setattr('single_artwork.catalog_names', lambda *args: [n[0] for n in names])
    path = tmp_path / 'PS1.lpl'
    path.write_text(json.dumps({'items': [{'label': name, 'path': '/roms/' + folder + '/' + name + '.cue'}
                                        for name, folder in entries]}))
    before = path.read_bytes()
    rows = analyze_playlist(str(path), 'Sony - PlayStation', str(source), verify_artwork=True)
    assert path.read_bytes() == before
    return rows


def test_spelling_and_patch_metadata_use_one_general_ranking_rule(tmp_path, monkeypatch):
    rows = preview(tmp_path, monkeypatch, [
        ('Star Voyager 4 (Japan)', '星际旅行4'), ('Star Voyager 5 (Japan)', '星际旅行5'),
        ('Battle Chronicle Alpha (Japan)', '战斗编年史α'),
        ('Battle Chronicle Alpha (USA)', '战斗编年史α'),
        ('Battle Chronicle Alpha Gaiden (Japan)', '战斗编年史α外传')],
        [('Star Voyagr 4 (J)', '星际旅行4'), ('Battle Chronicle Alpha (CHS) (v1.1)', '战斗编年史α')])
    assert [r['new_label'] for r in rows] == ['星际旅行4', '战斗编年史α']
    for row in rows:
        assert row['automatic_name_match'] is True
        assert row['identity']['requires_review'] is False
        assert row['artwork_recommended'] is True
        assert row['identity']['release_verified'] is False
    playlist = tmp_path / 'PS1.lpl'
    playlist.write_text(json.dumps({'items': [dict(r['original_item_snapshot'], label=r['new_label']) for r in rows]}))
    again = analyze_playlist(str(playlist), 'Sony - PlayStation', str(tmp_path / 'names'), verify_artwork=True)
    assert [r['new_label'] for r in again] == [r['new_label'] for r in rows]
    assert all(not r['identity']['requires_review'] for r in again)


def test_short_alias_needs_folder_and_matching_sequel_number(tmp_path, monkeypatch):
    rows = preview(tmp_path, monkeypatch, [('Kingdom II (Japan)', '王国2'), ('Kingdom V (Japan)', '王国5')],
                   [('King2', '王国2 - 完整版'), ('King3', '王国2 - 完整版')])
    assert rows[0]['new_label'] == '王国2'
    assert rows[0]['identity']['requires_review'] is False
    assert rows[1]['identity']['requires_review'] is True


def test_close_runners_up_and_unknown_hacks_still_require_review(tmp_path, monkeypatch):
    rows = preview(tmp_path, monkeypatch, [('Star Voyager (Japan)', '星际旅行'), ('Star Voyagers (Japan)', '星际旅人')],
                   [('Star Voyagr', '合集'), ('Star Voyager (Unknown Hack)', '星际旅行')])
    assert all(not r.get('automatic_name_match') for r in rows)
    assert all(r['identity']['requires_review'] for r in rows)


def test_catalog_embedded_english_aliases_are_reused_without_game_overrides(tmp_path, monkeypatch):
    rows = preview(tmp_path, monkeypatch, [
        ('Battle Chronicle - Collection (Japan) (Disc 1) (Battle Stories Complete Box)', '战斗编年史合集')],
        [('Battle Stories Complete Box', '合集')])
    assert rows[0]['automatic_name_match'] is True
    assert rows[0]['new_label'] == '战斗编年史合集'
    assert rows[0]['identity']['requires_review'] is False
