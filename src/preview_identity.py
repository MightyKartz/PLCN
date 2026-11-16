"""Project matching evidence without confusing local UUIDs with ROM identity."""
from match_evidence import normalize_source


def identity_state(change):
    diagnostics = change.get('match_diagnostics') or {}
    source = normalize_source(change.get('match_source'))
    translation = change.get('translation_match_source')
    evidence = diagnostics.get('evidence_chain') or []
    if diagnostics.get('conflicts'):
        state = 'conflict'
    elif source == 'manual_override':
        state = 'confirmed_rule'
    elif (translation in {'fuzzy_candidate', 'cross_system_candidate'} or change.get('translation_candidates')
          or change.get('artwork_identity_reason') == 'parent_title' or change.get('artwork_identity_status') == 'ambiguous'):
        state = 'candidate'
    elif any(item.get('source') in {'playlist_crc32', 'local_zip_crc'} and item.get('resolved_name') for item in evidence):
        state = 'checksum_match'
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
            'evidence': evidence, 'conflicts': diagnostics.get('conflicts') or [],
            'release_verified': False}
