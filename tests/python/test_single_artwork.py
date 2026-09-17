import base64
import errno
import io
import json
from pathlib import Path
import shlex
from types import SimpleNamespace

import pytest
from PIL import Image

import single_artwork as art


def picture(color='red', fmt='PNG'):
    buffer = io.BytesIO()
    Image.new('RGB', (12, 16), color).save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setenv('PLCN_HOME', str(tmp_path / 'runtime'))
    playlist = tmp_path / 'GBA.lpl'
    playlist.write_text(json.dumps({'items': [{'label': '游戏一', 'path': '/roms/one.gba'}, {'label': '游戏二', 'path': '/roms/two.gba'}]}))
    return {'playlist_path': str(playlist), 'system': 'GBA', 'thumbnails': str(tmp_path / '图片'),
            'index': 0, 'label': '游戏一', 'rom_path': '/roms/one.gba', 'kind': 'Named_Boxarts',
            'upload': base64.b64encode(picture(fmt='JPEG')).decode(), 'filename': '本地图.jpg'}


def test_preview_does_not_write_then_confirm_only_updates_one_image(context):
    playlist = Path(context['playlist_path'])
    original = playlist.read_bytes()
    other = Path(context['thumbnails']) / 'GBA/Named_Boxarts/游戏二.png'
    other.parent.mkdir(parents=True)
    other.write_bytes(picture('blue'))
    prepared = art.preview(context)
    target = Path(prepared['target'])
    assert not target.exists()
    assert prepared['replacing'] is False
    result = art.apply(prepared['token'])
    assert art.valid_png(target.read_bytes())
    assert art.apply(prepared['token']) == result  # Retry cannot write twice.
    assert result['backup'] is None
    assert other.read_bytes() == picture('blue')
    assert playlist.read_bytes() == original
    assert len(list(other.parent.glob('*.png'))) == 2


def test_replacement_preserves_old_image_and_receipt(context):
    target = Path(context['thumbnails']) / 'GBA/Named_Boxarts/游戏一.png'
    target.parent.mkdir(parents=True)
    target.write_bytes(picture('green'))
    prepared = art.preview(context)
    assert prepared['replacing']
    assert target.read_bytes() == picture('green')
    result = art.apply(prepared['token'])
    assert Path(result['backup']).read_bytes() == picture('green')
    assert prepared['current_image_url'] != result['image_url']
    assert 'before-' in prepared['current_image_url'] and 'after-' in result['image_url']
    assert target.read_bytes() != picture('green')
    assert art.apply(prepared['token']) == result


def test_sd_card_without_hard_links_can_add_image(context, monkeypatch):
    def unsupported(*args):
        raise OSError(errno.ENOTSUP, 'Hard links unsupported')
    monkeypatch.setattr(art.os, 'link', unsupported)
    prepared = art.preview(context)
    result = art.apply(prepared['token'])
    assert art.valid_png(Path(result['target']).read_bytes())
    assert not list(Path(result['target']).parent.glob('*.tmp'))


def test_adb_binary_reads_preserve_remote_exit_status(monkeypatch):
    def run(args, **kwargs):
        assert args[3:5] == ['shell', '-T']
        return SimpleNamespace(returncode=44, stdout=b'', stderr=b'')
    monkeypatch.setattr(art.subprocess, 'run', run)
    assert art.read_target('adb://device/sdcard/missing.png') is None


@pytest.mark.parametrize('change', ['playlist', 'target', 'candidate'])
def test_stale_review_cannot_write(context, change):
    prepared = art.preview(context)
    target = Path(prepared['target'])
    if change == 'playlist':
        path = Path(context['playlist_path'])
        path.write_text(path.read_text().replace('one.gba', 'changed.gba'))
    elif change == 'target':
        target.parent.mkdir(parents=True)
        target.write_bytes(picture('blue'))
    else:
        (art.app_paths.cache_dir() / 'artwork-previews' / (prepared['token'] + '.png')).write_bytes(picture('blue'))
    with pytest.raises((ValueError, RuntimeError)):
        art.apply(prepared['token'])
    if change == 'target':
        assert target.read_bytes() == picture('blue')
    else:
        assert not target.exists()


