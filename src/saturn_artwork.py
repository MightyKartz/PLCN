"""Resolve Saturn title families without guessing a region, revision or disc."""
from pathlib import PurePosixPath
import re

from artwork_identity import resolve, base_title
from gallery_names import release_candidates, matching_gallery_name
from rom_paths import rom_title, DISC_MARKER
from playlist_proposals import classify_match
from match_evidence import build_match_diagnostics


def distinct_disc_label(label, path, items):
    title = rom_title(path)
    disc = DISC_MARKER.search(title)
    if not disc or DISC_MARKER.search(label):
        return label
    family = DISC_MARKER.sub('', title).strip().casefold()
    parent = str(PurePosixPath(str(path).replace('\\', '/')).parent)
    for item in items:
        other = str(item.get('path') or '').replace('\\', '/')
        other_title = rom_title(other)
        other_disc = DISC_MARKER.search(other_title)
        if (other_disc and (other_disc[1] or other_disc[2]) != (disc[1] or disc[2]) and str(PurePosixPath(other).parent) == parent
                and DISC_MARKER.sub('', other_title).strip().casefold() == family):
            return label + ' (Disc ' + (disc[1] or disc[2]) + ')'
    return label


def resolve_proposals(proposals, translators, playlist_path, verify_artwork, thumbnails=None):
    from single_artwork import catalog_names
    catalogs = {}
    from playlist_browser import open_artwork_reader, artwork_statuses
    reader, lookups, image_error = open_artwork_reader(thumbnails, 'Sega - Saturn')
    for proposal in proposals:
        if proposal['system'] != 'Sega - Saturn':
            continue
        translator = translators['Sega - Saturn']
        db = translator.db
        if proposal['match_source'] != 'manual_override' and translator.normalize_name(rom_title(proposal['path'])) == 'chaosseed':
            translated, _ = translator.translate(rom_title(proposal['path']))
            if translator.last_match_source == 'curated_alias':
                proposal['new_label'] = translated

        context = {'system': proposal['system'], 'label': proposal['original_item_label'],
                   'rom_path': proposal['path'], 'playlist_path': playlist_path, 'kind': 'Named_Boxarts'}
        if proposal['match_source'] == 'manual_override':
            identity = {'names': [proposal['thumbnail_source']] if proposal['thumbnail_source'] else [], 'reason': 'confirmed', 'query': proposal['thumbnail_source'] or ''}
        else:
            identity = resolve(context, database=db)
        names = identity['names'] if identity['reason'] in {'confirmed', 'remembered'} else release_candidates(rom_title(proposal['path']), identity['names'])
        proposal['artwork_identity_reason'] = identity['reason']
        proposal['artwork_query'] = identity['query'] or base_title(proposal['new_label'])
        proposal['artwork_candidates'] = names
        proposal['artwork_identity_status'] = 'resolved' if names else 'unresolved'
        selected = names[0] if len(names) == 1 else None
        if selected and not re.search(r'[\u3400-\u9fff]', proposal['new_label']):
            chinese = db.search_by_english(selected, system=proposal['system'])
            if chinese:
                proposal['new_label'] = chinese
        if identity['reason'] == 'parent_title':
            selected = None
        # Explicit source choices already identify their release. For inferred
        # titles, keep all versions until one is supported by the input.
        if verify_artwork and names:
            availability = {}
            for kind in ('Named_Boxarts', 'Named_Snaps', 'Named_Titles'):
                if kind not in catalogs:
                    try:
                        catalogs[kind] = catalog_names(proposal['system'], kind)
                    except (OSError, ValueError, RuntimeError) as error:
                        catalogs[kind] = error
                catalog = catalogs[kind]
                if isinstance(catalog, Exception):
                    availability[kind] = {'status': 'unavailable', 'message': str(catalog)}
                else:
                    matches = list(dict.fromkeys(match for name in names
                        if (match := matching_gallery_name(proposal['system'], name, catalog))))
                    availability[kind] = {'status': 'available' if matches else 'not_found', 'names': matches}
            proposal['artwork_availability'] = availability
            boxart = availability['Named_Boxarts']
            if boxart['status'] == 'available':
                proposal['artwork_candidates'] = boxart['names']
            if boxart['status'] != 'available':
                selected = None
                proposal['artwork_gallery_status'] = boxart['status']
            elif selected:
                selected = matching_gallery_name(proposal['system'], selected, catalogs['Named_Boxarts'])
                proposal['artwork_gallery_status'] = 'matched'
            else:
                proposal['artwork_gallery_status'] = 'ambiguous'
        if selected:
            proposal['thumbnail_source'] = selected
            proposal['artwork_query'] = selected
            proposal['artwork'] = artwork_statuses(proposal['new_label'], proposal['path'], reader, lookups, thumbnails or '', proposal['system'])
            boxart = proposal['artwork']['Named_Boxarts']
            proposal['cover_exists'] = proposal['thumbnail_exists'] = proposal['local_thumbnail_exists'] = boxart['status'] == 'exists'
            proposal['cover_path'] = boxart['path']
            from playlist_artwork import cover_preview_url
            proposal['cover_preview_url'] = cover_preview_url(boxart['path'])
            evidence = [entry for entry in proposal.get('match_diagnostics', {}).get('evidence_chain', [])
                        if entry['source'] in {'playlist_crc32', 'local_zip_crc', 'manual_override'}]
            proposal['match_diagnostics'] = build_match_diagnostics({'evidence_chain': evidence},
                match_source='manual_override' if identity['reason'] in {'confirmed', 'remembered'} else 'fuzzy_candidate' if evidence else 'exact_alias',
                display_label=proposal['original_label'], new_label=proposal['new_label'], thumbnail_source=selected)
            match = classify_match(proposal['original_label'], proposal['new_label'], selected,
                                   current_label=proposal['original_item_label'], cover_exists=proposal['cover_exists'])
            proposal.update(match_status=match.match_status, match_score=match.match_score, needs_review=match.needs_review)
            proposal['match_reason'] = '已按当前游戏身份匹配标准图片源'
            if any(image['status'] != 'exists' for image in proposal['artwork'].values()):
                if proposal['match_status'] == 'ready': proposal['match_status'] = 'download'
                elif proposal['match_status'] == 'rename': proposal['match_status'] = 'matched'
            if proposal['match_diagnostics']['conflicts']:
                proposal.update(match_status='review', needs_review=True, match_reason='游戏身份与校验值证据冲突，请核对')
            if image_error:
                proposal['match_reason'] += '；设备图片读取失败：' + image_error
        elif names or verify_artwork:
            proposal['thumbnail_source'] = None
            proposal['artwork_review_only'] = not proposal.get('needs_review')
            proposal.update(match_status='review', needs_review=True)
            status = proposal.get('artwork_gallery_status', 'ambiguous' if names else 'unresolved')
            reasons = {'ambiguous': '已识别游戏，存在多个地区或修订，请选择图片版本',
                       'not_found': '当前图片源未匹配到官方封面，请核对标准名称与盘号',
                       'unavailable': '官方图库查询失败，请重试',
                       'unresolved': '名称未识别，请搜索图库或导入图片'}
            proposal['match_reason'] = ('依据父目录找到候选，请核对后选择图片源'
                if identity['reason'] == 'parent_title' else reasons[status])
