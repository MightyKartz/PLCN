"""Optical inspections read declarations and metadata, never game image contents."""
import json
from pathlib import Path

import pytest
import disc_inspection as discs

SYSTEM = 'Sega - Saturn'


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setenv('RETROARCH_ASSISTANT_HOME',str(tmp_path/'home'))
    lists=tmp_path/'RetroArch'/'playlists';lists.mkdir(parents=True)
    roms=tmp_path/'Roms'/'SS';roms.mkdir(parents=True)
    playlist=lists/'SS.lpl'
    def make(names, other=None):
        items=[]
        for name in names:
            file=roms/name
            if not file.exists(): file.write_bytes(b'image-content-must-not-be-read')
            items.append({'path':str(file),'label':name.split('.')[0],'core_path':'custom_core.so','custom':'keep'})
        playlist.write_text(json.dumps({'items':items}),encoding='utf-8')
        if other is not None:
            (lists/'Other.lpl').write_text(json.dumps({'items':[{'path':str(roms/name),'label':name} for name in other]}),encoding='utf-8')
        return playlist,roms
    return make


def codes(group):
    return {issue['code'] for issue in group['issues']}


def test_short_alias_three_discs_missing_duplicate_and_metadata_read_boundary(library, monkeypatch):
    playlist,roms=library(['GulliverBoy Disc1.chd','Kuusou Kagaku Sekai Gulliver Boy (Disc 2).chd',
        'Three (Disc 1 of 3).chd','Three (Disc 3 of 3).chd','Duplicate (Disc 1).chd','Duplicate (Disc 1).iso'])
    before={file:file.read_bytes() for file in [playlist,*roms.iterdir()]}
    original=discs.read
    monkeypatch.setattr(discs,'read',lambda path:original(path) if str(path).endswith('.lpl') else pytest.fail('ROM bytes were read'))
    result=discs.inspect_discs(str(playlist),SYSTEM)
    assert len(result['groups']) == 3
    gulliver=next(group for group in result['groups'] if 'Gulliver' in group['label'])
    assert len(gulliver['discs']) == 2 and not gulliver['issues']
    assert gulliver['status'] == 'candidate'
    assert gulliver['label'] == 'Kuusou Kagaku Sekai Gulliver Boy'
    assert 'missing_disc' in codes(next(group for group in result['groups'] if 'Three' in group['label']))
    assert 'duplicate_disc' in codes(next(group for group in result['groups'] if 'Duplicate' in group['label']))
    assert {file:file.read_bytes() for file in before} == before
    assert not list(playlist.parent.glob('*.bak*'))


def test_existing_m3u_order_cue_tracks_shared_playlists_and_sizes(library):
    playlist,roms=library(['Game.m3u','Game (Disc 1).cue','Game (Disc 1).bin','Game (Disc 2).chd'],
                          other=['Game (Disc 1).bin','Game (Disc 2).chd'])
    (roms/'Game.m3u').write_text('#EXTM3U\nGame (Disc 2).chd\nGame (Disc 1).cue\n',encoding='utf-8')
    (roms/'Game (Disc 1).cue').write_text('FILE "Game (Disc 1).bin" BINARY\n TRACK 01 MODE1/2352\n',encoding='utf-8')
    result=discs.inspect_discs(str(playlist),SYSTEM)
    assert len(result['groups']) == 1
    group=result['groups'][0];files={file['id']:file for file in result['files']}
    assert [files[key]['disc']['number'] for key in group['discs']] == [2,1]
    assert len(group['files']) == 4 and result['summary']['discs'] == 2
    assert set(group['entry_indices']) == {0,1,2,3}
    track=next(file for file in result['files'] if file['format']=='bin')
    assert len(track['playlist_references']) == 2 and track['referenced_by']
    assert 'shared_playlist' in codes(group)
    assert all(file['status']=='present' and file['size'] is not None for file in result['files'])
    second=discs.inspect_discs(str(playlist),SYSTEM)
    assert second['groups'][0]['id'] == group['id']


