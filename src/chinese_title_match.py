"""Resolve Chinese filenames against the selected system's catalog, across consoles."""
import json
import re
import unicodedata
from pathlib import Path

from rapidfuzz.fuzz import ratio

from artwork_identity import rom_search_alias
from display_names import base_display_title
from gallery_names import release_tags
from match_evidence import build_match_diagnostics
from playlist_proposals import has_chinese
from rom_paths import rom_title
from title_family import family_key, recommend_source

ROMAN = {'I': '1', 'II': '2', 'III': '3', 'IV': '4', 'V': '5', 'VI': '6', 'VII': '7', 'VIII': '8', 'IX': '9', 'X': '10', 'XX': '20'}
CHINESE_NUMBERS = dict(zip('一二三四五六七八九十', map(str, range(1, 11))))


def resolve_chinese_titles(proposals, translators):
    catalogs = {}
    replacements = None
    for row in proposals:
        query = rom_title(row['path'])
        if (not has_chinese(query) or row['match_source'] == 'manual_override'
                or row.get('translation_match_source') in {'exact', 'exact_alias', 'curated_alias', 'title_family'}
                or row.get('artwork_identity_reason') in {'confirmed', 'remembered', 'curated'}
                or row.get('match_diagnostics', {}).get('conflicts')):
            continue
        translator = translators[row['system']]
        if replacements is None:
            path = Path(translator.rom_name_cn_path) / 'name_alias(Chinese).json'
            metadata = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
            if not isinstance(metadata, dict):
                raise ValueError('中文别名目录必须是 JSON 对象')
            replacements = {}
            for entry in metadata.values():
                if not isinstance(entry, dict):
                    raise ValueError('中文别名条目必须是对象')
                default, aliases = entry.get('default'), entry.get('alias', [])
                if default is None:
                    continue
                if not isinstance(default, str) or not isinstance(aliases, list) or any(not isinstance(a, str) for a in aliases):
                    raise ValueError('中文别名必须使用字符串名称与别名数组')
                replacements.update({a: default for a in aliases if a})
            alias_pattern = re.compile('|'.join(re.escape(a) for a in sorted(replacements, key=len, reverse=True))) if replacements else None

        def chinese_key(value):
            value = unicodedata.normalize('NFKC', base_display_title(value))
            value = re.sub(r'[\[(](?:汉化(?:版)?|(?:简体|繁体)?中文(?:版)?)[\])]', '', value)
            value = re.sub(r'(?<![A-Za-z])[IVX]+(?![A-Za-z])', lambda m: ROMAN.get(m[0], m[0]), value)
            value = re.sub(r'第([一二三四五六七八九十])(?=[次部代])', lambda m: '第' + CHINESE_NUMBERS[m[1]], value)
            if alias_pattern:
                value = alias_pattern.sub(lambda m: replacements[m[0]], value)
            return family_key(value)

        key = chinese_key(query)
        if len(key) < 2:
            continue
        current = row.get('original_item_label') or ''
        if has_chinese(current) and chinese_key(current) != key:
            continue
        if any(family_key('(' + (a or b) + ')') for a, b in re.findall(r'\(([^()]*)\)|\[([^\[\]]*)\]', query)):
            continue
        system = row['system']
        if system not in catalogs:
            systems = translator.db.expand_system_mapping(system)
            placeholders = ','.join('?' for _ in systems)
            catalogs[system] = translator.db.get_connection().execute(
                f'SELECT english_name, chinese_name FROM translations WHERE system_base(system) IN ({placeholders})', systems).fetchall()
        curated = rom_search_alias(system, query)
        constraints = release_tags(query) - {'a', 'b', 'chs', 'cht'}
        digits = re.findall(r'\d+', key)
        checksums = {e['resolved_name'] for e in row.get('match_diagnostics', {}).get('evidence_chain', [])
                     if e.get('source') in {'playlist_crc32', 'local_zip_crc'} and e.get('resolved_name')}
        ranked = {}
        for record in catalogs[system]:
            english, chinese = record['english_name'], record['chinese_name']
            if not chinese or not constraints <= release_tags(english) or (checksums and english not in checksums):
                continue
            candidate = chinese_key(chinese)
            if not candidate:
                continue
            if curated:
                if family_key(curated) != family_key(english):
                    continue
                grade, score = 4, 100
            else:
                other_digits = re.findall(r'\d+', candidate)
                if digits != other_digits:
                    continue
                parts = [chinese_key(part) for part in re.split(r'[-–:：]', chinese)]
                latin = re.findall(r'[a-z]+', key)
                chinese_part = re.sub(r'[a-z]+', '', key)
                if key == candidate:
                    grade, score = 3, 100
                elif key in parts:
                    grade, score = 2, 100
                elif (latin and len(chinese_part) >= 3 and chinese_part in parts
                      and all(word in re.findall(r'[a-z]+', english.casefold()) for word in latin)):
                    grade, score = 2, 100
                elif digits and any(len(part) >= 3 and key.startswith(part) and re.findall(r'\d+', part) == digits for part in parts):
                    grade, score = 2, 95
                else:
                    grade, score = 1, ratio(key, candidate)
                    shorter, longer = sorted((key, candidate), key=len)
                    if len(shorter) / len(longer) >= .5 and shorter in longer:
                        score = max(score, 94)
                    if len(key) / len(candidate) >= .5 and len(key) <= len(candidate):
                        chars = iter(candidate)
                        if all(char in chars for char in key):
                            score = max(score, 90)
            group = ranked.setdefault(candidate, {'rank': (grade, score), 'names': [], 'chinese': chinese})
            group['rank'] = max(group['rank'], (grade, score))
            group['names'].append(english)
        best = sorted(ranked.values(), key=lambda g: g['rank'], reverse=True)
        if not best or best[0]['rank'][1] < 85:
            continue
        if len(best) > 1 and best[0]['rank'][0] == best[1]['rank'][0]:
            margin = best[0]['rank'][1] - best[1]['rank'][1]
            if margin < (8 if best[0]['rank'][0] == 1 else 1):
                continue
        english = recommend_source(best[0]['names'])
        row.update(new_label=current if has_chinese(current) else best[0]['chinese'], thumbnail_source=english,
                   chinese_title_sources=best[0]['names'], chinese_title_constraints=sorted(constraints),
                   translation_match_source='title_family', translation_candidates=[], automatic_name_match=True,
                   needs_review=False, match_score=round(best[0]['rank'][1]), match_reason='已按本主机中文名称或别名自动匹配，可单独更换图片')
        diagnostics = row.get('match_diagnostics') or {}
        for evidence in diagnostics.get('evidence_chain', []):
            if evidence.get('source') in {'rom_filename', 'fuzzy_candidate', 'fallback', 'exact_alias'}:
                evidence['resolved_name'] = english
        diagnostics.setdefault('evidence_chain', []).append({'source': 'exact_alias', 'value': query,
            'resolved_name': english, 'note': 'Same-system Chinese title matching; region/revision not verified'})
        row['match_diagnostics'] = build_match_diagnostics(diagnostics, match_source='exact_alias',
            display_label=row['original_label'], new_label=row['new_label'], thumbnail_source=english)