def test_colliding_image_names_reject_single_game_action(context):
    path = Path(context['playlist_path'])
    data = json.loads(path.read_text(encoding='utf-8'))
    data['items'][1]['label'] = data['items'][0]['label']
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='共用'):
        art.preview(context)


def test_corrupt_upload_and_invalid_kind_are_rejected(context):
    with pytest.raises(ValueError, match='损坏'):
        art.preview({**context, 'upload': base64.b64encode(b'not image').decode()})
    with pytest.raises(ValueError):
        art.preview({**context, 'kind': '../escape'})


def test_online_source_search_and_preview_are_distinct(context, monkeypatch):
    urls = []
    def get(url):
        urls.append(url)
        if url.endswith('/'):
            return b'<a href="Goodboy%20Galaxy%20(World).png">image</a><a href="../evil.png">bad</a>'
        return picture()
    monkeypatch.setattr(art, 'download', get)
    result = art.search({'system': 'GBA', 'query': 'goodboy', 'kind': 'Named_Boxarts'})
    assert result['names'] == ['Goodboy Galaxy (World)'] and result['total'] == 1
    assert result['candidates'][0]['image_url'].startswith('/api/artwork/thumbnail?')
    request = {key: value for key, value in context.items() if key != 'upload'}
    prepared = art.preview({**request, 'source': result['names'][0]})
    assert urls[-1].endswith('/Named_Boxarts/Goodboy%20Galaxy%20%28World%29.png')
    assert not Path(prepared['target']).exists()
    from artwork_identity import remembered
    assert remembered(context) == {}
    art.apply(prepared['token'])
    assert remembered(context)['sources']['Named_Boxarts'] == result['names'][0]
    assert art.search({'system': 'GBA', 'query': 'not found'})['names'] == []


@pytest.mark.parametrize('broken_push', [False, True])
def test_adb_stages_verifies_and_only_replaces_selected_image(context, monkeypatch, broken_push):
    context['thumbnails'] = 'adb://device/sdcard/RetroArch/thumbnails'
    remote_target = context['thumbnails'] + '/GBA/Named_Boxarts/游戏一.png'
    remote = {remote_target: picture('green'), remote_target.replace('游戏一', '游戏二'): picture('blue')}
    original_read = art.read_target
    monkeypatch.setattr(art, 'read_target', lambda path: remote.get(path) if path.startswith('adb://') else original_read(path))
    def push(local, target):
        remote[target] = b'bad' if broken_push else Path(local).read_bytes()
    monkeypatch.setattr(art, 'push_adb_file', push)
    commands = []
    def command(serial, script):
        args = shlex.split(script)
        commands.append(args[0])
        uri = lambda p: 'adb://' + serial + p
        if args[0] in {'cp', 'mv'}:
            remote[uri(args[2])] = remote[uri(args[1])]
            if args[0] == 'mv': del remote[uri(args[1])]
        elif args[0] == 'rm': remote.pop(uri(args[-1]), None)
    monkeypatch.setattr(art, 'adb_command', command)
    prepared = art.preview(context)
    if broken_push:
        with pytest.raises(RuntimeError, match='暂存'):
            art.apply(prepared['token'])
        assert remote[remote_target] == picture('green')
        assert 'mv' not in commands
    else:
        result = art.apply(prepared['token'])
        assert remote[result['backup']] == picture('green')
        assert art.valid_png(remote[remote_target])
        assert remote[remote_target] != picture('green')
    assert remote[remote_target.replace('游戏一', '游戏二')] == picture('blue')
    assert not any(path.endswith('.tmp') for path in remote)


