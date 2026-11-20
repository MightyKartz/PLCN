import hashlib
import io
from pathlib import Path

from PIL import Image
import pytest

import app_paths
from artwork_provenance import mark_stale, save
from thumbnail_downloader import ThumbnailDownloader


def picture(color):
    data = io.BytesIO();Image.new('RGB', (2, 2), color).save(data, format='PNG');return data.getvalue()


@pytest.mark.parametrize('automatic,changed,replace', [(True, False, True), (False, False, False), (True, True, False)])
def test_only_unchanged_automatic_images_from_another_game_are_stale(tmp_path, automatic, changed, replace):
    image = tmp_path / 'cover.png';old = picture('red');image.write_bytes(picture('blue') if changed else old)
    save({str(image): {'source': 'Wrong Game', 'sha256': hashlib.sha256(old).hexdigest(), 'automatic': automatic}})
    row = {'thumbnail_source': 'Correct Game', 'match_reason': '', 'artwork': {'Named_Boxarts': {'status': 'exists', 'path': str(image)}}}
    mark_stale(row)
    assert bool(row.get('replace_artwork_hashes')) == replace
    assert image.read_bytes() == (picture('blue') if changed else old)


def test_replacement_requires_matching_bytes(tmp_path):
    old, new = picture('red'), picture('blue')
    target = tmp_path / 'MAME' / 'Named_Boxarts' / '游戏.png';target.parent.mkdir(parents=True);target.write_bytes(old)
    digest = hashlib.sha256(old).hexdigest()
    downloader = ThumbnailDownloader(str(tmp_path))
    downloader.replace_hashes[('MAME', 'Correct Game', '游戏')] = {'Named_Boxarts': digest}
    from types import SimpleNamespace
    downloader.session.get = lambda *args, **kwargs: SimpleNamespace(status_code=200, content=new)
    results = downloader.download_thumbnail('MAME', 'Correct Game', '游戏')
    assert all(r['status'] == 'success' for r in results)
    assert target.read_bytes() == new
    assert not (app_paths.user_data_dir() / 'artwork-backups').exists()
    # A different existing image is treated as a user change and preserved.
    target.write_bytes(picture('green'))
    results = downloader.download_thumbnail('MAME', 'Correct Game', '游戏')
    assert results[0]['status'] == 'skipped'
    assert target.read_bytes() == picture('green')
