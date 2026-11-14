"""A batch summary is read-only; applying it uses its exact proposals and options."""
import json
from pathlib import Path

import pytest

from batch_review import prepare_review, apply_review
from thumbnail_downloader import ThumbnailDownloader


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setenv('PLCN_HOME', str(tmp_path / 'home'))
    root = tmp_path / 'library'
    lists = root / 'playlists'
    lists.mkdir(parents=True)
    images = root / 'thumbnails'
    images.mkdir()
    source = tmp_path / 'source'
    source.mkdir()
    path = lists / 'NES.lpl'
    path.write_text(json.dumps({'items': [{'label': 'Game', 'path': '/roms/Game.nes', 'db_name': 'NES.lpl'}]}), encoding='utf-8')
    (source / 'NES.csv').write_text('Name EN,Name CN\nGame,游戏\n', encoding='utf-8')
    return lists, images, source, path


def review(library, names=True, images=False):
    lists, thumbnails, source, _ = library
    return prepare_review(str(lists), str(thumbnails), str(source), None,
                          {'write_names': names, 'download_thumbnails': images}, lambda *args: None, lambda: False)


def test_summary_reads_only_and_apply_does_not_match_again(library):
    _, _, source, path = library
    before = path.read_bytes()
    plan = review(library)
    assert path.read_bytes() == before
    assert plan['rows'][0]['names'] == 1
    assert plan['rows'][0]['artwork'] == 0
    # A source update after review must not silently substitute new suggestions.
    (source / 'NES.csv').write_text('Name EN,Name CN\nGame,另一个译名\n', encoding='utf-8')
    result = apply_review(plan, lambda *args: None, lambda: False)
    assert not result['errors']
    assert result['processed_count'] == 1
    assert json.loads(path.read_text(encoding='utf-8'))['items'][0]['label'] == '游戏'
    assert result['playlists'][0]['apply']['backup_path']


def test_external_playlist_edit_requires_a_fresh_summary(library):
    path = library[-1]
    plan = review(library)
    content = json.loads(path.read_text(encoding='utf-8'))
    content['items'][0]['label'] = '外部修改'
    path.write_text(json.dumps(content), encoding='utf-8')
    before = path.read_bytes()
    result = apply_review(plan, lambda *args: None, lambda: False)
    assert '汇总后已改变' in result['errors'][0]
    assert result['processed_count'] == 0
    assert path.read_bytes() == before
    import app_paths
    assert not list((app_paths.user_data_dir() / 'playlist-backups').glob('*'))


def test_artwork_only_uses_original_labels_and_preserves_playlist_bytes(library, monkeypatch):
    path = library[-1]
    before = path.read_bytes()
    tasks = []
    def download(_self, batch, **_kwargs):
        tasks.extend(batch)
        return ThumbnailDownloader.empty_summary()
    monkeypatch.setattr(ThumbnailDownloader, 'download_batch', download)
    plan = review(library, names=False, images=True)
    assert plan['rows'][0]['names'] == 0
    assert plan['rows'][0]['artwork'] == 1
    result = apply_review(plan, lambda *args: None, lambda: False)
    assert result['processed_count'] == 1
    assert path.read_bytes() == before
    assert tasks and all(task[2] == 'Game' for task in tasks)
    assert result['playlists'][0]['apply']['backup_path'] is None


def test_invalid_playlist_is_visible_in_summary_and_stop_option_refuses_writes(library):
    lists, _, _, path = library
    (lists / 'Broken.lpl').write_text('{', encoding='utf-8')
    before = path.read_bytes()
    plan = review(library)
    assert len(plan['rows']) == 2
    assert any(row['error'] for row in plan['rows'])
    with pytest.raises(ValueError, match='读取失败'):
        apply_review(plan, lambda *args: None, lambda: False, continue_on_error=False)
    assert path.read_bytes() == before
    result = apply_review(plan, lambda *args: None, lambda: False)
    assert result['processed_count'] == 1
    assert len(result['errors']) == 1


def test_cancelling_review_never_writes(library):
    from task_control import TaskCancelled
    lists, images, source, path = library
    before = path.read_bytes()
    with pytest.raises(TaskCancelled):
        prepare_review(str(lists), str(images), str(source), None, {'write_names': True, 'download_thumbnails': False},
                       lambda *args: None, lambda: True)
    assert path.read_bytes() == before


@pytest.mark.parametrize('write_names', [True, False], ids=['rename', 'artwork-only'])
def test_adb_transport_only_pushes_playlist_when_names_are_enabled(library, monkeypatch, write_names):
    import shutil
    import playlist_transport as transport
    from safe_io import file_digest
    path = library[-1]
    original = path.read_bytes()
    plan = review(library, names=write_names, images=not write_names)['plans'][0]
    pushed_lists, pushed_images, staged = [], [], []
    def materialize(_uri, cache_dir):
        local = Path(cache_dir) / 'NES.lpl'
        shutil.copyfile(path, local)
        staged.append(local)
        return str(local)
    def push_playlist(local, uri, expected):
        assert expected == json.loads(original)
        assert json.loads(Path(local).read_text(encoding='utf-8'))['items'][0]['label'] == '游戏'
        pushed_lists.append(uri)
        return 'adb://device/backup/NES.lpl'
    monkeypatch.setattr(transport, 'materialize_adb_file', materialize)
    monkeypatch.setattr(transport, 'verified_push_adb_playlist', push_playlist)
    monkeypatch.setattr(transport, 'push_adb_directory', lambda local, uri: pushed_images.append(uri))
    monkeypatch.setattr(ThumbnailDownloader, 'download_batch', lambda *args, **kwargs: ThumbnailDownloader.empty_summary())
    result = transport.apply_playlist('adb://device/sdcard/RetroArch/playlists/NES.lpl', plan['changes'],
                                      'adb://device/sdcard/RetroArch/thumbnails',
                                      options={'write_names': write_names, 'download_thumbnails': not write_names},
                                      progress=lambda *args: None, cancel_check=lambda: False, expected_digest=file_digest(path))
    assert len(pushed_lists) == int(write_names)
    assert len(pushed_images) == int(not write_names)
    assert result['transport'] == 'adb'
    assert result['applied_count'] == int(write_names)
    assert path.read_bytes() == original
    assert all(not local.exists() for local in staged)
