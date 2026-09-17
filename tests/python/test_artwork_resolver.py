import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace

from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).parent / 'src'))
from artwork_resolver import ArtworkResolver, artwork_path, sanitize_filename, valid_image_file
from thumbnail_downloader import ThumbnailDownloader
import plcn


def png():
    output = io.BytesIO()
    Image.new('RGB', (2, 2)).save(output, format='PNG')
    return output.getvalue()


def test_per_type_status_detects_damage_and_reusable_source(tmp_path):
    cover = artwork_path(tmp_path, 'NES', '中文')
    cover.parent.mkdir(parents=True)
    cover.write_bytes(b'broken')
    snap = artwork_path(tmp_path, 'NES', 'Game (USA)', 'Named_Snaps')
    snap.parent.mkdir(parents=True)
    snap.write_bytes(png())
    result = ArtworkResolver(tmp_path, 'NES').resolve_all('中文', source='Game (USA)')
    assert result['Named_Boxarts']['status'] == 'invalid'
    assert result['Named_Snaps']['status'] == 'reusable'
    assert result['Named_Titles']['status'] == 'missing'


def test_download_reuses_english_artwork_without_network(tmp_path):
    downloader = ThumbnailDownloader(str(tmp_path))
    for kind in downloader.THUMBNAIL_TYPES:
        path = artwork_path(tmp_path, 'NES', 'Game', kind)
        path.parent.mkdir(parents=True)
        path.write_bytes(png())
    def unexpected(*args, **kwargs):
        raise AssertionError('No network needed')
    downloader.session.get = unexpected
    results = downloader.download_thumbnail('NES', 'Game', '中文')
    assert all(row['reason'] == 'reused_local' for row in results)
    assert all(valid_image_file(row['path']) for row in results)


def test_download_rejects_html_then_repairs_invalid_images(tmp_path):
    downloader = ThumbnailDownloader(str(tmp_path))
    downloader.session.get = lambda *a, **kw: SimpleNamespace(status_code=200, content=b'<html>error</html>')
    assert all(row['reason'] == 'invalid_image' for row in downloader.download_thumbnail('NES', 'Game', '中文'))
    assert not list(tmp_path.rglob('*.png'))
    target = artwork_path(tmp_path, 'NES', '中文')
    target.write_bytes(b'incomplete')
    downloader.session.get = lambda *a, **kw: SimpleNamespace(status_code=200, content=png())
    assert all(row['status'] == 'success' for row in downloader.download_thumbnail('NES', 'Game', '中文'))
    assert valid_image_file(target)


def test_not_found_has_distinct_reason(tmp_path, monkeypatch):
    monkeypatch.setattr('single_artwork.catalog_names', lambda *args: [])
    downloader = ThumbnailDownloader(str(tmp_path))
    downloader.session.get = lambda *a, **kw: SimpleNamespace(status_code=404)
    assert all(row['reason'] == 'not_found' for row in downloader.download_thumbnail('NES', 'Game', '中文'))


def test_missing_catalog_spelling_retries_verified_name_and_keeps_target(tmp_path, monkeypatch):
    from urllib.parse import unquote
    monkeypatch.setattr('single_artwork.catalog_names', lambda *args: ['Out Run (Japan)'])
    downloader = ThumbnailDownloader(str(tmp_path))
    calls = []
    def get(url, **kwargs):
        calls.append(unquote(url))
        return SimpleNamespace(status_code=200, content=png()) if calls[-1].endswith('/Out Run (Japan).png') else SimpleNamespace(status_code=404)
    downloader.session.get = get
    results = downloader.download_thumbnail('NEC - PC Engine - TurboGrafx 16', 'OutRun (Japan) (En)', '户外大飙车')
    assert len(calls) == 6
    assert all(row['status'] == 'success' and row['gallery_source'] == 'Out Run (Japan)' for row in results)
    assert all(Path(row['path']).name == '户外大飙车.png' and valid_image_file(row['path']) for row in results)


def test_batch_coalesces_duplicates_and_rejects_colliding_sources(tmp_path):
    downloader = ThumbnailDownloader(str(tmp_path))
    calls = []
    def get(*args, **kwargs):
        calls.append(args[0])
        return SimpleNamespace(status_code=200, content=png())
    downloader.session.get = get
    task = ('NES', 'Game', '中文')
    result = downloader.download_batch([task, task])
    assert len(calls) == 3
    assert result['item_count'] == 1
    assert result['total']['success'] == 3
    calls.clear()
    result = downloader.download_batch([('NES', 'Game (USA)', '同名'), ('NES', 'Game (Japan)', '同名')])
    assert not calls
    assert result['total']['failed'] == 3
    assert all(row['reason'] == 'filename_collision' for row in result['details'])
    assert not artwork_path(tmp_path, 'NES', '同名').exists()


def test_shared_naming_rules_and_directory_boundary(tmp_path):
    title = 'A`B"C/D&E'
    assert sanitize_filename(title) == 'A_B_C_D_E'
    assert plcn.sanitize_thumbnail_filename(title) == ThumbnailDownloader(str(tmp_path)).sanitize_filename(title)
    with pytest.raises(ValueError):
        artwork_path(tmp_path, '../outside', 'Game')


def test_mixed_playlist_resolves_each_entry_system(tmp_path, monkeypatch):
    from data_pack import build_pack
    from libretro_db import LibretroDB
    source = tmp_path / 'source'
    source.mkdir()
    for system, cn in [('NES', '红色'), ('SNES', '绿色')]:
        (source / (system + '.csv')).write_text('Name EN,Name CN\nSame Game,' + cn + '\n', encoding='utf-8')
    pack = tmp_path / 'pack'
    build_pack(source, pack)
    monkeypatch.setattr(LibretroDB, 'load_system_dat', lambda *a: False)
    path = tmp_path / 'Favorites.lpl'
    path.write_text(json.dumps({'items': [{'path': '/roms/a.zip', 'label': 'Same Game', 'db_name': 'NES.lpl'}, {'path': '/roms/b.zip', 'label': 'Same Game', 'db_name': 'SNES.lpl'}]}))
    results = plcn.analyze_playlist(str(path), 'Favorites', str(pack / 'rom-name-cn'), str(tmp_path / 'art'))
    assert [row['system'] for row in results] == ['NES', 'SNES']
    assert [row['new_label'] for row in results] == ['红色', '绿色']
    assert all(set(row['artwork']) == set(ThumbnailDownloader.THUMBNAIL_TYPES) for row in results)
