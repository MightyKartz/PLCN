"""Wikipedia article artwork, for explicit review only; never bulk auto-applied.

API: https://www.mediawiki.org/wiki/Extension:PageImages#API
Image selection uses server-issued IDs, not caller-supplied download URLs.
"""
import html
import io
import json
import re
import time
import uuid
from urllib.parse import urlsplit

import requests
from PIL import Image

import app_paths
from dos_artwork_names import game
from safe_io import atomic_write_bytes, atomic_write_json

HEADERS = {'User-Agent': 'PLCN/3.2 (RetroArch artwork manager; https://github.com/MightyKartz/PLCN)'}
LIMIT = 12 * 1024 * 1024


def api(language, params):
    try:
        response = requests.get(f'https://{language}.wikipedia.org/w/api.php',
                                params={'action': 'query', 'format': 'json', 'formatversion': 2, **params},
                                headers=HEADERS, timeout=(8, 20))
        response.raise_for_status()
        data = response.json()
        if data.get('error'):
            raise ValueError(data['error'].get('info', 'API error'))
        return data.get('query', {}).get('pages', [])
    except (requests.RequestException, ValueError) as error:
        raise RuntimeError('备用图库连接失败，请稍后重试或导入本地图片') from error


def field(content, name):
    found = re.search(r'^[ \t]*\|[ \t]*(?:' + name + r')[ \t]*=[ \t]*([^\n]*)', content, re.M | re.I)
    value = found[1] if found else ''
    value = re.sub(r'<!--.*?-->|<ref.*?</ref>', '', value)
    value = re.sub(r'\[\[(?:[^\]|]*\|)?([^\]]+)\]\]', r'\1', value)
    value = re.sub(r'\{\{(?:hlist|spml|plainlist|ubl)\|', '', value, flags=re.I)
    value = re.sub(r'<[^>]*>|\{\{.*?\}\}', ' ', value)
    return html.unescape(value.replace('}}', '').replace('|', ' / ').replace("'''", '')).strip()[:300]


def image_url(value):
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or parsed.hostname != 'upload.wikimedia.org' or parsed.port not in (None, 443) or parsed.username or not parsed.path.startswith('/wikipedia/'):
        raise ValueError('备用图片地址无效，请重新搜索')
    return value


def search(payload):
    from artwork_resolver import validate_system
    system = validate_system(payload.get('system', ''))
    kind = payload.get('kind', 'Named_Boxarts')
    if kind != 'Named_Boxarts':
        return {'names': [], 'candidates': [], 'total': 0, 'provider': 'wikipedia',
                'message': '备用来源仅提供条目配图，请为截图或标题图使用官方图库或本地导入。'}
    query = str(payload.get('query') or '').strip()
    if not 2 <= len(query) <= 200:
        raise ValueError('请输入 2–200 个字符的游戏名称')
    known = game(query) if system == 'DOS' else None
    language = 'zh' if known or re.search('[\u3400-\u9fff]', query) else 'en'
    params = {'prop': 'pageimages|revisions|info', 'piprop': 'original', 'pilicense': 'any',
              'rvprop': 'content', 'rvslots': 'main', 'inprop': 'url', 'redirects': 1}
    if known:
        params.update(titles=known[1], converttitles=1)
    else:
        params.update(generator='search', gsrsearch=query, gsrnamespace=0, gsrlimit=5)
    pages = api(language, params)
    directory = app_paths.cache_dir() / 'secondary-artwork'
    directory.mkdir(parents=True, exist_ok=True)
    for old in directory.iterdir():
        if old.is_file() and time.time() - old.stat().st_mtime > 86400:
            old.unlink(missing_ok=True)
    candidates = []
    for page in pages:
        original = page.get('original', {})
        content = page.get('revisions', [{}])[0].get('slots', {}).get('main', {}).get('content', '')
        if not original.get('source') or not re.search(r'\{\{\s*(?:Infobox[ _](?:VG|video[ _]game)|電子遊戲資訊框)', content, re.I):
            continue
        try:
            url = image_url(original['source'])
        except ValueError:
            continue
        token = uuid.uuid4().hex
        platform = field(content, 'platforms?|平台') or '平台未注明'
        caption = field(content, 'caption|图像说明|圖像說明') or ('条目配图：' + field(content, 'image|图像|圖像') + '，平台与版本未注明')
        # Neither a multiplatform article nor a title match certifies this image
        # as DOS box art (some articles use Saturn covers or title screens).
        version = caption + '；请核对是否适用于当前游戏版本'
        if known and 'Power Up Kit' in known[0]:
            version += '；未确认是威力加强版封面'
        entry = {'id': token, 'name': page['title'], 'provider': 'wikipedia', 'provider_label': 'Wikipedia · 备用配图',
                 'system': system, 'kind': kind, 'platform': platform, 'version': version,
                 'source_page': f'https://{language}.wikipedia.org/?curid={page["pageid"]}',
                 'url': url, 'created': time.time()}
        atomic_write_json(directory / (token + '.json'), entry)
        candidates.append({k: v for k, v in entry.items() if k not in {'url', 'created'}})
        candidates[-1]['image_url'] = '/api/artwork/thumbnail?candidate=' + token
    return {'names': [c['name'] for c in candidates], 'candidates': candidates, 'total': len(candidates),
            'provider': 'wikipedia', 'message': '' if candidates else '备用来源未找到合适配图，可修改名称搜索或导入本地图片。'}


def load(token, system=None, kind=None):
    if not isinstance(token, str) or not re.fullmatch('[0-9a-f]{32}', token):
        raise ValueError('请选择搜索结果中的候选图片')
    try:
        entry = json.loads((app_paths.cache_dir() / 'secondary-artwork' / (token + '.json')).read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise ValueError('候选图片已过期，请重新搜索') from error
    if time.time() - entry['created'] > 86400 or (system is not None and entry['system'] != system) or (kind is not None and entry['kind'] != kind):
        raise ValueError('候选图片与当前平台或图片类型不符，请重新搜索')
    image_url(entry['url'])
    return entry


def content(token, system=None, kind=None):
    from single_artwork import normalize_image
    entry = load(token, system, kind)
    cache = app_paths.cache_dir() / 'secondary-artwork' / (token + '.png')
    if not cache.exists():
        try:
            with requests.get(entry['url'], headers=HEADERS, timeout=(8, 25), stream=True, allow_redirects=False) as response:
                response.raise_for_status()
                if response.is_redirect:
                    raise ValueError('备用图片地址已改变，请重新搜索')
                raw = bytearray()
                for chunk in response.iter_content(65536):
                    raw.extend(chunk)
                    if len(raw) > LIMIT:
                        raise ValueError('图片超过 12 MiB，请改用本地导入')
            data, _ = normalize_image(bytes(raw))
            atomic_write_bytes(cache, data)
        except requests.RequestException as error:
            raise RuntimeError('备用图片下载失败，请重试或导入本地图片') from error
    return cache.read_bytes(), entry


def thumbnail(token):
    data, _ = content(token)
    with Image.open(io.BytesIO(data)) as img:
        img.thumbnail((240, 240))
        output = io.BytesIO()
        img.save(output, format='PNG')
    return output.getvalue()