def test_status_separates_missing_damaged_and_disconnected(context, monkeypatch):
    path = Path(context['thumbnails']) / 'bad.png'
    assert art.image_status(str(path))['status'] == 'missing'
    path.parent.mkdir()
    path.write_bytes(b'bad')
    assert art.image_status(str(path))['status'] == 'invalid'
    def disconnected(path): raise RuntimeError('offline')
    monkeypatch.setattr(art, 'read_target', disconnected)
    assert art.image_status('adb://offline/image.png')['status'] == 'unreadable'


def share_names(context):
    path = Path(context['playlist_path'])
    data = json.loads(path.read_text(encoding='utf-8'))
    data['items'][1]['label'] = data['items'][0]['label']
    path.write_text(json.dumps(data))
    return path, path.read_bytes(), data


def test_shared_entry_gets_independent_artwork_without_changing_other_rom(context):
    path, original, data = share_names(context)
    info = art.entry_context(context)
    assert len(info['shared']) == 2
    assert info['suggested_label'] == 'one'
    old = Path(context['thumbnails']) / 'GBA' / 'Named_Boxarts' / '游戏一.png'
    old.parent.mkdir(parents=True); old.write_bytes(picture('blue'))
    snap = old.parent.parent / 'Named_Snaps' / old.name
    snap.parent.mkdir(); snap.write_bytes(picture('green'))
    prepared = art.preview({**context, 'new_label': '游戏一 独立版'})
    assert path.read_bytes() == original
    assert not Path(prepared['target']).exists()
    result = art.apply(prepared['token'])
    updated = json.loads(path.read_text(encoding='utf-8'))
    assert updated['items'][0] == {**data['items'][0], 'label': '游戏一 独立版'}
    assert updated['items'][1] == data['items'][1]
    assert Path(result['playlist_backup']).read_bytes() == original
    assert old.read_bytes() == picture('blue')
    assert snap.read_bytes() == picture('green')
    assert picture('green') in [p.read_bytes() for p in snap.parent.glob('游戏一*.png')]
    assert art.apply(prepared['token']) == result


@pytest.mark.parametrize('remote', [False, True])
def test_shared_name_suggestion_avoids_existing_artwork_in_all_types(context, monkeypatch, remote):
    share_names(context)
    existing = {'Named_Boxarts': {'ONE.PNG'}, 'Named_Snaps': {'one (2).png'}, 'Named_Titles': set()}
    if remote:
        context['thumbnails'] = 'adb://device/sdcard/thumbnails'
        monkeypatch.setattr(art, 'remote_inventory', lambda root, system, kind: {'filenames': existing[kind]})
    else:
        for kind, names in existing.items():
            directory = Path(context['thumbnails']) / 'GBA' / kind
            directory.mkdir(parents=True)
            for name in names:
                (directory / name).write_bytes(picture())
    assert art.entry_context(context)['suggested_label'] == 'one (3)'


def test_independent_rename_detects_playlist_change_without_overwriting_it(context):
    path, _, data = share_names(context)
    prepared = art.preview({**context, 'new_label': '独立名称'})
    data['items'].append({'label': 'later', 'path': '/later.gba'})
    path.write_text(json.dumps(data))
    with pytest.raises(RuntimeError, match='列表已改变'):
        art.apply(prepared['token'])
    assert json.loads(path.read_text(encoding='utf-8')) == data
    assert not Path(prepared['target']).exists()


def test_independent_rename_retry_recovers_after_playlist_commit_response_lost(context, monkeypatch):
    path, original, _ = share_names(context)
    prepared = art.preview({**context, 'new_label': '独立名称'})
    write = art.write_target
    lost = [False]
    def write_then_lose_response(target, content, expected, **kwargs):
        result = write(target, content, expected, **kwargs)
        if target == str(path) and not lost[0]:
            lost[0] = True
            raise RuntimeError('connection lost after commit')
        return result
    monkeypatch.setattr(art, 'write_target', write_then_lose_response)
    with pytest.raises(RuntimeError, match='未确认'):
        art.apply(prepared['token'])
    result = art.apply(prepared['token'])
    assert result['new_label'] == '独立名称'
    assert Path(result['playlist_backup']).read_bytes() == original
    assert len(list(path.parent.glob(path.name + '.bak-*'))) == 1


