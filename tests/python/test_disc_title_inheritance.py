import json
import pytest

from manual_overrides import save_overrides
from playlist_analysis import analyze_playlist


@pytest.mark.parametrize('manual', [False, True])
def test_confirmed_title_is_reused_only_for_same_directory_release_and_disc_family(tmp_path, monkeypatch, manual):
    system = 'Sony - PlayStation'
    source = tmp_path / 'names'; source.mkdir()
    (source / (system + '.csv')).write_text('Name EN,Name CN\n' + ('Unrelated,其他游戏\n' if manual else 'Game (Japan) (Disc 1),已确认游戏\n'), encoding='utf-8')
    names = ['Game (Japan) (Disc 1)', 'Game (Japan) (Disc 2)', 'Game II (Japan) (Disc 2)',
             'Game (USA) (Disc 2)', 'Game (Japan) (Rev 1) (Disc 2)', 'Game (Japan) (Disc 3)']
    items = [{'path': '/roms/set/' + name + '.cue', 'label': name, 'core_path': 'custom.so'} for name in names]
    items.append({'path': '/roms/other/Game (Japan) (Disc 2).cue', 'label': 'Game (Japan) (Disc 2)'})
    playlist = tmp_path / 'games.lpl';playlist.write_text(json.dumps({'items': items}))
    rules = tmp_path / 'rules.json'
    save_overrides(rules, [{'system': system, 'rom_path': items[0]['path'], 'rom_filename': names[0] + '.cue',
                           'new_label': '已确认游戏', 'thumbnail_source': names[0]}])
    monkeypatch.setattr('single_artwork.catalog_names', lambda *args: names)
    before = playlist.read_bytes()
    rows = analyze_playlist(str(playlist), system, str(source), manual_overrides_path=str(rules) if manual else None, verify_artwork=True)
    assert playlist.read_bytes() == before
    assert rows[1]['new_label'] == '已确认游戏（第2盘）'
    assert rows[5]['new_label'] == '已确认游戏（第3盘）'
    assert rows[1]['identity']['requires_review'] is False
    assert rows[1]['identity']['release_verified'] is False
    assert rows[1]['original_item_snapshot']['core_path'] == 'custom.so'
    assert all(rows[i]['match_source'] != 'confirmed_sibling_title' for i in [2, 3, 4, 6])
    playlist.write_text(json.dumps({'items': [dict(item, label=r['new_label']) for item, r in zip(items, rows)]}))
    again = analyze_playlist(str(playlist), system, str(source), manual_overrides_path=str(rules) if manual else None, verify_artwork=True)
    assert again[1]['new_label'] == rows[1]['new_label']
    assert again[1]['identity']['requires_review'] is False


def test_refreshed_remote_preview_checks_all_three_image_types(tmp_path, monkeypatch):
    import mtp_runtime as mtp
    system = 'Sony - PlayStation'
    source = tmp_path / 'names';source.mkdir()
    (source / (system + '.csv')).write_text('Name EN,Name CN\nGame (Japan),游戏\n', encoding='utf-8')
    playlist = tmp_path / 'games.lpl'
    playlist.write_text(json.dumps({'items': [{'label': '游戏', 'path': '/roms/Game (Japan).cue'}]}))
    monkeypatch.setattr(mtp, 'listing', lambda path: [] if 'Named_Titles' in path else [{'name': '游戏.png', 'folder': False}])
    monkeypatch.setattr('single_artwork.catalog_names', lambda *args: ['Game (Japan)'])
    row = analyze_playlist(str(playlist), system, str(source), 'mtp://device/00010001/RetroArch/thumbnails', verify_artwork=True)[0]
    assert row['identity']['requires_review'] is False
    assert row['artwork']['Named_Boxarts']['status'] == row['artwork']['Named_Snaps']['status'] == 'exists'
    assert row['artwork']['Named_Titles']['status'] == 'missing'


def test_resolved_checksum_is_not_replaced_by_another_discs_title():
    import copy
    from disc_title_inheritance import inherit_confirmed_titles
    source = {'system': 'PS1', 'path': '/roms/Game (Japan) (Disc 1).cue', 'new_label': '游戏',
              'match_source': 'manual_override', 'thumbnail_source': 'Game (Japan) (Disc 1)', 'proposal_id': 'source'}
    target = {'system': 'PS1', 'path': '/roms/Game (Japan) (Disc 2).cue', 'new_label': '游戏',
              'original_item_label': 'Game (Japan) (Disc 2)', 'match_source': 'rom-name-cn', 'translation_match_source': 'exact_alias',
              'thumbnail_source': 'Game (Japan) (Disc 1)', 'match_diagnostics': {'evidence_chain': [
                  {'source': 'playlist_crc32', 'resolved_name': 'Game (Japan) (Disc 1)'}]}}
    before = copy.deepcopy(target)
    inherit_confirmed_titles([source, target])
    assert target == before
