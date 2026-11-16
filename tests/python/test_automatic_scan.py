import json
from pathlib import Path
import pytest
from PIL import Image
import automatic_scan as auto
import workbench_library


def test_multi_system_incremental_import_preserves_settings_and_skips_support_files(tmp_path):
    root=tmp_path/'RetroArch';root.mkdir();playlists=root/'playlists';playlists.mkdir()
    games=tmp_path/'Roms'
    for folder, names in [('NES',['old.nes','new.nes']),('GBA',['new.gba']),('FBNEO',['neogeo.zip','bioship.zip']),('Other',['unknown.bin'])]:
        directory=games/folder;directory.mkdir(parents=True)
        for name in names:(directory/name).write_bytes(b'test content')
    target=playlists/'NES.lpl'
    old={'path':str(games/'NES/old.nes'),'label':'手工名称','core_path':'custom.so','custom':'preserved','db_name':'Nintendo - Nintendo Entertainment System.lpl'}
    document={'items':[old],'default_core_path':'installed.so','default_core_name':'Custom core','sort_mode':1}
    target.write_text(json.dumps(document), encoding='utf-8');before=target.read_bytes()
    root_value,sources=auto.validate({'root':str(root),'sources':[str(tmp_path)]})
    plan=auto.preview(root_value,sources)
    public=auto.public_result(plan)
    assert {r['system']:r['added'] for r in public['rows']} == {'Nintendo - Nintendo Entertainment System':1,'Nintendo - Game Boy Advance':1,'FBNeo - Arcade Games':1}
    assert len(public['unclassified'])==1
    assert target.read_bytes()==before
    result=auto.apply(plan,list(plan['plans']))
    assert result['added']==3
    updated=json.loads(target.read_text(encoding='utf-8'))
    assert updated['items'][0]==old
    assert updated['default_core_path']=='installed.so' and updated['default_core_name']=='Custom core'
    assert updated['sort_mode']==1
    assert all(not p['added'] for p in auto.preview(str(root),sources)['plans'].values())
    assert (games/'FBNEO/neogeo.zip').read_bytes()==b'test content'


def test_new_library_can_be_created_after_review_and_stale_lists_are_not_overwritten(tmp_path):
    root=tmp_path/'RetroArch';root.mkdir();games=tmp_path/'Roms/GBC';games.mkdir(parents=True);(games/'new.gbc').touch()
    plan=auto.preview(str(root),[str(tmp_path)])
    assert not (root/'playlists').exists()
    result=auto.apply(plan,list(plan['plans']))
    target=Path(result['playlists'][0]['playlist_path']);doc=json.loads(target.read_text(encoding='utf-8'))
    assert doc['default_core_path']=='DETECT' and doc['default_core_name']=='DETECT'
    (games/'second.gbc').touch();again=auto.preview(str(root),[str(tmp_path)])
    target.write_text('{"items":[]}', encoding='utf-8')
    with pytest.raises(RuntimeError,match='列表已变化'):auto.apply(again,list(again['plans']))
    assert target.read_text(encoding='utf-8')=='{"items":[]}'


def test_cancel_before_import_keeps_playlists_and_roms_unchanged(tmp_path):
    from task_control import TaskCancelled
    root=tmp_path/'RetroArch';root.mkdir();games=tmp_path/'Roms/GB';games.mkdir(parents=True)
    rom=games/'game.gb';rom.write_bytes(b'test')
    plan=auto.preview(str(root),[str(tmp_path)])
    with pytest.raises(TaskCancelled):auto.apply(plan,list(plan['plans']),cancel_check=lambda:True)
    assert not (root/'playlists').exists()
    assert rom.read_bytes()==b'test'


def test_mtp_storage_requires_real_android_path_and_device_boundary(monkeypatch):
    import content_scan as scan
    root='mtp://handheld/00010001/RetroArch';source='mtp://handheld/00020001/'
    tree={root:[],source:[{'name':'Roms','folder':True}],scan.join(source,'Roms'):[{'name':'GBA','folder':True}]}
    monkeypatch.setattr(scan,'folders',lambda p:tree[p])
    result=auto.preview(root,[source])
    assert not result['plans']
    assert '启动路径' in result['unclassified'][0]['reason']
    with pytest.raises(ValueError,match='当前掌机'):auto.validate({'root':root,'sources':['mtp://another/00020001/']})


def test_overview_uses_actual_artwork_and_storage_counts_and_excludes_bios(tmp_path):
    root=tmp_path/'RetroArch';(root/'playlists').mkdir(parents=True)
    system='FBNeo - Arcade Games';images=root/'thumbnails'/system/'Named_Boxarts';images.mkdir(parents=True)
    Image.new('RGB',(12,18),'green').save(images/'游戏.png')
    (root/'playlists/FBNeo.lpl').write_text(json.dumps({'items':[
        {'path':'/storage/CARD/Roms/FBNEO/game.zip','label':'游戏','db_name':system+'.lpl'},
        {'path':'/storage/emulated/0/Roms/FBNEO/another.zip','label':'另一个','db_name':system+'.lpl'},
        {'path':'/storage/CARD/Roms/FBNEO/neogeo.zip','label':'系统','db_name':system+'.lpl'}]}), encoding='utf-8')
    result=workbench_library.overview(str(root))['playlists'][0]['locations']
    assert result['card']['count']==1 and result['internal']['count']==1
    assert result['card']['covers'][0]['label']=='游戏'
    assert result['internal']['missing']==1
