"""Rank catalog title families, keeping runner-up and sequel evidence explicit."""
import re
from pathlib import PurePosixPath

from rapidfuzz.fuzz import ratio

from artwork_identity import base_title
from gallery_names import release_tags
from rom_paths import rom_title
from title_family import family_key, keep_disc_marker


def search_title(value):
    # A translation patch version describes the patch, not a retail revision.
    if re.search(r'\((?:CHS|CHT|CN)\)|\[T[+-]', value, re.I):
        value = re.sub(r'\(v\d+(?:\.\d+)*\)', '', value, flags=re.I)
    return value


def numbers(title):
    roman = {'I': '1', 'II': '2', 'III': '3', 'IV': '4', 'V': '5', 'VI': '6', 'VII': '7', 'VIII': '8', 'IX': '9', 'X': '10'}
    return re.findall(r'\d+', title) + [roman[t] for t in re.findall(r'\b[IVX]+\b', title) if t in roman]


def resolve(proposals, translators):
    catalogs = {}
    for row in proposals:
        system = row['system']
        if (row.get('translation_match_source') != 'fuzzy_candidate' and row.get('match_source') != 'playlist') or row.get('match_diagnostics', {}).get('conflicts'):
            continue
        if any(term in system for term in ('Arcade', 'FBNeo', 'MAME', 'DOS')):
            continue
        if system == 'Sega - Saturn' and row.get('artwork_identity_reason') not in {'filename', 'unknown'}:
            continue
        if system not in catalogs:
            db = translators[system].db
            systems = db.expand_system_mapping(system)
            placeholders = ','.join('?' for _ in systems)
            catalogs[system] = db.get_connection().execute(
                f'SELECT english_name, chinese_name FROM translations WHERE system_base(system) IN ({placeholders})', systems).fetchall()
        query = search_title(rom_title(row['path']))
        key = family_key(query)
        if not key or len(key) < 4:
            continue
        # Unknown edition/hack tags are not spelling mistakes to be erased.
        if any(family_key('(' + (a or b) + ')') for a, b in re.findall(r'\(([^()]*)\)|\[([^\[\]]*)\]', query)):
            continue
        parent = PurePosixPath(str(row['path']).replace('\\', '/')).parent.name
        parent_title = re.split(r'\s+[-–]\s+', parent)[0]
        ranked = {}
        constraints = release_tags(query) - {'a', 'b', 'chs', 'cht'}
        for record in catalogs[system]:
            english, chinese = record['english_name'], record['chinese_name']
            if not chinese or not constraints <= release_tags(english):
                continue
            title = base_title(english)
            aliases = [title] + [tag for tag in re.findall(r'\(([^()]*)\)', english)
                                 if len(tag.split()) >= 3 and not re.search(r'edition|version|demo|prototype|hack', tag, re.I)]
            score = max((ratio(key, family_key(alias)) for alias in aliases
                         if numbers(base_title(query)) == numbers(alias)), default=0)
            # Short ROM aliases need independent, precise Chinese folder evidence.
            corroborated = (family_key(parent_title) == family_key(chinese) and len(key) <= 12
                            and key[:4] == family_key(title)[:4] and numbers(base_title(query)) == numbers(title))
            if corroborated:
                score = max(score, 99)
            group = family_key(title)
            if group not in ranked or score > ranked[group][0]:
                ranked[group] = (score, english, chinese)
        best = sorted(ranked.values(), reverse=True)
        if not best or best[0][0] < 90 or (len(best) > 1 and best[0][0] - best[1][0] < 8):
            continue
        score, english, chinese = best[0]
        current = row.get('original_item_label') or ''
        if re.search(r'[\u3400-\u9fff]', current) and family_key(current) != family_key(chinese):
            continue
        row.update(new_label=keep_disc_marker(chinese, rom_title(row['path'])), thumbnail_source=english,
                   translation_match_source='title_family', translation_candidates=[], automatic_name_match=True,
                   needs_review=False, match_score=round(score), match_reason='名称候选唯一且显著优于其他游戏，已自动匹配')
        row['name_match_ranking'] = {'score': round(score, 2), 'runner_up_score': round(best[1][0], 2) if len(best) > 1 else 0}
        for evidence in row.get('match_diagnostics', {}).get('evidence_chain', []):
            if evidence.get('source') in {'rom_filename', 'fuzzy_candidate', 'exact_alias'}:
                evidence['resolved_name'] = english
        from match_evidence import build_match_diagnostics
        row['match_diagnostics'] = build_match_diagnostics(row.get('match_diagnostics'),
            match_source=row['match_source'], display_label=row['original_label'],
            new_label=row['new_label'], thumbnail_source=english)
