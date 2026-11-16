"""Project matching evidence without confusing local UUIDs with ROM identity."""
from match_evidence import normalize_source
from rom_paths import DISC_MARKER, rom_title
import re


def identity_state(change):
    diagnostics = change.get('match_diagnostics') or {}
    source = normalize_source(change.get('match_source'))
    translation = change.get('translation_match_source')
    evidence = diagnostics.get('evidence_chain') or []
    conflicts = list(diagnostics.get('conflicts') or [])
    titles = [change.get('original_item_label') or '', rom_title(change.get('path')), change.get('thumbnail_source') or '']
    discs = {int(m[1] or m[2]) for title in titles if (m := DISC_MARKER.search(title))}
    sides = {m[1].upper() for title in titles if (m := re.search(r'[（(]([AB])[）)]', title, re.I))}
    if source != 'manual_override' and (len(discs) > 1 or len(sides) > 1):
        conflicts.append({'reason': '列表与文件的盘号或 A/B 标记不一致'})
    if conflicts:
        state = 'conflict'
    elif source == 'manual_override':
        state = 'confirmed_rule'
    elif (translation in {'fuzzy_candidate', 'cross_system_candidate'} or change.get('translation_candidates')
          or change.get('artwork_identity_reason') == 'parent_title' or change.get('artwork_identity_status') == 'ambiguous'):
        state = 'candidate'
    elif any(item.get('source') in {'playlist_crc32', 'local_zip_crc'} and item.get('resolved_name') for item in evidence):
        state = 'checksum_match'
    elif translation == 'title_family':
        state = 'title_family'
    elif source == 'libretro_dat':
        state = 'database_title'
    elif translation in {'exact', 'exact_alias', 'curated_alias'} or source == 'exact_alias':
        state = 'exact_title'
    elif change.get('artwork_identity_status') == 'resolved':
        state = 'title_family'
    elif change.get('thumbnail_source'):
        state = 'candidate'
    else:
        state = 'unresolved'
    return {'state': state, 'requires_review': state in {'candidate', 'conflict', 'unresolved'},
            'source': change.get('match_source') or 'fallback', 'translation_source': translation,
            'evidence': evidence, 'conflicts': conflicts,
            'release_verified': False}
