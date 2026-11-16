import csv
import json
from pathlib import Path

from playlist_analysis import analyze_playlist


def test_mame_catalog_contains_correct_romset_names_not_neogeo_fuzzy_guesses():
    source = Path(__file__).resolve().parents[2] / 'data' / 'rom-name-cn' / 'MAME.csv'
    with source.open(encoding='utf-8') as handle:
        rows = {r['MAME Name']: r for r in csv.DictReader(handle)}
    assert len(rows) > 2000
    assert rows['hook']['CN Name'] == '铁钩船长'
    assert rows['raiden']['EN Name'] == 'Raiden'
    assert rows['inthunt']['CN Name'] == '海底大战争'
    assert rows['tdragon']['EN Name'] == 'Thunder Dragon'
    assert rows['s1945']['EN Name'] != 'Strikers 1945 Plus'


def test_missing_box_art_uses_same_game_snapshot_for_preview_and_download(tmp_path, monkeypatch):
    from thumbnail_downloader import ThumbnailDownloader
    from artwork_resolver import valid_png
    from PIL import Image
    from types import SimpleNamespace
    import io

    system = 'MAME';source = tmp_path / 'names';source.mkdir()
    (source / 'MAME.csv').write_text('Name EN,Name CN\nMahjong Example,麻雀示例\n', encoding='utf-8')
    monkeypatch.setattr('single_artwork.catalog_names', lambda system, kind: [] if kind == 'Named_Boxarts' else ['Mahjong Example'])
    playlist = tmp_path / 'games.lpl'
    playlist.write_text(json.dumps({'items': [{'label': '麻雀示例', 'path': '/roms/麻雀示例.zip'}]}), encoding='utf-8')
    row = analyze_playlist(str(playlist), system, str(source), verify_artwork=True)[0]
    assert row['thumbnail_source'] == 'Mahjong Example'
    assert row['artwork_cover_fallback'] == 'Named_Snaps'
    assert not row['identity']['requires_review']
    data = io.BytesIO();Image.new('RGB', (2, 2), 'green').save(data, format='PNG')
    downloader = ThumbnailDownloader(str(tmp_path / 'images'))
    key = (system, row['thumbnail_source'], row['new_label'])
    downloader.cover_fallbacks[key] = row['artwork_cover_fallback']
    downloader.session.get = lambda url, **kwargs: SimpleNamespace(status_code=404 if '/Named_Boxarts/' in url else 200, content=data.getvalue())
    results = downloader.download_thumbnail(*key)
    assert all(r['status'] == 'success' for r in results)
    assert results[0]['gallery_kind'] == 'Named_Snaps'
    assert '/Named_Snaps/' in results[0]['url']
    assert Path(results[0]['path']).parent.name == 'Named_Boxarts'
    assert all(valid_png(Path(r['path']).read_bytes()) for r in results)
    # After application a refreshed preview sees an ordinary valid image;
    # it does not offer the fallback as another pending download.
    again = analyze_playlist(str(playlist), system, str(source), str(tmp_path / 'images'), verify_artwork=True)[0]
    assert all(a['status'] == 'exists' for a in again['artwork'].values())