def test_versions_extras_sequels_and_parent_folders_stay_separate(library):
    playlist,roms=library(['Game (Japan) (Disc 1).chd','Game (USA) (Disc 2).chd',
        'Game (Japan) (Rev A) (Disc 2).chd','Game (Japan) [T-Chi v1] (Disc 2).chd',
        'Game Bonus (Disc 2).chd','Game 2 (Disc 1).chd'])
    doc=json.loads(playlist.read_text());other=roms/'other';other.mkdir()
    (other/'Game (Japan) (Disc 2).chd').touch()
    doc['items'].append({'path':str(other/'Game (Japan) (Disc 2).chd'),'label':'相同中文名'})
    for item in doc['items']: item['label']='相同中文名'
    playlist.write_text(json.dumps(doc),encoding='utf-8')
    result=discs.inspect_discs(str(playlist),SYSTEM)
    assert len(result['groups']) == 7
    assert sum('version_conflict' in codes(group) for group in result['groups']) == 4
    for group in result['groups']:
        for issue in group['issues']:
            if issue['code']=='version_conflict': assert len(issue['related_paths']) == 4
    assert sum('extra_disc' in codes(group) for group in result['groups']) == 1
    assert all(len(group['discs'])==1 for group in result['groups'])


def test_missing_cycle_bad_references_and_incomplete_coverage_are_visible(library):
    playlist,roms=library(['Game.m3u','Other.m3u'])
    (roms/'Game.m3u').write_text('Other.m3u\nMissing (Disc 2).chd\nhttps://example.com/Game.chd\n',encoding='utf-8')
    (roms/'Other.m3u').write_text('Game.m3u\n',encoding='utf-8')
    (playlist.parent/'Broken.lpl').write_text('{',encoding='utf-8')
    result=discs.inspect_discs(str(playlist),SYSTEM)
    assert result['coverage']['playlists'] == 1 and len(result['coverage']['errors'])==1
    assert {'reference_cycle','missing','invalid_reference','nested_m3u'} <= codes(result['groups'][0])


@pytest.mark.parametrize('title,number,total', [('Game (Disc 1)',1,None),('Game Disc1',1,None),
    ('Game_Disc 2',2,None),('Game [CD 3 of 3]',3,3),('Game (Disc 0)',None,None),
    ('Game (Disc 9999999999)',None,None),('Game Disc1 Disc2',None,None)])
def test_disc_markers(title,number,total):
    evidence=discs.disc_evidence(title+'.chd',SYSTEM)
    assert evidence['number']==number and evidence['total']==total


def test_cue_track_entry_order_does_not_create_an_extra_game(library):
    playlist,roms=library(['Plain.bin','Plain.cue'])
    (roms/'Plain.cue').write_text('FILE Plain.bin BINARY\n',encoding='utf-8')
    result=discs.inspect_discs(str(playlist),SYSTEM)
    assert result['summary']=={'groups':1,'discs':1,'files':2,'entries':2,'candidates':0,'attention':0}


def test_unmapped_mtp_is_not_missing_and_does_not_open_usb(monkeypatch,tmp_path):
    monkeypatch.setenv('RETROARCH_ASSISTANT_HOME',str(tmp_path))
    playlist='mtp://device/00010001/RetroArch/playlists/SS.lpl'
    monkeypatch.setattr(discs,'folders',lambda _: [{'name':'SS.lpl','folder':False}])
    monkeypatch.setattr(discs,'read',lambda _:json.dumps({'items':[{'path':'/storage/CARD/Roms/Game (Disc 1).chd'}]}).encode())
    monkeypatch.setattr(discs.mtp,'listing',lambda _:pytest.fail('Unmapped Android paths must not open USB'))
    result=discs.inspect_discs(playlist,SYSTEM)
    assert result['files'][0]['status']=='unmapped'
    assert 'unmapped' in codes(result['groups'][0]) and 'missing' not in codes(result['groups'][0])


