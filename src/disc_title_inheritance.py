"""Reuse a confirmed title for other discs in the same playlist directory."""
from pathlib import PurePosixPath

from display_names import base_display_title
from gallery_names import release_tags
from match_evidence import build_match_diagnostics
from playlist_proposals import has_chinese
from rom_paths import DISC_MARKER, rom_title
from title_family import family_key


def inherit_confirmed_titles(proposals):
    groups = {}
    for row in proposals:
        title = rom_title(row['path'])
        if not DISC_MARKER.search(title):
            continue
        key = (row['system'], str(PurePosixPath(row['path'].replace('\\', '/')).parent),
               family_key(title), tuple(sorted(t for t in release_tags(title) if not t.startswith('disc '))))
        groups.setdefault(key, []).append(row)
    for group in groups.values():
        confirmed = []
        for row in group:
            image_disc = DISC_MARKER.search(row.get('thumbnail_source') or '')
            file_disc = DISC_MARKER.search(rom_title(row['path']))
            if ((row['match_source'] == 'manual_override' or row.get('translation_match_source') in {'exact', 'exact_alias', 'curated_alias', 'title_family'})
                    and not row.get('needs_review') and not row.get('match_diagnostics', {}).get('conflicts')
                    and has_chinese(row['new_label']) and image_disc
                    and int(image_disc[1] or image_disc[2]) == int(file_disc[1] or file_disc[2])):
                confirmed.append(row)
        if not confirmed or len({base_display_title(r['new_label']) for r in confirmed}) != 1:
            continue
        source = confirmed[0]
        if not DISC_MARKER.search(source['thumbnail_source']):
            continue
        for row in group:
            disc = DISC_MARKER.search(rom_title(row['path']))
            image_disc = DISC_MARKER.search(row.get('thumbnail_source') or '')
            wrong_disc_alias = image_disc and int(image_disc[1] or image_disc[2]) != int(disc[1] or disc[2])
            diagnostics = row.get('match_diagnostics') or {}
            checksum_evidence = any(e.get('source') in {'playlist_crc32', 'local_zip_crc'} and e.get('resolved_name')
                                    for e in diagnostics.get('evidence_chain', []))
            if (row in confirmed or checksum_evidence or (diagnostics.get('conflicts') and not wrong_disc_alias)
                    or row.get('match_source') not in {'fallback', 'rom-name-cn', 'playlist', 'libretro-dat'}
                    or (row.get('translation_match_source') not in {'', 'fallback', 'fuzzy_candidate'} and not wrong_disc_alias)):
                continue
            current = row.get('original_item_label') or ''
            if has_chinese(current) and family_key(base_display_title(current)) != family_key(base_display_title(source['new_label'])):
                continue
            number = str(int(disc[1] or disc[2]))
            english = DISC_MARKER.sub('(Disc ' + number + ')', source['thumbnail_source'])
            row.update(new_label=base_display_title(source['new_label']) + ' (Disc ' + number + ')',
                       thumbnail_source=english, match_source='confirmed_sibling_title', translation_match_source='title_family',
                       translation_candidates=[], automatic_name_match=True, needs_review=False,
                       match_reason='复用同目录同一游戏已确认的名称，保留本盘盘号')
            diagnostics = row.get('match_diagnostics') or {}
            for evidence in diagnostics.get('evidence_chain', []):
                if evidence.get('source') in {'rom_filename', 'fuzzy_candidate', 'fallback', 'exact_alias'}:
                    evidence['resolved_name'] = english
            diagnostics.setdefault('evidence_chain', []).append({'source': 'exact_alias', 'value': source['proposal_id'],
                'resolved_name': english, 'note': 'Title inherited from a confirmed sibling disc; checksum and core are not inherited'})
            row['match_diagnostics'] = build_match_diagnostics(diagnostics, match_source='exact_alias',
                display_label=row['original_label'], new_label=row['new_label'], thumbnail_source=english)
