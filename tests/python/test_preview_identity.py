"""Identity evidence remains separate from display names, artwork and local UUIDs."""
import copy
import json

import pytest

from preview_identity import identity_state


@pytest.mark.parametrize('fields,state', [
    ({'match_source':'manual_override'}, 'confirmed_rule'),
    ({'match_source':'rom-name-cn','translation_match_source':'exact'}, 'exact_title'),
    ({'match_source':'rom-name-cn','translation_match_source':'curated_alias'}, 'exact_title'),
    ({'match_source':'libretro-dat'}, 'database_title'),
    ({'match_source':'libretro-dat','match_diagnostics':{'evidence_chain':[{'source':'playlist_crc32','value':'12345678'}]}}, 'database_title'),
    ({'match_source':'rom-name-cn','translation_match_source':'fuzzy_candidate'}, 'candidate'),
    ({'match_source':'libretro-dat','translation_match_source':'cross_system_candidate'}, 'candidate'),
    ({'thumbnail_source':'Game (Japan)','artwork_identity_status':'resolved'}, 'title_family'),
    ({'thumbnail_source':'Game (Japan)'}, 'candidate'),
    ({'artwork_identity_reason':'parent_title','artwork_identity_status':'resolved'}, 'candidate'),
    ({'artwork_identity_status':'ambiguous'}, 'candidate'),
    ({}, 'unresolved'),
    ({'match_source':'manual_override','match_diagnostics':{'conflicts':[{'reason':'conflict'}]}}, 'conflict'),
    ({'match_source':'libretro-dat','match_diagnostics':{'evidence_chain':[
        {'source':'playlist_crc32','value':'12345678','resolved_name':'Game (USA)'}]}}, 'checksum_match'),
])
def test_evidence_classification_is_read_only_and_never_claims_a_verified_release(fields, state):
    before = copy.deepcopy(fields)
    result = identity_state(fields)
    assert fields == before
    assert result['state'] == state
    assert result['requires_review'] == (state in {'candidate','unresolved','conflict'})
    assert result['release_verified'] is False


@pytest.mark.parametrize('remote', [False, True])
def test_browsing_and_repair_share_uuids_and_preserve_original_snapshots(tmp_path, monkeypatch, remote):
    from playlist_analysis import analyze_playlist
    from playlist_browser import read_playlist
    monkeypatch.setenv('RETROARCH_ASSISTANT_HOME', str(tmp_path/'home'))
    source = tmp_path/'names';source.mkdir()
    system = 'Nintendo - Nintendo Entertainment System'
    (source/'NES.csv').write_text('Name EN,Name CN\nGame,游戏\n', encoding='utf-8')
    playlist = tmp_path/'playlists'/'NES.lpl';playlist.parent.mkdir()
    item = {'label':'Game','path':'/roms/Game.nes','core_path':'custom.so','core_name':'My core',
            'db_name':'NES.lpl','custom':'keep'}
    playlist.write_text(json.dumps({'items':[item]}), encoding='utf-8')
    before = playlist.read_bytes()
    locator = 'mtp://handheld/00010001/RetroArch/playlists/NES.lpl' if remote else str(playlist)
    if remote:
        monkeypatch.setattr('playlist_browser.mtp.materialize', lambda path, temporary: str(playlist))
    row = analyze_playlist(str(playlist),system,str(source),source_playlist_path=locator)[0]
    browser = read_playlist(locator,system)['items'][0]
    for key in ('game_id','disc_id','content_id'):
        assert row[key] == browser[key]
    assert row['original_item_snapshot'] == item
    assert row['identity']['state'] == 'exact_title'
    assert row['identity']['requires_review'] is False
    assert playlist.read_bytes() == before
    assert not list(tmp_path.rglob('*.bak*'))


@pytest.mark.parametrize('names,images', [(True,False),(False,True)])
def test_batch_does_not_automatically_apply_candidates_with_valid_names_and_sources(tmp_path, monkeypatch, names, images):
    import batch_review
    source = tmp_path/'NES.lpl';source.write_text('{"items":[]}', encoding='utf-8')
    monkeypatch.setattr(batch_review, 'scan_retroarch_target', lambda _: {'playlists':[{'system':'NES','path':str(source)}]})
    monkeypatch.setattr(batch_review.playlist_service, 'analyze_playlist', lambda *args, **kwargs: [{
        'original_item_label':'Game','new_label':'错误名称','thumbnail_source':'Other Game (Japan)',
        'identity':{'state':'candidate','requires_review':True}}])
    before = source.read_bytes()
    review = batch_review.prepare_review(str(tmp_path),'','',None,{'write_names':names,'download_thumbnails':images},
                                        lambda *args:None,lambda:False)
    assert review['rows'][0]['review'] == 1
    assert review['rows'][0]['names'] == review['rows'][0]['artwork'] == 0
    assert review['plans'][0]['changes'] == []
    assert source.read_bytes() == before


@pytest.mark.parametrize('gallery', ['unavailable', 'not_found'])
def test_batch_gallery_problem_with_stale_source_is_reviewed_instead_of_downloaded(tmp_path, monkeypatch, gallery):
    import batch_review
    source = tmp_path/'NES.lpl';source.write_text('{"items":[]}', encoding='utf-8')
    monkeypatch.setattr(batch_review, 'scan_retroarch_target', lambda _: {'playlists':[{'system':'NES','path':str(source)}]})
    monkeypatch.setattr(batch_review.playlist_service, 'analyze_playlist', lambda *args, **kwargs: [{
        'original_item_label':'Game','new_label':'游戏','thumbnail_source':'Unverified source',
        'identity':{'state':'exact_title','requires_review':False},'artwork_gallery_status':gallery}])
    review = batch_review.prepare_review(str(tmp_path),'','',None,{'write_names':True,'download_thumbnails':True},
                                        lambda *args:None,lambda:False)
    assert review['rows'][0]['review'] == 1
    assert review['plans'][0]['changes'] == []