def test_independent_name_cannot_overwrite_an_existing_unreferenced_image(context):
    share_names(context)
    target = Path(context['thumbnails']) / 'GBA' / 'Named_Boxarts' / '独立名称.png'
    target.parent.mkdir(parents=True); target.write_bytes(picture('blue'))
    with pytest.raises(ValueError, match='已存在'):
        art.preview({**context, 'new_label': '独立名称'})
    assert target.read_bytes() == picture('blue')


@pytest.mark.parametrize('renaming', [False, True])
def test_rom_named_artwork_is_previewed_and_updated_with_label_image(context, renaming):
    root = Path(context['thumbnails']) / 'GBA/Named_Boxarts'
    root.mkdir(parents=True)
    alias = root / 'one.png'
    alias.write_bytes(picture('green'))
    label = root / '游戏一.png'
    label.write_bytes(picture('blue'))
    if renaming:
        share_names(context)
        context = {**context, 'new_label': '独立名称'}
    prepared = art.preview(context)
    assert Path(prepared['rom_target']).name == 'one.png'
    result = art.apply(prepared['token'])
    assert alias.read_bytes() == Path(result['target']).read_bytes()
    assert (root / ('one.png.bak-' + prepared['token'])).read_bytes() == picture('green')
    if renaming:
        assert label.read_bytes() == picture('blue')
    assert art.apply(prepared['token']) == result


def test_rom_image_changed_after_preview_does_not_overwrite_either_image(context):
    root = Path(context['thumbnails']) / 'GBA/Named_Boxarts'
    root.mkdir(parents=True)
    alias = root / 'one.png'
    alias.write_bytes(picture('green'))
    prepared = art.preview(context)
    alias.write_bytes(picture('blue'))
    with pytest.raises(RuntimeError, match='已改变'):
        art.apply(prepared['token'])
    assert not Path(prepared['target']).exists()
    assert alias.read_bytes() == picture('blue')


@pytest.mark.parametrize('renaming', [False, True])
def test_rom_image_sync_recovers_when_second_write_is_interrupted(context, monkeypatch, renaming):
    root = Path(context['thumbnails']) / 'GBA/Named_Boxarts'
    root.mkdir(parents=True)
    alias = root / 'one.png'
    alias.write_bytes(picture('green'))
    if renaming:
        share_names(context)
        context = {**context, 'new_label': '独立名称'}
    original_playlist = Path(context['playlist_path']).read_bytes()
    prepared = art.preview(context)
    original_write = art.write_target
    def fail_alias(target, *args, **kwargs):
        if target == str(alias):
            raise RuntimeError('USB disconnected')
        return original_write(target, *args, **kwargs)
    monkeypatch.setattr(art, 'write_target', fail_alias)
    with pytest.raises(RuntimeError, match='USB'):
        art.apply(prepared['token'])
    assert Path(context['playlist_path']).read_bytes() == original_playlist
    monkeypatch.setattr(art, 'write_target', original_write)
    result = art.apply(prepared['token'])
    assert alias.read_bytes() == Path(result['target']).read_bytes()
    assert art.apply(prepared['token']) == result


def test_rom_alias_used_by_another_label_is_not_silently_overwritten(context):
    path = Path(context['playlist_path'])
    data = json.loads(path.read_text(encoding='utf-8'))
    data['items'][1]['label'] = 'one'
    path.write_text(json.dumps(data))
    alias = Path(context['thumbnails']) / 'GBA/Named_Boxarts/one.png'
    alias.parent.mkdir(parents=True)
    alias.write_bytes(picture('green'))
    with pytest.raises(ValueError, match='其他条目'):
        art.preview(context)
    assert alias.read_bytes() == picture('green')
