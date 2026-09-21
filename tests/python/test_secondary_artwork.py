import json
import time

import pytest

import secondary_artwork as secondary
import single_artwork as art
from dos_artwork_names import search_names


def page(caption='1995 DOS cover'):
    return {'pageid': 42, 'title': 'Example',
            'original': {'source': 'https://upload.wikimedia.org/wikipedia/zh/a/ab/cover.png'},
            'revisions': [{'slots': {'main': {'content': '{{Infobox VG\n| platform = [[MS-DOS]]\n| caption = ' + caption + '\n| image = cover.png\n}}'}}}]}


@pytest.fixture
def provider(tmp_path, monkeypatch):
    monkeypatch.setenv('PLCN_HOME', str(tmp_path))
    monkeypatch.setattr(secondary, 'api', lambda *args: [page()])
    return {'system': 'DOS', 'kind': 'Named_Boxarts', 'query': 'Sword and Fairy'}


def test_candidates_preserve_provenance_and_require_scoped_ids(provider):
    result = secondary.search(provider)
    candidate = result['candidates'][0]
    assert candidate['platform'] == 'MS-DOS'
    assert candidate['source_page'] == 'https://zh.wikipedia.org/?curid=42'
    assert '1995 DOS cover' in candidate['version']
    assert 'url' not in candidate
    assert secondary.load(candidate['id'], 'DOS', 'Named_Boxarts')['provider'] == 'wikipedia'
    for system, kind in [('GBA', 'Named_Boxarts'), ('DOS', 'Named_Snaps')]:
        with pytest.raises(ValueError, match='平台或图片类型'):
            secondary.load(candidate['id'], system, kind)
    for token in ['../anything', 'https://example.com/file', 'bad']:
        with pytest.raises(ValueError):
            secondary.load(token)
    path = secondary.app_paths.cache_dir() / 'secondary-artwork' / (candidate['id'] + '.json')
    entry = json.loads(path.read_text()); entry['created'] = time.time() - 90000
    path.write_text(json.dumps(entry))
    with pytest.raises(ValueError):
        secondary.load(candidate['id'])


def test_no_image_or_wrong_kind_is_not_a_successful_candidate(provider, monkeypatch):
    monkeypatch.setattr(secondary, 'api', lambda *args: [{'pageid':42, 'title':'No image'}])
    assert secondary.search(provider)['total'] == 0
    assert secondary.search({**provider, 'kind':'Named_Titles'})['total'] == 0
    monkeypatch.setattr(secondary, 'api', lambda *args: [page('SEGA Saturn版游戏封面')])
    candidate = secondary.search(provider)['candidates'][0]
    assert 'Saturn' in candidate['version']
    assert '核对' in candidate['version']


def test_untrusted_image_hosts_and_redirect_urls_are_not_candidates(provider, monkeypatch):
    for url in ['http://upload.wikimedia.org/wikipedia/zh/a.png', 'https://evil.test/a.png',
                'https://upload.wikimedia.org.evil.test/wikipedia/x', 'https://user@upload.wikimedia.org/wikipedia/x',
                'https://upload.wikimedia.org:8080/wikipedia/x']:
        result = page(); result['original']['source'] = url
        monkeypatch.setattr(secondary, 'api', lambda *args: [result])
        assert secondary.search(provider)['total'] == 0


def test_empty_caption_does_not_capture_the_next_infobox_field():
    assert secondary.field('|caption=\n|developer=Koei', 'caption') == ''
    assert secondary.field('|platforms = {{hlist|[[DOS]]|[[Windows]]}}', 'platforms?') == 'DOS / Windows'


def test_official_alias_search_includes_pinyin_and_keeps_power_up_kit(monkeypatch):
    monkeypatch.setattr(art, 'catalog_names', lambda *args: ['Xian Jian Qi Xia Zhuan (1995)',
        'Xian Jian Qi Xia Zhuan 2 (2003)', 'Sangokushi V (1995)'])
    result = art.search({'system':'DOS','query':'Sword and Fairy','automatic':True})
    assert result['names'] == ['Xian Jian Qi Xia Zhuan (1995)']
    assert art.search({'system':'DOS','query':'三国志5威力加强版','automatic':True})['names'] == []
    assert '三國志V' not in search_names('DOS', '三国志5威力加强版')
