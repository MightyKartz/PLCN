"""A batch summary is read-only; applying it uses its exact proposals and options."""
import json
from pathlib import Path

import pytest

from batch_review import prepare_review, apply_review
from thumbnail_downloader import ThumbnailDownloader


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setenv('RETROARCH_ASSISTANT_HOME', str(tmp_path / 'home'))
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
    assert 'backup_path' not in result['playlists'][0]['apply']


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
    assert 'backup_path' not in result['playlists'][0]['apply']


def test_rename_still_applies_when_artwork_has_no_source(library, monkeypatch):
    """A missing image gallery must not block a known translation."""
    import playlist_service
    path = library[-1]
    change = {'original_item_label': 'Game', 'original_label': 'Game', 'new_label': '游戏',
              'path': '/roms/Game.nes', 'system': 'NES', 'identity': {},
              'artwork_gallery_status': 'not_found', 'thumbnail_source': None,
              'cover_exists': False, 'artwork': {}}
    monkeypatch.setattr(playlist_service, 'analyze_playlist', lambda *args, **kwargs: [change])
    plan = review(library, images=True)
    assert plan['rows'][0]['names'] == 1
    # The artwork gap remains manual work even though the rename is applied.
    assert plan['rows'][0]['review'] == 1
    monkeypatch.setattr(ThumbnailDownloader, 'download_batch', lambda *args, **kwargs: ThumbnailDownloader.empty_summary())
    result = apply_review(plan, lambda *args: None, lambda: False)
    assert result['processed_count'] == 1
    assert json.loads(path.read_text(encoding='utf-8'))['items'][0]['label'] == '游戏'


@pytest.mark.parametrize('change', [
    {'identity': {'requires_review': True}, 'new_label': '游戏'},
    {'identity': {}, 'new_label': ''},
    {'identity': {}, 'new_label': '游戏', 'artwork_gallery_status': 'not_found', 'thumbnail_source': None},
], ids=['unverified-identity', 'no-translation', 'no-gallery'])
def test_complete_games_are_not_counted_as_manual_work(library, monkeypatch, change):
    """A game with a Chinese name and all artwork needs nothing, verified or not."""
    import playlist_service
    change = {'original_item_label': '游戏', 'path': '/roms/Game.nes', 'system': 'NES',
              'cover_exists': True, **change}
    monkeypatch.setattr(playlist_service, 'analyze_playlist', lambda *args, **kwargs: [change])
    assert review(library, images=True)['rows'][0]['review'] == 0


def test_untranslatable_english_name_is_manual_work(library, monkeypatch):
    """A name the catalogue cannot translate must not vanish from the summary."""
    import playlist_service
    change = {'original_item_label': 'Ketsui', 'new_label': 'Ketsui', 'path': '/roms/ket.zip',
              'system': 'NES', 'identity': {}, 'thumbnail_source': 'Ketsui', 'cover_exists': True}
    monkeypatch.setattr(playlist_service, 'analyze_playlist', lambda *args, **kwargs: [change])
    assert review(library, images=True)['rows'][0]['review'] == 1


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
        return None
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


def classify(change, names=True, images=True):
    from batch_review import classify_change
    return classify_change(dict(change), {'write_names': names, 'download_thumbnails': images})


def base_change(**overrides):
    change = {'original_item_label': 'Game', 'original_label': 'Game', 'new_label': '游戏',
              'path': '/roms/Game.zip', 'system': 'NES', 'identity': {},
              'thumbnail_source': 'Game (USA)', 'cover_exists': False,
              'artwork': {'Named_Boxarts': {'status': 'missing'}}, 'artwork_gallery_status': 'found'}
    change.update(overrides)
    return change


@pytest.mark.parametrize('change,names,images,expected', [
    # Trusted rename, no artwork source: rename applies, artwork gap is manual.
    (base_change(thumbnail_source=None, artwork_gallery_status='not_found'), True, True,
     {'rename': True, 'artwork': False, 'manual': True}),
    (base_change(thumbnail_source=None, artwork_gallery_status='unavailable'), True, True,
     {'rename': True, 'artwork': False, 'manual': True}),
    # Complete game, gallery empty: nothing to do, nothing manual.
    (base_change(original_item_label='游戏', thumbnail_source=None, artwork_gallery_status='not_found',
                 cover_exists=True, artwork={'Named_Boxarts': {'status': 'exists'}}), True, True,
     {'rename': False, 'artwork': False, 'manual': False}),
    # Untranslatable English name, artwork complete: manual name gap only.
    (base_change(new_label='Game', cover_exists=True,
                 artwork={'Named_Boxarts': {'status': 'exists'}}), True, True,
     {'rename': False, 'artwork': False, 'manual': True}),
    # Untranslatable English name and no artwork source: one manual entry.
    (base_change(new_label='Game', thumbnail_source=None, artwork_gallery_status='not_found'), True, True,
     {'rename': False, 'artwork': False, 'manual': True}),
    # Conflicting identity blocks auto-apply but stays manual.
    (base_change(identity={'requires_review': True}, thumbnail_source=None,
                 artwork_gallery_status='not_found'), True, True,
     {'rename': False, 'artwork': False, 'manual': True}),
    # Names-only run: rename applies, artwork never counted.
    (base_change(thumbnail_source=None, artwork_gallery_status='unavailable'), True, False,
     {'rename': True, 'artwork': False, 'manual': False}),
    # Artwork-only run on a complete, untranslatable game: nothing to do.
    (base_change(new_label='Game', cover_exists=True,
                 artwork={'Named_Boxarts': {'status': 'exists'}}), False, True,
     {'rename': False, 'artwork': False, 'manual': False}),
], ids=['rename-gallery-not-found', 'rename-gallery-unavailable', 'complete-game',
        'untranslatable-complete', 'untranslatable-no-source', 'identity-conflict',
        'names-only-rename', 'images-only-complete'])
def test_classify_change_acceptance_matrix(change, names, images, expected):
    assert classify(change, names, images) == expected


def test_classify_change_strips_unverified_source_for_rename():
    change = base_change(artwork_gallery_status='not_found')
    from batch_review import classify_change
    verdict = classify_change(change, {'write_names': True, 'download_thumbnails': True})
    assert verdict['rename'] is True and verdict['artwork'] is False
    assert change['thumbnail_source'] is None


def test_classify_change_artwork_only_uses_current_label_for_missing_images(tmp_path, monkeypatch):
    """仅补图时按实际保留的列表名称查本地图片，而不是按提案名。"""
    checked = []
    monkeypatch.setattr('batch_review.open_artwork_reader', lambda t, s: ('resolver', 'lookups', None))
    monkeypatch.setattr('batch_review.artwork_statuses',
                        lambda label, path, *args: checked.append(label)
                        or {'Named_Boxarts': {'status': 'exists'}})
    change = base_change(new_label='游戏')
    from batch_review import classify_change
    verdict = classify_change(change, {'write_names': False, 'download_thumbnails': True},
                              str(tmp_path), 'NES', {})
    assert checked == ['Game']
    assert change['new_label'] == 'Game'
    assert verdict == {'rename': False, 'artwork': False, 'manual': False}
