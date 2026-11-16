import copy
import hashlib
import io
import json
from pathlib import Path
import struct
import zipfile

import pytest
import content_scan as scan
import core_catalog


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setenv('PLCN_HOME', str(tmp_path / 'home'))
    root = tmp_path / 'RetroArch'; (root / 'playlists').mkdir(parents=True)
    games = tmp_path / 'Roms'; games.mkdir()
    core = tmp_path / 'snes9x_libretro.dylib'; core.write_bytes(b'installed')
    config = scan.validate({'root':str(root),'directory':str(games),
        'system':'Nintendo - Super Nintendo Entertainment System', 'core_id':'snes9x',
        'core_path':str(core), 'extensions':'sfc smc zip', 'recursive':True})
    return root, games, config


def test_incremental_import_preserves_overrides_backups_and_refresh(library):
    root, games, config = library
    (games / 'old.sfc').write_bytes(b'old'); (games / 'new.sfc').write_bytes(b'new')
    (games / 'notes.txt').write_text('not a ROM', encoding='utf-8')
    target = root / 'playlists' / (config['system'] + '.lpl')
    old = {'version':'1.5','sort_mode':1,'items':[{'path':str(games/'old.sfc'),'label':'已修中文名',
        'core_path':'special.dylib','core_name':'Special','custom':'keep'}]}
    target.write_text(json.dumps(old,ensure_ascii=False), encoding='utf-8'); before = target.read_bytes()
    plan = scan.preview(config)
    assert [a['label'] for a in plan['added']] == ['new']
    assert plan['document']['items'][0] == old['items'][0]
    assert plan['document']['sort_mode'] == 1
    assert target.read_bytes() == before
    result = scan.apply(plan)
    assert Path(result['backup']).read_bytes() == before
    assert json.loads(target.read_text(encoding='utf-8'))['default_core_path'] == config['core_path']
    assert scan.profiles()[str(root)][0] == config
    again = scan.preview(config)
    assert again['added'] == [] and again['can_apply'] is False


def test_stale_plan_cannot_replace_changed_playlist(library):
    root, games, config = library
    (games / 'new.sfc').touch()
    plan = scan.preview(config)
    Path(plan['target']).write_text('{"items":[]}', encoding='utf-8')
    with pytest.raises(RuntimeError, match='列表已变化'): scan.apply(plan)
    assert Path(plan['target']).read_text(encoding='utf-8') == '{"items":[]}'


def test_arcade_scan_skips_bios_files_without_dat_filter(library):
    root, games, config = library
    config['system'] = 'FBNeo - Arcade Games'
    for name in ('neogeo.zip', 'pgm.zip', 'skns.zip', 'nmk004.zip', 'bioship.zip'):
        (games / name).write_bytes(b'ROM')
    plan = scan.preview(config)
    assert [item['label'] for item in plan['added']] == ['bioship']
    assert all((games / name).exists() for name in ('neogeo.zip', 'pgm.zip', 'skns.zip', 'nmk004.zip'))


def test_disc_entry_filtering_and_m3u_do_not_duplicate_tracks(library):
    root, games, config = library
    for name in ['Game (Disc 1).cue','Game (Disc 1).bin','Game (Disc 2).chd','other.cue','other.bin']:
        (games / name).touch()
    (games / 'Game.m3u').write_text('Game (Disc 1).cue\nGame (Disc 2).chd\n', encoding='utf-8')
    config['extensions'] = 'cue chd m3u'
    target = root / 'playlists' / (config['system']+'.lpl')
    retained = {'path':str(games/'Game (Disc 1).cue'),'label':'已有逐碟记录'}
    target.write_text(json.dumps({'items':[retained]}), encoding='utf-8')
    plan = scan.preview(config)
    assert {row['label'] for row in plan['added']} == {'Game','other'}
    assert plan['document']['items'][0] == retained


def test_dat_names_filter_bios_and_recursion(library):
    root, games, config = library
    sub=games/'sub';sub.mkdir()
    for name in ['good.zip','unknown.zip','bios.zip']: (sub/name).touch()
    dat=games/'arcade.dat'
    dat.write_text('<datafile><game name="good"><description>Game Name</description></game><game name="bios" isbios="yes"/></datafile>', encoding='utf-8')
    config.update(dat_path=str(dat),dat_filter=True)
    plan=scan.preview(config)
    assert [row['label'] for row in plan['added']] == ['Game Name']
    config['recursive']=False
    assert scan.preview(config)['added'] == []


