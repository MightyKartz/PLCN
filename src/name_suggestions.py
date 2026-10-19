"""Offer English search names from the bundled Chinese name catalog.

A suggestion is a search aid, never a confirmed identity: callers must show the
candidates and let the user choose one. A missing or unreadable catalog degrades
to "no suggestions" instead of breaking artwork lookup.
"""
import json
import re
from pathlib import Path

import app_paths
from artwork_identity import title_key

# CJK ideographs, kana and hangul: a query in these scripts cannot appear in the
# English gallery index, so it must be translated before it can match.
CJK = re.compile(r'[\u2e80-\u9fff\u3040-\u30ff\uac00-\ud7af]')
# Below this score the catalog search is guessing; the user must still confirm,
# but a weak list is noise rather than a search aid.
FUZZY_MIN = 70
TIERS = ('exact', 'contains', 'fuzzy')


def has_cjk(value):
    return bool(CJK.search(str(value or '')))


def source_path(config_path=None, name_source=None):
    if name_source:
        return Path(name_source)
    config = Path(config_path or app_paths.config_path())
    try:
        settings = json.loads(config.read_text())
    except (OSError, ValueError):
        settings = {}
    return Path(settings.get('rom_name_cn_path') or app_paths.default_source())


def tier(query, english, chinese):
    """Grade one catalog row against the query; cheapest, most certain test first."""
    key = title_key(query)
    if not key:
        return 'fuzzy'
    if key in {title_key(english), title_key(chinese)}:
        return 'exact'
    if key in title_key(english) or key in title_key(chinese):
        return 'contains'
    return 'fuzzy'


def suggest(system, query, config_path=None, name_source=None, limit=8):
    """Rank English names in the local catalog for one Chinese or English query."""
    text = str(query or '').strip()
    if len(text) < 2:
        return []
    try:
        from data_pack import open_database
        database = open_database(source_path(config_path, name_source))
    except Exception:
        return []
    try:
        rows = database.search_by_keyword(text, system=system, limit=limit * 2)
    except Exception:
        return []
    finally:
        database.close()
    key = title_key(text)
    found, seen = [], set()
    for row in rows:
        english = str(row.get('english_name') or '').strip()
        chinese = str(row.get('chinese_name') or '').strip()
        if not english or title_key(english) in seen:
            continue
        grade = tier(text, english, chinese)
        score = row.get('score')
        if grade == 'fuzzy':
            # A much shorter catalog name inside a longer query is usually a
            # generic word ("游戏"), not the game the user asked for.
            lengths = sorted((len(key), len(title_key(chinese) or title_key(english))))
            if not lengths[0] or lengths[0] / lengths[1] < 0.55:
                continue
            if score is None or float(score) < FUZZY_MIN:
                continue
        seen.add(title_key(english))
        found.append({'english_name': english, 'chinese_name': chinese, 'tier': grade,
                      'score': None if score is None else round(float(score))})
        if len(found) >= limit:
            break
    found.sort(key=lambda item: (TIERS.index(item['tier']), -(item['score'] or 0), item['english_name']))
    return found
