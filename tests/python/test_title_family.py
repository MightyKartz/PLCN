import json

import pytest

from playlist_analysis import analyze_playlist
from title_family import family_key


@pytest.fixture
def ps1_names(tmp_path):
    source = tmp_path / 'names'
    source.mkdir()
    (source / 'Sony - PlayStation.csv').write_text(
        'Name EN,Name CN\nAlundra (Japan),阿兰朵拉\nAlundra (USA),阿兰朵拉\n'
        'Alundra 2 (Japan),阿兰朵拉2\n'
        'Biohazard 2 (Japan) (Disc 1) (Leon-hen),生化危机2\n'
        'Biohazard 2 (Japan) (Disc 2) (Claire-hen),生化危机2\n', encoding='utf-8')
    return source


def test_known_family_selects_artwork_and_keeps_packaging_markers(tmp_path, ps1_names, monkeypatch):
    from batch_review import prepare_review
    names = ['Alundra', 'Biohazard 2 (A) (CHS)', 'Biohazard 2 (B) (CHS)']
    playlist = tmp_path / 'PS1.lpl'
    items = [{'label': name, 'path': '/roms/' + name + '.cue', 'core_path': 'custom.so'} for name in names]
    playlist.write_text(json.dumps({'items': items}), encoding='utf-8')
    before = playlist.read_bytes()
    catalog = ['Alundra (Japan)', 'Alundra (USA)', 'Alundra 2 (Japan)',
               'Biohazard 2 (Japan) (Disc 1) (Leon-hen)', 'Biohazard 2 (Japan) (Disc 2) (Claire-hen)']
    monkeypatch.setattr('single_artwork.catalog_names', lambda *args: catalog)
    changes = analyze_playlist(str(playlist), 'Sony - PlayStation', str(ps1_names), verify_artwork=True)
    assert [c['new_label'] for c in changes] == ['阿兰朵拉', '生化危机2（A）', '生化危机2（B）']
    for c in changes:
        assert c['identity']['state'] == 'title_family'
        assert c['identity']['requires_review'] is False
        assert c['identity']['release_verified'] is False
        assert c['artwork_recommended'] is True
        assert c['thumbnail_source'] in catalog
    assert changes[0]['thumbnail_source'] == 'Alundra (Japan)'
    assert 'Alundra 2 (Japan)' not in changes[0]['artwork_candidates']
    monkeypatch.setattr('batch_review.scan_retroarch_target', lambda _: {'playlists': [{'system': 'Sony - PlayStation', 'path': str(playlist)}]})
    review = prepare_review(str(tmp_path), '', str(ps1_names), None,
                            {'write_names': True, 'download_thumbnails': True}, lambda *a: None, lambda: False)
    assert review['rows'][0]['review'] == 0
    assert len(review['plans'][0]['changes']) == 3
    assert playlist.read_bytes() == before
    renamed = [dict(item, label=change['new_label']) for item, change in zip(items, changes)]
    playlist.write_text(json.dumps({'items': renamed}), encoding='utf-8')
    again = analyze_playlist(str(playlist), 'Sony - PlayStation', str(ps1_names), verify_artwork=True)
    assert [c['new_label'] for c in again] == [c['new_label'] for c in changes]
    assert all(not c['identity']['requires_review'] for c in again)


@pytest.mark.parametrize('name', ['Alundra 2', 'Alundra - Special Edition', 'Alundra (Hack)', 'Alundra (HD)'])
def test_title_family_never_discards_sequels_or_unknown_edition_tags(name):
    assert family_key(name) != family_key('Alundra')


@pytest.mark.parametrize('marker', ['[Disc1of3]', '(Disc 1 of 3)', ' Disc1'])
def test_compact_multidisc_markers_keep_disc_identity(marker):
    from title_family import keep_disc_marker
    from gallery_names import release_candidates
    source = 'Game' + marker
    assert family_key(source) == family_key('Game')
    assert keep_disc_marker('游戏', source) == '游戏 (Disc 1)'
    assert release_candidates(source, ['Game (Japan) (Disc 1)', 'Game (Japan) (Disc 2)']) == ['Game (Japan) (Disc 1)']


@pytest.mark.parametrize('label,filename', [('Biohazard 2 (Disc 2)', 'Biohazard 2 (Disc 1)'),
                                            ('Biohazard 2 (A) (CHS)', 'Biohazard 2 (B) (CHS)')])
def test_exact_family_does_not_override_conflicting_disc_markers(tmp_path, ps1_names, label, filename):
    playlist = tmp_path / 'PS1.lpl'
    playlist.write_text(json.dumps({'items': [{'label': label, 'path': '/roms/' + filename + '.cue'}]}))
    row = analyze_playlist(str(playlist), 'Sony - PlayStation', str(ps1_names))[0]
    assert row['identity']['state'] == 'conflict'
    assert row['identity']['requires_review'] is True


def test_disc_constraints_and_failed_gallery_do_not_become_verified_releases(tmp_path, ps1_names, monkeypatch):
    playlist = tmp_path / 'PS1.lpl'
    playlist.write_text(json.dumps({'items': [{'label': 'Biohazard 2 (Disc 2)', 'path': '/roms/Biohazard 2 (Disc 2).cue'}]}))
    monkeypatch.setattr('single_artwork.catalog_names', lambda *a: [
        'Biohazard 2 (Japan) (Disc 1) (Leon-hen)', 'Biohazard 2 (Japan) (Disc 2) (Claire-hen)'])
    row = analyze_playlist(str(playlist), 'Sony - PlayStation', str(ps1_names), verify_artwork=True)[0]
    assert row['new_label'] == '生化危机2（第2盘）'
    assert row['artwork_candidates'] == ['Biohazard 2 (Japan) (Disc 2) (Claire-hen)']
    def failed(*args):
        raise RuntimeError('offline')
    monkeypatch.setattr('single_artwork.catalog_names', failed)
    row = analyze_playlist(str(playlist), 'Sony - PlayStation', str(ps1_names), verify_artwork=True)[0]
    assert row['artwork_gallery_status'] == 'unavailable'
    assert row['thumbnail_source'] is None
    assert row['identity']['release_verified'] is False