def test_mtp_paths_are_android_paths_and_unavailable_storage_never_deletes(monkeypatch, tmp_path):
    monkeypatch.setenv('PLCN_HOME', str(tmp_path))
    root='mtp://device/00010001/RetroArch'
    config=scan.validate({'root':root,'directory':'mtp://device/00010001/Roms/SS',
        'android_directory':'/storage/CARD/Roms/SS','system':'Sega - Saturn','core_id':'mednafen_saturn',
        'core_path':'/data/user/0/com.retroarch/cores/mednafen_saturn_libretro_android.so','extensions':'cue chd'})
    monkeypatch.setattr(scan,'folders',lambda path:[{'name':'Game.cue','folder':False}])
    monkeypatch.setattr(scan,'read',lambda path:None)
    plan=scan.preview(config)
    assert plan['added'][0]['path'] == '/storage/CARD/Roms/SS/Game.cue'
    assert plan['document']['scan_content_dir'] == '/storage/CARD/Roms/SS'
    assert '未知' in plan['core_status']
    def unavailable(path): raise RuntimeError('设备读取失败')
    monkeypatch.setattr(scan,'folders',unavailable)
    with pytest.raises(RuntimeError,match='设备读取失败'): scan.preview(config)
    with pytest.raises(ValueError): scan.validate({**config,'android_directory':'/storage/CARD/../other'})
    with pytest.raises(ValueError): scan.validate({**config,'directory':'mtp://other/00010001/Roms'})


def core_archive(elf_class=2, machine=183):
    elf=bytearray(64);elf[:6]=b'\x7fELF'+bytes([elf_class,1]);struct.pack_into('<H',elf,18,machine)
    data=io.BytesIO()
    with zipfile.ZipFile(data,'w') as archive: archive.writestr('gambatte_libretro_android.so',elf)
    return data.getvalue(),bytes(elf)


def test_official_core_download_checks_abi_records_source_and_never_claims_installed(tmp_path,monkeypatch):
    monkeypatch.setenv('PLCN_HOME',str(tmp_path))
    archive,binary=core_archive()
    urls=[]
    def get(url):
        urls.append(url)
        return archive if url.endswith('.zip') else b'supported_extensions = "gb|gbc"\n'
    monkeypatch.setattr(core_catalog,'official_get',get)
    result=core_catalog.download('gambatte','arm64-v8a')
    assert urls[0].startswith(core_catalog.BASE+'arm64-v8a/')
    assert urls[1].startswith('https://raw.githubusercontent.com/libretro/libretro-core-info/')
    assert result['status']=='downloaded' and result['sha256']==hashlib.sha256(binary).hexdigest()
    assert result['extensions']=='gb gbc'
    assert '尚未安装' in result['message']
    bad,_=core_archive(1,40)
    monkeypatch.setattr(core_catalog,'official_get',lambda url:bad)
    with pytest.raises(ValueError,match='架构'): core_catalog.download('gambatte','arm64-v8a')
    with pytest.raises(ValueError): core_catalog.download('../../unknown','arm64-v8a')


def test_scan_validation_requires_core_format_and_dat(library):
    root,games,config=library
    for change in [{'core_id':'mgba'}, {'extensions':'sfc,smc'}, {'dat_filter':True}, {'core_path':'missing.dylib'}]:
        with pytest.raises(ValueError):scan.validate({**config,**change})


def test_existing_android_mapping_and_core_are_recovered_without_guessing(monkeypatch):
    old={'items':[{'path':'/storage/ABCD/Roms/SS/Chinese/Game.cue',
                   'core_path':'/data/user/0/com.retroarch/cores/mednafen_saturn_libretro_android.so'}]}
    monkeypatch.setattr(scan,'read',lambda path:json.dumps(old).encode())
    result=scan.hints('mtp://device/00010001/RetroArch','Sega - Saturn','mtp://device/00010001/Roms/SS')
    assert result['android_directory']=='/storage/ABCD/Roms/SS'
    assert result['core_path']==old['items'][0]['core_path']
    old['items'].append({'path':'/storage/OTHER/Roms/SS/Game2.cue'})
    assert scan.hints('mtp://device/00010001/RetroArch','Sega - Saturn','mtp://device/00010001/Roms/SS')['android_directory']==''


