"""Use the default catalog recommendation without a per-game confirmation gate."""
from rapidfuzz.fuzz import WRatio

from gallery_names import release_tags
from playlist_proposals import has_chinese
from preview_identity import identity_state
from rom_paths import rom_title
from title_family import family_key, recommend_source


def resolve(proposals, translators):
    catalogs = {}
    for row in proposals:
        if identity_state(row)['state'] != 'candidate':
            continue
        system = row['system']
        if system not in catalogs:
            db = translators[system].db
            systems = db.expand_system_mapping(system)
            placeholders = ','.join('?' for _ in systems)
            catalogs[system] = db.get_connection().execute(
                f'SELECT english_name, chinese_name FROM translations WHERE system_base(system) IN ({placeholders})', systems).fetchall()
        query = rom_title(row['path']) or row['original_label']
        constraints = release_tags(query) - {'a', 'b', 'chs', 'cht'}
        records = [r for r in catalogs[system] if constraints <= release_tags(r['english_name'])]
        source = row.get('thumbnail_source')
        existing = [r for r in records if r['english_name'] == source]
        candidates = [name for name in row.get('artwork_candidates', []) if constraints <= release_tags(name)]
        if candidates:
            source = recommend_source(candidates)
            chosen = next((r for r in records if r['english_name'] == source),
                          {'english_name': source, 'chinese_name': row['new_label']})
        elif existing:
            chosen = existing[0]
        elif (source and not has_chinese(source) and any(c.isalpha() for c in source)
              and (source != query or row.get('translation_match_source') != 'fuzzy_candidate')):
            chosen = {'english_name': source, 'chinese_name': row['new_label']}
        elif records:
            def score(record):
                name = record['chinese_name'] if has_chinese(query) else record['english_name']
                return WRatio(family_key(query), family_key(name or record['english_name']))
            best_score = max(score(r) for r in records)
            best = [r for r in records if score(r) == best_score]
            chosen_name = recommend_source([r['english_name'] for r in best])
            chosen = next(r for r in best if r['english_name'] == chosen_name)
            source = chosen['english_name']
        else:
            row.update(default_recommendation=True, needs_review=False, thumbnail_source=None,
                       artwork_query=source or query, artwork_gallery_status='not_found',
                       match_reason='没有可用的本主机推荐图片源，可单独更换')
            continue
        row.update(thumbnail_source=source, default_recommendation=True,
                   needs_review=False, artwork_identity_status='resolved',
                   artwork_identity_reason='default_recommendation', artwork_recommended=True,
                   match_status='download' if row['new_label'] == row.get('original_item_label') else 'matched',
                   match_reason='已采用默认推荐，可单独更换名称或图片；未验证 ROM 版本',
                   chinese_title_sources=[r['english_name'] for r in records
                                          if r['chinese_name'] == chosen['chinese_name'] or r['english_name'] == source],
                   chinese_title_constraints=sorted(constraints))
        if any(term in system for term in ('Arcade', 'FBNeo', 'MAME')):
            # Chinese catalog synonyms can belong to different arcade games.
            # The ZIP/DAT title owns the image family, not its translated label.
            row['chinese_title_sources'] = [source]