def test_mtp_saved_mapping_handles_other_storage_and_caches_directory_reads(monkeypatch,tmp_path):
    monkeypatch.setenv('RETROARCH_ASSISTANT_HOME',str(tmp_path))
    playlist='mtp://device/00010001/RetroArch/playlists/SS.lpl'
    root=playlist.rsplit('/',2)[0]
    monkeypatch.setattr(discs,'profiles',lambda:{root:[{'android_directory':'/storage/CARD/Roms/SS','directory':'mtp://device/00020001/Roms/SS'}]})
    monkeypatch.setattr(discs,'folders',lambda _: [{'name':'SS.lpl','folder':False}])
    names=['游戏 Disc1.chd','游戏 Disc2.chd'];calls=[]
    monkeypatch.setattr(discs,'read',lambda _:json.dumps({'items':[{'path':'/storage/CARD/Roms/SS/'+name} for name in names]}).encode())
    def listing(path):
        calls.append(path)
        return [{'name':name,'folder':False,'size':123} for name in names]
    monkeypatch.setattr(discs.mtp,'listing',listing)
    result=discs.inspect_discs(playlist,SYSTEM)
    assert len(calls)==1 and calls[0]=='mtp://device/00020001/Roms/SS'
    assert all(file['status']=='present' for file in result['files'])
    assert len(result['groups'])==1 and len(result['groups'][0]['discs'])==2


def test_descriptor_errors_unknown_totals_and_unknown_formats(library):
    playlist,roms=library(['Bad.cue','Bad.m3u','Plain (Disc 1).ccd'])
    (roms/'Bad.cue').write_text('FILE "unterminated BINARY',encoding='utf-8')
    (roms/'Bad.m3u').write_text('"Bad.cue"\nBad.cue\nBad.cue\n',encoding='utf-8')
    result=discs.inspect_discs(str(playlist),SYSTEM)
    all_codes={code for group in result['groups'] for code in codes(group)}
    assert {'invalid_reference','duplicate_reference','descriptor_not_inspected'} <= all_codes
    assert all(not group['total_known'] for group in result['groups'])


def test_non_optical_lists_are_not_grouped(library):
    playlist,_=library(['Cart.sfc'])
    with pytest.raises(ValueError,match='Saturn'):
        discs.inspect_discs(str(playlist),'Nintendo - Super Nintendo Entertainment System')


def test_per_disc_artwork_sources_and_cores_are_preserved_without_title_matching(library,monkeypatch):
    playlist,_=library(['Game Disc1.chd','Game Disc2.chd'])
    original=playlist.read_bytes()
    monkeypatch.setattr(discs,'remembered',lambda context:{'sources':{'Named_Boxarts':context['rom_path']+' saved cover'}})
    result=discs.inspect_discs(str(playlist),SYSTEM)
    records=result['entries']
    assert records[0]['artwork_sources'] != records[1]['artwork_sources']
    assert all(record['core_path']=='custom_core.so' for record in records)
    assert playlist.read_bytes()==original


def test_large_metadata_is_reported_without_reading_it(library,monkeypatch):
    playlist,roms=library(['Large.m3u'])
    (roms/'Large.m3u').write_bytes(b'x'*(discs.METADATA_LIMIT+1))
    original=discs.read
    monkeypatch.setattr(discs,'read',lambda path:original(path) if str(path).endswith('.lpl') else pytest.fail('Oversized metadata read'))
    result=discs.inspect_discs(str(playlist),SYSTEM)
    assert 'metadata_too_large' in codes(result['groups'][0])


def test_same_device_mtp_uri_is_required_even_when_declared_in_playlist(monkeypatch,tmp_path):
    monkeypatch.setenv('RETROARCH_ASSISTANT_HOME',str(tmp_path))
    playlist='mtp://device/00010001/RetroArch/playlists/SS.lpl'
    monkeypatch.setattr(discs,'folders',lambda _: [{'name':'SS.lpl','folder':False}])
    monkeypatch.setattr(discs,'read',lambda _:json.dumps({'items':[{'path':'mtp://other/00020001/Game.chd'}]}).encode())
    monkeypatch.setattr(discs.mtp,'listing',lambda _:pytest.fail('Must not open a different device'))
    result=discs.inspect_discs(playlist,SYSTEM)
    assert result['files'][0]['status']=='unmapped'