def test_server_applies_only_its_stored_scan_plan_and_rejects_replay(library,monkeypatch):
    import api_content
    from job_manager import JobManager
    from types import SimpleNamespace
    root,games,config=library
    (games/'New.sfc').touch()
    plan=scan.preview(config)
    jobs=JobManager();ident=jobs.create_job();jobs.complete_job(ident,{'can_apply':True})
    jobs.contexts[ident]={'content_plan':plan}
    context=SimpleNamespace(job_manager=jobs)
    output=[]
    monkeypatch.setattr(api_content,'reply',lambda handler,data:output.append(data))
    def immediate(jobs,title,work):
        ident=jobs.create_job();jobs.complete_job(ident,work(ident));return ident
    monkeypatch.setattr(api_content,'background',immediate)
    api_content.apply(None,context,{'preview_job_id':ident,'document':{'items':[]},'target':'untrusted.lpl'})
    assert json.loads(Path(plan['target']).read_text(encoding='utf-8'))['items'][0]['label']=='New'
    with pytest.raises(ValueError,match='已经应用'):api_content.apply(None,context,{'preview_job_id':ident})


def test_custom_playlist_target_preserves_name_and_rejects_path_escape(library):
    root,games,config=library
    config=scan.validate({**config,'playlist_name':'我的 SNES.lpl'})
    (games/'New.sfc').touch()
    plan=scan.preview(config)
    assert Path(plan['target']).name=='我的 SNES.lpl'
    for name in ['../outside.lpl','/outside.lpl','wrong.json']:
        with pytest.raises(ValueError):scan.validate({**config,'playlist_name':name})


def test_card_games_can_update_internal_playlist_without_changing_target(monkeypatch,tmp_path):
    monkeypatch.setenv('PLCN_HOME',str(tmp_path))
    root='mtp://device/00010001/RetroArch'
    config=scan.validate({'root':root,'directory':'mtp://device/00020001/Roms/SS',
        'android_directory':'/storage/CARD/Roms/SS','system':'Sega - Saturn','core_id':'mednafen_saturn',
        'core_path':'/data/user/0/com.retroarch/cores/mednafen_saturn_libretro_android.so','extensions':'cue'})
    monkeypatch.setattr(scan,'folders',lambda path:[{'name':'Card Game.cue','folder':False}])
    monkeypatch.setattr(scan,'read',lambda path:None)
    plan=scan.preview(config)
    assert '/00010001/RetroArch/playlists/' in plan['target']
    assert plan['added'][0]['path']=='/storage/CARD/Roms/SS/Card Game.cue'
    monkeypatch.setattr(scan,'read',lambda path:json.dumps({'items':[{'path':'/storage/emulated/0/Roms/SS/Other.cue'}]}).encode())
    assert scan.hints(root,'Sega - Saturn',config['directory'])['android_directory']==''
    with pytest.raises(ValueError):scan.validate({**config,'directory':'mtp://another/00020001/Roms/SS'})


def test_core_status_distinguishes_local_file_from_unverified_remote_install(tmp_path, monkeypatch):
    core = tmp_path / 'core.so'
    core.write_bytes(b'file presence is not a core-load verification')
    assert scan.core_status(str(tmp_path), str(core))['state'] == 'available'
    assert '尚未验证' in scan.core_status(str(tmp_path), str(core))['detail']
    assert scan.core_status(str(tmp_path), str(tmp_path / 'missing.so'))['state'] == 'missing'
    assert scan.core_status(str(tmp_path), '')['state'] == 'unconfigured'
    monkeypatch.setattr(scan.mtp, 'read', lambda *a: pytest.fail('Core status must not open USB'))
    assert scan.core_status('mtp://device/00010001/RetroArch', str(core))['state'] == 'unknown'
    assert scan.core_status('mtp://device/00010001/RetroArch', '')['state'] == 'unconfigured'
    for root, path in [(None, ''), ('adb://device', ''), ('/tmp', None)]:
        with pytest.raises(ValueError):
            scan.core_status(root, path)