def test_archive_members_are_unknown_not_missing_and_images_are_not_unpacked(library,monkeypatch):
    playlist,roms=library(['Archive.zip'])
    playlist.write_text(json.dumps({'items':[{'path':str(roms/'Archive.zip')+'#Game Disc1.chd'}]}),encoding='utf-8')
    original=discs.read
    monkeypatch.setattr(discs,'read',lambda path:original(path) if str(path).endswith('.lpl') else pytest.fail('Archive must not be read'))
    result=discs.inspect_discs(str(playlist),SYSTEM)
    assert result['files'][0]['status']=='unchecked'
    assert 'missing' not in codes(result['groups'][0])


def test_mtp_path_aliases_keep_each_original_identity_binding(monkeypatch,tmp_path):
    monkeypatch.setenv('RETROARCH_ASSISTANT_HOME',str(tmp_path))
    playlist='mtp://device/00010001/RetroArch/playlists/SS.lpl';root=playlist.rsplit('/',2)[0]
    monkeypatch.setattr(discs,'profiles',lambda:{root:[{'android_directory':prefix,'directory':'mtp://device/00020001/Roms'}
        for prefix in ['/sdcard/Roms','/storage/emulated/0/Roms']]})
    monkeypatch.setattr(discs,'folders',lambda _: [{'name':'SS.lpl','folder':False}])
    monkeypatch.setattr(discs,'read',lambda _:json.dumps({'items':[{'path':prefix+'/Game Disc1.chd'}
        for prefix in ['/sdcard/Roms','/storage/emulated/0/Roms']]}).encode())
    monkeypatch.setattr(discs.mtp,'listing',lambda _: [{'name':'Game Disc1.chd','folder':False,'size':123}])
    result=discs.inspect_discs(playlist,SYSTEM)
    assert len(result['files'])==1
    assert result['entries'][0]['content_id'] != result['entries'][1]['content_id']
    assert set(result['files'][0]['content_ids']) == {entry['content_id'] for entry in result['entries']}
    assert result['files'][0]['content_id'] is None


def test_nested_m3u_order_and_relative_cue_references(library):
    playlist,roms=library(['Game.m3u','Game (Disc 1).cue','Game (Disc 1).bin','Game (Disc 2).chd','Game (Disc 3).chd'])
    nested=roms/'nested';nested.mkdir()
    (roms/'Game.m3u').write_text('nested/first.m3u\nGame (Disc 3).chd\n',encoding='utf-8')
    (nested/'first.m3u').write_text('../Game (Disc 1).cue\n../Game (Disc 2).chd\n',encoding='utf-8')
    (roms/'Game (Disc 1).cue').write_text('FILE "Game (Disc 1).bin" BINARY\n',encoding='utf-8')
    result=discs.inspect_discs(str(playlist),SYSTEM)
    group=result['groups'][0];files={file['id']:file for file in result['files']}
    assert [files[key]['disc']['number'] for key in group['discs']] == [1,2,3]
    assert 'nested_m3u' in codes(group)
    assert all(file['status']=='present' for file in result['files'])


def test_encoded_mtp_filenames_have_the_same_disc_evidence_as_android_paths():
    uri='mtp://device/00020001/Roms/Game%20%28Japan%29%20Disc2.chd'
    assert discs.disc_evidence(uri,SYSTEM) == discs.disc_evidence('/storage/CARD/Roms/Game (Japan) Disc2.chd',SYSTEM)


def test_relative_reference_uses_windows_descriptor_parent():
    from disc_inspection import reference_path

    assert reference_path(r'C:\Games\Disc.cue', 'Track.bin') == 'C:/Games/Track.bin'
