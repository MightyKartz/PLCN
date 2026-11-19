"""Analyze playlist entries and produce repair proposals without writing playlists."""
import os
import re
from playlist_manager import PlaylistManager
from translator import Translator
from rom_fingerprint import build_rom_match_candidates
from rom_paths import disc_group, preferred_disc_entry, rom_filename, rom_title, DISC_MARKER
from manual_overrides import find_override, load_overrides
from system_resources import is_system_resource
from artwork_resolver import ArtworkResolver, sanitize_filename, validate_system
from playlist_proposals import (
    has_chinese,
    normalize_value,
    build_change_proposal,
)
from playlist_artwork import (
    build_existing_boxart_lookup,
    find_existing_boxart,
)


def is_generic_collection_label(text):
    if not has_chinese(text):
        return False

    compact = re.sub(r'[\s_\-·./\\]+', '', (text or '').casefold())
    if not compact:
        return False

    exact_generic_names = {
        "中文游戏",
        "汉化游戏",
        "游戏合集",
        "游戏目录",
        "游戏列表",
        "游戏",
    }
    if compact in exact_generic_names:
        return True

    if any(phrase in compact for phrase in ("中文游戏", "汉化游戏", "游戏合集", "游戏目录", "游戏列表")):
        return True

    platform_aliases = {
        "gba", "gb", "gbc", "nds", "nes", "fc", "sfc", "snes", "md",
        "n64", "ps", "ps1", "psx", "pce", "msx", "wii", "dc", "ss",
    }
    generic_suffixes = {"中文", "游戏", "中文游戏", "汉化", "汉化游戏"}
    return any(compact == f"{alias}{suffix}" for alias in platform_aliases for suffix in generic_suffixes)


def add_unique_candidate(candidates, value, source):
    value = (value or '').strip()
    if not value:
        return
    key = value.casefold()
    if key in {candidate.casefold() for candidate, _ in candidates}:
        return
    candidates.append((value, source))


def get_rom_path_candidates(path):
    candidates = []
    if not path:
        return candidates
    basename = os.path.basename(path)
    if '#' in basename:
        basename = basename.split('#')[0]
    if not basename:
        return candidates
    stem = os.path.splitext(basename)[0]
    add_unique_candidate(candidates, stem, "rom")
    add_unique_candidate(candidates, basename, "rom")
    return candidates


def disc_sibling_key(path):
    if not path:
        return None, None
    clean_path = normalize_value(str(path)).split('#')[0].replace('\\', '/')
    dirname, basename = clean_path.rsplit('/', 1) if '/' in clean_path else ('', clean_path)
    stem, ext = os.path.splitext(basename)
    if not stem:
        return None, None
    return f"{dirname}/{stem}".casefold(), ext.casefold()


def has_disc_descriptor_siblings(items):
    descriptor_exts = {'.cue'}
    media_exts = {'.bin', '.img'}
    path_grouped_exts = {}
    label_grouped_exts = {}

    for item in items or []:
        key, ext = disc_sibling_key(item.get('path'))
        if not ext:
            continue

        if key:
            path_grouped_exts.setdefault(key, set()).add(ext)

        label = normalize_value(item.get('label')).casefold()
        if label:
            label_grouped_exts.setdefault(label, set()).add(ext)

    groups = list(path_grouped_exts.values()) + list(label_grouped_exts.values())

    return any(
        exts & descriptor_exts and exts & media_exts
        for exts in groups
    )


def analyze_playlist(playlist_path, system_name, rom_name_cn_path, thumbnails_dir=None, manual_overrides_path=None, verify_artwork=False, source_playlist_path=None):
    """
    Analyzes the playlist and returns a list of proposed changes.
    Returns:
        list of dicts: {
            'index': int,
            'original_label': str,
            'path': str,
            'new_label': str,
            'thumbnail_source': str (Standard English Name or None),
            'system': str
        }
    """

    # Clean FBNeo/Arcade game names
    def clean_arcade_name(game_name):
        """
        Cleans arcade game names by removing region codes, version info, and dates.
        Examples:
          "1941: Counter Attack (World 900227)" -> "1941: Counter Attack"
          "Street Fighter II' - Champion Edition (USA 920313)" -> "Street Fighter II' - Champion Edition"
        """
        import re
        # Remove region and date codes like (World 900227), (USA 920313), (Japan), etc.
        cleaned = re.sub(r'\s*\([^)]*\d{6}[^)]*\)$', '', game_name)  # Remove (Region YYMMDD)
        cleaned = re.sub(r'\s*\([^)]*\)$', '', cleaned)  # Remove remaining (Region) or (version)
        return cleaned.strip()

    # Normalize system name (remove timestamp and number suffixes)
    # e.g., "Nintendo - SNES (20240830-122750) (3308)" -> "Nintendo - SNES"
    def normalize_system_name(system_name):
        import re
        # Remove patterns like (YYYYMMDD-HHMMSS) and (number)
        normalized = re.sub(r'\s*\(\d{8}-\d{6}\)\s*', '', system_name)
        normalized = re.sub(r'\s*\(\d+\)\s*$', '', normalized)
        return normalized.strip()

    normalized_system = normalize_system_name(system_name)
    print(f"System: {system_name}")
    if normalized_system != system_name:
        print(f"Normalized to: {normalized_system} (for database matching)")

    # Initialize components
    playlist_manager = PlaylistManager(playlist_path)
    playlist_system = system_name
    translators = {}
    artwork_resolvers = {}
    lookups = {}
    translator = None
    artwork_resolver = None

    # Preserve every row and its original index. Renaming never implies deletion.

    items = playlist_manager.get_items()
    preferred_disc = preferred_disc_entry(items)
    proposed_changes = []
    boxart_lookup = None
    manual_overrides = load_overrides(manual_overrides_path) if manual_overrides_path else []

    def add_proposal(index, item, display_label, new_label, thumbnail_source, match_source, match_reason, match_diagnostics=None):
        if match_source != 'manual_override':
            from title_family import keep_disc_marker
            new_label = keep_disc_marker(new_label, rom_title(item.get('path')))
        if system_name == 'Sega - Saturn':
            from saturn_artwork import distinct_disc_label
            new_label = distinct_disc_label(new_label, item.get('path'), items)
        cover_exists, cover_path = find_existing_boxart(
            thumbnails_dir,
            system_name,
            rom_title(item.get('path')),
            new_label,
            (item.get('label') or '') if '(Disc ' not in new_label else '',
            lookup=boxart_lookup,
        )
        artwork = None
        if artwork_resolver:
            artwork = artwork_resolver.resolve_all(new_label, source=thumbnail_source, rom_path=item.get('path'))
            boxart = artwork['Named_Boxarts']
            cover_exists = boxart['status'] == 'exists'
            cover_path = boxart['path']
        proposal = build_change_proposal(
            index=index,
            item=item,
            display_label=display_label,
            new_label=new_label,
            thumbnail_source=thumbnail_source,
            system_name=system_name,
            match_source=match_source,
            match_reason=match_reason,
            match_diagnostics=match_diagnostics,
            cover_exists=cover_exists,
            cover_path=cover_path,
        )
        if match_source == "manual_override":
            proposal["needs_review"] = False
            proposal["match_score"] = 100
            if proposal["match_status"] == "review":
                proposal["match_status"] = "matched"
        elif getattr(translator, 'last_match_source', '') in {'fuzzy_candidate', 'cross_system_candidate'}:
            proposal['match_status'] = 'review'
            proposal['needs_review'] = True
            proposal['match_score'] = min(proposal['match_score'], 72)
            proposal['match_reason'] += '；中文译名来自模糊或跨系统候选，需要人工确认'
            proposal['translation_candidates'] = getattr(translator, 'last_translation_candidates', [])
        proposal['translation_match_source'] = getattr(translator, 'last_match_source', '')
        if artwork:
            proposal['artwork'] = artwork
            if proposal['match_status'] == 'ready' and any(value['status'] != 'exists' for value in artwork.values()):
                proposal['match_status'] = 'download'
                proposal['match_reason'] = '名称已就绪，仍有图片需要补齐'
        proposed_changes.append(proposal)

    def build_rom_match_diagnostics(rom_matches, dat_result, matched_candidate=None, matched_source=None):
        return {
            "candidate_count": len(rom_matches.candidates),
            "candidates": [
                {"value": candidate, "source": source}
                for candidate, source in rom_matches.candidates
            ],
            "candidate_sources": sorted({source for _, source in rom_matches.candidates}),
            "fingerprint_status": rom_matches.fingerprint_status,
            "fingerprint_error": rom_matches.fingerprint_error,
            "dat_result": dat_result,
            "matched_candidate": matched_candidate,
            "matched_candidate_source": matched_source,
        }

    def fbneo_fallback_reason(rom_matches):
        if rom_matches.fingerprint_status == "readable":
            return "本地 DAT 未命中：已读取 ROM 指纹，但没有匹配到标准名，需要确认封面源"
        if rom_matches.fingerprint_status == "unreadable":
            return "本地 DAT 未命中：ROM 文件读取失败，仅使用路径和游戏列表名称生成建议"
        return "本地 DAT 未命中：ROM 文件不可直接读取，仅使用路径和游戏列表名称生成建议"

    def translate_arcade_label_candidate(candidate):
        if not candidate:
            return None, None

        chinese = translator.db.search_by_english(candidate, system=translator.system_name)
        if chinese:
            return chinese, candidate

        normalized = translator.normalize_name(candidate)
        chinese, english = translator.db.search_by_normalized_alias(normalized, system=translator.system_name)
        if chinese and english:
            translator.last_match_source = 'exact_alias'
            return chinese, english

        if translator.libretro_db:
            standard_name = translator.libretro_db.get_standard_name(candidate)
            if standard_name:
                chinese = translator.db.search_by_english(standard_name, system=translator.system_name)
                return chinese or standard_name, standard_name

        return None, None

    def is_chinese_text(value):
        return any('\u4e00' <= char <= '\u9fff' for char in (value or ''))

    def filename_stem_from_path(value):
        return rom_title(value) or None

    def filename_from_path(value):
        return rom_filename(value) or None

    def evidence_system_hint(value):
        if "Super Nintendo" in (value or ""):
            return "SNES"
        if "Genesis" in (value or ""):
            return "Genesis"
        return value

    def looks_nonstandard_name(value):
        compact = (value or "").casefold()
        return any(term in compact for term in ("hack", "collection", "prototype", "homebrew"))

    def is_system_folder_name(folder, system):
        compact_folder = re.sub(r"[^a-z0-9]+", "", (folder or "").casefold())
        compact_system = re.sub(r"[^a-z0-9]+", "", (system or "").casefold())
        system_aliases = {
            "gba": "nintendogameboyadvance",
            "snes": "nintendosupernintendoentertainmentsystem",
            "sfc": "nintendosupernintendoentertainmentsystem",
            "genesis": "segamegadrivegenesis",
            "megadrive": "segamegadrivegenesis",
            "ps": "sonyplaystation",
            "ps1": "sonyplaystation",
            "dc": "segadreamcast",
            "dreamcast": "segadreamcast",
        }
        return bool(
            compact_folder
            and (
                compact_folder in compact_system
                or system_aliases.get(compact_folder) == compact_system
            )
        )

    def resolve_exact_english_source(candidate):
        if not candidate or is_chinese_text(candidate):
            return None

        candidate = os.path.splitext(str(candidate).strip())[0] if "." in str(candidate) else str(candidate).strip()
        if not candidate:
            return None

        if translator.db.search_by_english(candidate, system=translator.system_name):
            return candidate

        normalized = translator.normalize_name(candidate)
        chinese, english = translator.db.search_by_normalized_alias(normalized, system=translator.system_name)
        if chinese and english:
            return english

        if translator.libretro_db:
            standard_name = translator.libretro_db.get_standard_name(candidate)
            if standard_name:
                return standard_name

        if translator.resolve_title_family(candidate):
            translator.last_match_source = 'title_family'
            return candidate

        return None

    def resolve_thumbnail_source_for_chinese_label(chinese_label, path, display_label, original_label):
        # Arcade ZIP identifiers remain useful after the label has been translated.
        # A shared Chinese label must not override the ROM's DAT title.
        if any(term in translator.system_name for term in ('Arcade', 'FBNeo', 'MAME')):
            source = find_exact_rom_source(path)
            if source:
                return source, "rom_filename"
        exact_chinese_source = translator.db.search_by_chinese(chinese_label, system=translator.system_name)
        if exact_chinese_source:
            return exact_chinese_source, "exact_alias"

        english_candidates = []
        add_unique_candidate(english_candidates, filename_stem_from_path(path), "filename")
        add_unique_candidate(english_candidates, display_label, "display")
        add_unique_candidate(english_candidates, original_label, "playlist")

        for candidate, _ in english_candidates:
            source = resolve_exact_english_source(candidate)
            if source:
                return source, "rom_filename"

        for candidate, _ in english_candidates:
            if candidate and not is_chinese_text(candidate):
                return candidate, "fallback"

        return chinese_label, "fallback"

    def find_exact_rom_source(path):
        arcade = any(term in translator.system_name for term in ('Arcade', 'FBNeo', 'MAME'))
        for candidate, _ in get_rom_path_candidates(path):
            if arcade:
                names = translator.libretro_db.rom_names.get(candidate.casefold(), []) if translator.libretro_db else []
                source = names[0] if len(names) == 1 else None
            else:
                source = resolve_exact_english_source(candidate)
            if source:
                return source
        if arcade:
            # Older FBNeo DATs omit some short identifiers that the MAME
            # catalog still maps exactly. Never fuzzy-match a ZIP identifier.
            chinese, source = translator.db.search_by_normalized_alias(
                translator.normalize_name(rom_title(path)), system='MAME')
            if chinese and source:
                return source
        return None

    def add_manual_override_proposal(index, item, display_label, override):
        new_label = override.get("new_label") or item.get("label")
        thumbnail_source = override.get("thumbnail_source")
        exact_source = find_exact_rom_source(item.get("path"))
        conflict = bool(
            exact_source
            and thumbnail_source
            and normalize_value(exact_source).casefold() != normalize_value(thumbnail_source).casefold()
        )
        diagnostics = {
            "override_updated_at": override.get("updated_at"),
            "exact_rom_source": exact_source,
        }

        if conflict:
            diagnostics["conflicting_thumbnail_source"] = thumbnail_source
            match_reason = f"manual override conflict with exact ROM source: {exact_source}"
        else:
            match_reason = "本地人工覆盖记录命中"

        add_proposal(
            index,
            item,
            display_label,
            new_label,
            thumbnail_source,
            "manual_override",
            match_reason,
            diagnostics,
        )

        proposal = proposed_changes[-1]
        if conflict:
            proposal["match_status"] = "review"
            proposal["match_score"] = 80
            proposal["needs_review"] = True
        else:
            proposal["match_score"] = 100
            proposal["needs_review"] = False

    dos_gallery = {}
    for i, item in enumerate(items):
        if is_system_resource(item, playlist_system):
            continue
        disc_key = disc_group(path := item.get('path'), item.get('label'), [entry.get('path') for entry in items])
        if disc_key and disc_key in preferred_disc and preferred_disc[disc_key] != i:
            continue
        db_name = str(item.get('db_name') or '').replace('\\', '/').rsplit('/', 1)[-1]
        system_name = os.path.splitext(db_name)[0] if db_name and db_name != 'DETECT' else playlist_system
        validate_system(system_name)
        normalized_system = normalize_system_name(system_name)
        if normalized_system not in translators:
            translators[normalized_system] = Translator(rom_name_cn_path, normalized_system)
        translator = translators[normalized_system]
        translator.last_match_source = ''
        translator.last_translation_candidates = []
        if system_name not in lookups:
            lookups[system_name] = build_existing_boxart_lookup(thumbnails_dir, system_name)
            if thumbnails_dir and not str(thumbnails_dir).startswith(('adb://', 'mtp://')):
                artwork_resolvers[system_name] = ArtworkResolver(thumbnails_dir, system_name)
        boxart_lookup = lookups[system_name]
        artwork_resolver = artwork_resolvers.get(system_name)
        original_label = item.get('label')
        path = item.get('path')

        # Extract ROM name for display (filename without extension)
        display_label = original_label
        if path:
            display_label = rom_title(path)

        new_label = original_label
        thumbnail_source = None

        manual_override = find_override(manual_overrides, system_name, item)
        if manual_override:
            add_manual_override_proposal(i, item, display_label, manual_override)
            continue

        if normalized_system == 'DOS':
            from artwork_identity import resolve as resolve_artwork_identity
            from gallery_names import matching_artwork_name
            from single_artwork import catalog_names
            identity = resolve_artwork_identity({'system': 'DOS', 'label': original_label or '',
                                                 'rom_path': path, 'playlist_path': str(playlist_path),
                                                 'kind': 'Named_Boxarts'}, name_source=rom_name_cn_path)
            source = None
            gallery_status = 'unknown'
            reason = '名称未识别：请搜索图库或导入本地图片'
            if identity['status'] == 'resolved':
                # Check once per preview, including failures. An English search
                # alias alone must not enqueue a batch of predictable 404s.
                if not dos_gallery:
                    try:
                        dos_gallery['names'] = catalog_names('DOS', 'Named_Boxarts')
                    except (OSError, ValueError, RuntimeError) as error:
                        dos_gallery['error'] = str(error)
                if 'error' in dos_gallery:
                    gallery_status = 'unavailable'
                    reason = '名称已识别，但图库查询失败；请重试搜索或导入本地图片'
                else:
                    source = matching_artwork_name('DOS', identity['query'], dos_gallery['names'])
                    gallery_status = 'matched' if source else 'not_found'
                    reason = '已找到官方 DOS 封面' if source else '名称已识别，官方 DOS 图库未找到匹配封面；可搜索其他名称或导入本地图片'
            add_proposal(i, item, original_label or display_label, original_label or display_label,
                         source, 'dos_title', reason, {'evidence_chain': [{
                             # The full title is a search alias, not a DAT/CRC
                             # match. Do not invent conflicting ROM evidence
                             # from the archive filename when no cover exists.
                             'source': 'exact_alias' if identity['reason'] == 'curated' else 'fallback',
                             'value': original_label or display_label,
                             'resolved_name': identity['query'] or original_label or display_label,
                         }]})
            proposed_changes[-1]['artwork_identity_reason'] = identity['reason']
            proposed_changes[-1]['artwork_identity_status'] = identity['status']
            proposed_changes[-1]['artwork_query'] = identity['query']
            proposed_changes[-1]['artwork_gallery_status'] = gallery_status
            continue

        # Special handling for FBNeo/Arcade games
        # These games have region codes like "(World 900227)" that need to be removed
        is_arcade = 'Arcade' in normalized_system or 'FBNeo' in normalized_system or normalized_system == 'MAME'

        if is_arcade and original_label and not any('\u4e00' <= char <= '\u9fff' for char in original_label):
            # Clean the arcade name (remove region codes and dates)
            cleaned_name = clean_arcade_name(original_label)
            print(f"  [{i}] Arcade game detected: '{original_label}' -> '{cleaned_name}'")

            rom_matches = build_rom_match_candidates(path, item.get('crc32'))
            matched_candidate = None
            matched_source = None
            standard_english_name = None

            if translator.libretro_db:
                for candidate, candidate_source in rom_matches.candidates:
                    standard_name = translator.libretro_db.get_standard_name(candidate)
                    if standard_name:
                        matched_candidate = candidate
                        matched_source = candidate_source
                        standard_english_name = standard_name
                        break

            if standard_english_name:
                # An exact zip-stem alias identifies the romset precisely; title
                # lookups can silently collapse releases whose names differ only
                # inside stripped parentheses (e.g. kov vs kov114).
                translated_cn, _ = translate_arcade_label_candidate(matched_candidate)
                if not has_chinese(translated_cn):
                    translated_cn, _ = translator.translate(standard_english_name)
                new_label = translated_cn if has_chinese(translated_cn) else standard_english_name
                thumbnail_source = standard_english_name
                print(f"  [{i}] Libretro DAT ROM match: '{matched_candidate}' -> '{standard_english_name}'")
                add_proposal(
                    i,
                    item,
                    display_label,
                    new_label,
                    thumbnail_source,
                    "libretro-dat-rom",
                    "ROM 文件名或校验值通过 Libretro DAT 标准化"
                    if has_chinese(new_label)
                    else "ROM 文件名或校验值已匹配 DAT 标准名，但缺少中文名，需要人工确认",
                    build_rom_match_diagnostics(rom_matches, "matched", matched_candidate, matched_source),
                )
                continue

            label_candidates = []
            add_unique_candidate(label_candidates, original_label, "label")
            add_unique_candidate(label_candidates, display_label, "label")
            add_unique_candidate(label_candidates, cleaned_name, "label")

            matched_candidate = None
            translated_cn = None
            english_name = None

            for candidate, _ in label_candidates:
                candidate_cn, candidate_en = translate_arcade_label_candidate(candidate)
                is_chinese_match = has_chinese(candidate_cn) and candidate_cn != candidate
                is_standard_name_match = candidate_en and candidate_en != candidate and candidate_en != candidate_cn
                if is_chinese_match or is_standard_name_match:
                    matched_candidate = candidate
                    translated_cn = candidate_cn
                    english_name = candidate_en
                    break

            diagnostics = build_rom_match_diagnostics(rom_matches, "not-found")

            if matched_candidate and translated_cn and translated_cn != matched_candidate:
                new_label = translated_cn
                thumbnail_source = english_name if english_name else matched_candidate
                match_source = "rom-name-cn"
                match_reason = "街机名称通过本地中文库匹配"
                print(f"  [{i}] Found Chinese translation: '{translated_cn}' from '{matched_candidate}'")
            elif matched_candidate and english_name and english_name != matched_candidate:
                new_label = english_name
                thumbnail_source = english_name
                match_source = "libretro-dat"
                match_reason = "街机名称通过 Libretro DAT 标准化"
                print(f"  [{i}] Using standardized English name: '{english_name}' from '{matched_candidate}'")
            else:
                new_label = cleaned_name
                thumbnail_source = cleaned_name
                match_source = "arcade-fallback"
                match_reason = fbneo_fallback_reason(rom_matches)
                print(f"  [{i}] No DAT match found, using cleaned name")

            add_proposal(i, item, display_label, new_label, thumbnail_source, match_source, match_reason, diagnostics)
            continue

        # Priority 1: If original_label already contains Chinese and is not empty, use it
        # This preserves user's manual edits from previous runs
        if original_label and is_chinese_text(original_label) and not is_generic_collection_label(original_label):
            print(f"  [{i}] Using existing Chinese label: '{original_label}'")
            new_label = original_label
            thumbnail_source, chinese_label_source = resolve_thumbnail_source_for_chinese_label(
                original_label,
                path,
                display_label,
                original_label,
            )
            if thumbnail_source:
                print(f"  [{i}] Found thumbnail source: '{thumbnail_source}'")

            label_identity = thumbnail_source if chinese_label_source == "exact_alias" else new_label
            if thumbnail_source and chinese_label_source == "rom_filename":
                known_chinese = translator.db.search_by_english(thumbnail_source, system=translator.system_name)
                if getattr(translator, 'last_match_source', '') == 'title_family':
                    known_chinese, _ = translator.translate(thumbnail_source)
                # Compare a known translation in one language. A disc suffix is
                # display metadata, but disagreeing disc numbers remain a conflict.
                disc_numbers = {int(marker[1] or marker[2]) for value in (original_label, rom_title(path), thumbnail_source)
                                if (marker := DISC_MARKER.search(value))}
                from display_names import base_display_title
                if (known_chinese and len(disc_numbers) <= 1
                        and normalize_value(base_display_title(original_label)) == normalize_value(base_display_title(known_chinese))):
                    label_identity = thumbnail_source
                    if not getattr(translator, 'last_match_source', ''):
                        translator.last_match_source = 'exact'
            diagnostics = {
                "evidence_chain": [
                    {
                        "source": "exact_alias" if chinese_label_source == "exact_alias" else "fuzzy_candidate",
                        "value": original_label,
                        "resolved_name": label_identity,
                        "note": "Chinese playlist label",
                    }
                ]
            }
            if is_arcade and chinese_label_source == 'rom_filename':
                # The label is preserved as display text, not competing ROM
                # identity evidence after a ZIP identifier has resolved.
                diagnostics['evidence_chain'].clear()
            if chinese_label_source == "rom_filename":
                diagnostics["evidence_chain"].insert(0, {
                    "source": "rom_filename",
                    "value": os.path.basename((path or "").split("#", 1)[0]),
                    "resolved_name": thumbnail_source,
                    "note": "ROM filename source; manual review",
                })

            add_proposal(
                i,
                item,
                display_label,
                new_label,
                thumbnail_source,
                "playlist",
                "游戏列表已有中文标签，保留并补齐封面源",
                diagnostics,
            )
            continue

        # Priority 2: Check if filename (without extension) contains Chinese characters
        if path:
            # Handle RetroArch archive paths (e.g. /path/to/Game.zip#Inner.nes)
            basename = os.path.basename(path)
            if '#' in basename:
                basename = basename.split('#')[0]

            filename_no_ext = os.path.splitext(basename)[0]

            if filename_no_ext and any('\u4e00' <= char <= '\u9fff' for char in filename_no_ext):
                # Remove content in brackets [] and parentheses ()
                clean_name = re.sub(r'\[.*?\]', '', filename_no_ext)
                clean_name = re.sub(r'\(.*?\)', '', clean_name).strip()

                if clean_name and any('\u4e00' <= char <= '\u9fff' for char in clean_name):
                    new_label = clean_name
                    # Use translator.translate to get fuzzy matching
                    print(f"  [{i}] Translating: '{clean_name}'")
                    translated_cn, english_name = translator.translate(clean_name)
                    # Check if we found a match
                    if translated_cn and translated_cn != clean_name:
                        # Found Chinese translation
                        new_label = translated_cn
                        thumbnail_source = english_name if english_name else clean_name
                        print(f"  [{i}] Found Chinese translation: '{translated_cn}'")
                    elif english_name and english_name != clean_name:
                        # No Chinese, but found standardized English name
                        new_label = english_name
                        thumbnail_source = english_name
                        print(f"  [{i}] Using standardized English name: '{english_name}'")
                    else:
                        # No match found
                        print(f"  [{i}] No match found")
                        if original_label and not any('\u4e00' <= char <= '\u9fff' for char in original_label):
                            thumbnail_source = original_label
                            print(f"  [{i}] Using original label as fallback: '{original_label}'")
                else:
                    new_label = filename_no_ext
                    print(f"  [{i}] Translating: '{filename_no_ext}'")
                    translated_cn, english_name = translator.translate(filename_no_ext)
                    # Check if we found a match
                    if translated_cn and translated_cn != filename_no_ext:
                        # Found Chinese translation
                        new_label = translated_cn
                        thumbnail_source = english_name if english_name else filename_no_ext
                        print(f"  [{i}] Found Chinese translation: '{translated_cn}'")
                    elif english_name and english_name != filename_no_ext:
                        # No Chinese, but found standardized English name
                        new_label = english_name
                        thumbnail_source = english_name
                        print(f"  [{i}] Using standardized English name: '{english_name}'")
                    else:
                        # No match found
                        print(f"  [{i}] No match found")
                        if original_label and not any('\u4e00' <= char <= '\u9fff' for char in original_label):
                            thumbnail_source = original_label
                            print(f"  [{i}] Using original label as fallback: '{original_label}'")

                filename_diagnostics = {
                    "evidence_chain": [
                        {
                            "source": "rom_filename",
                            "value": filename_from_path(path),
                            "resolved_name": thumbnail_source or new_label,
                            "note": "missing thumbnail source; manual review"
                            if not thumbnail_source
                            else "Chinese filename",
                        }
                    ]
                }
                add_proposal(
                    i,
                    item,
                    display_label,
                    new_label,
                    thumbnail_source,
                    "filename",
                    "中文文件名解析后生成建议",
                    filename_diagnostics,
                )
                continue

        # Priority 3: Translation
        candidates = []
        ignored_parent_note = None
        if path:
            filename_no_ext = rom_title(path)
            if filename_no_ext: candidates.append(filename_no_ext)
        if original_label and original_label not in candidates and not is_generic_collection_label(original_label):
            candidates.append(original_label)
        if path:
            parent_dir = os.path.basename(os.path.dirname(path))
            # Parent folders often describe a collection, e.g. "gba中文游戏".
            # Do not let Chinese folder names override stronger ROM filename or playlist label evidence.
            if (
                parent_dir
                and parent_dir not in candidates
                and not is_chinese_text(parent_dir)
                and not is_system_folder_name(parent_dir, normalized_system)
            ):
                candidates.append(parent_dir)
            elif parent_dir and is_chinese_text(parent_dir):
                ignored_parent_note = f"parent folder ignored: {parent_dir}"

        translated_label = None
        matched_english_name = None
        standard_english_name = None

        for candidate in candidates:
            if looks_nonstandard_name(candidate):
                continue
            translation, std_en = translator.translate(candidate)
            if translation != candidate:
                # Found Chinese translation
                translated_label = translation
                matched_english_name = candidate
                standard_english_name = std_en
                break
            elif std_en != candidate:
                # No Chinese translation, but found standardized English name
                # Store this as a fallback option
                if not standard_english_name:  # Only use first match
                    standard_english_name = std_en
                    matched_english_name = candidate


        # Determine new_label and thumbnail_source
        # Check if we have a Chinese translation (contains Chinese characters)
        if translated_label and any('\u4e00' <= char <= '\u9fff' for char in translated_label):
            # Priority 1: Use Chinese translation
            new_label = translated_label
            thumbnail_source = standard_english_name or matched_english_name
        elif standard_english_name and standard_english_name != matched_english_name:
            # Priority 2: Use standardized English name (if different from original)
            new_label = standard_english_name
            thumbnail_source = standard_english_name
        else:
            # No translation or standardization found, keep original
            new_label = normalize_value(display_label or original_label)
            thumbnail_source = None if looks_nonstandard_name(new_label) else new_label

        if translated_label and has_chinese(translated_label):
            match_source = "rom-name-cn"
            match_reason = "中文库匹配"
        elif standard_english_name:
            match_source = "libretro-dat"
            match_reason = "Libretro DAT 标准名匹配"
        else:
            match_source = "fallback"
            match_reason = "未找到中文或标准英文匹配，保留原始名称"

        evidence_note_parts = [part for part in [
            match_source,
            ignored_parent_note,
            evidence_system_hint(normalized_system),
        ] if part]
        unicode_normalized = bool(original_label and original_label != new_label and normalize_value(original_label) == new_label)

        if match_source == "fallback" and looks_nonstandard_name(new_label):
            evidence_note_parts.extend(["nonstandard", "manual review"])
        elif match_source == "fallback" and unicode_normalized:
            evidence_note_parts.append("unicode-normalized")

        translation_diagnostics = {
            "evidence_chain": [
                {
                    "source": "rom_filename",
                    "value": filename_from_path(path),
                    "resolved_name": thumbnail_source or new_label,
                    "note": "; ".join(evidence_note_parts),
                }
            ]
        }
        if unicode_normalized:
            translation_diagnostics["evidence_chain"].append({
                "source": "fallback",
                "value": original_label,
                "resolved_name": new_label,
                "note": "unicode-normalized",
            })

        add_proposal(
            i,
            item,
            display_label,
            new_label,
            thumbnail_source,
            match_source,
            match_reason,
            translation_diagnostics,
        )

    if 'Sega - Saturn' in translators:
        from saturn_artwork import resolve_proposals
        resolve_proposals(proposed_changes, translators, source_playlist_path or str(playlist_path), verify_artwork, thumbnails_dir)
    from automatic_name_match import resolve as resolve_automatic_names
    from chinese_title_match import resolve_chinese_titles
    resolve_chinese_titles(proposed_changes, translators)
    from disc_title_inheritance import inherit_confirmed_titles
    inherit_confirmed_titles(proposed_changes)
    resolve_automatic_names(proposed_changes, translators)
    from default_recommendations import resolve as resolve_default_recommendations
    resolve_default_recommendations(proposed_changes, translators)
    from title_family import resolve_artwork
    resolve_artwork(proposed_changes, verify_artwork)
    from display_names import normalize_proposals
    normalize_proposals(proposed_changes)
    # Different arcade sets need different RetroArch thumbnail filenames even
    # when their Chinese display titles are identical.
    arcade_targets = {}
    for proposal in proposed_changes:
        if any(term in proposal['system'] for term in ('Arcade', 'FBNeo', 'MAME')):
            key = (proposal['system'], sanitize_filename(proposal['new_label']).casefold())
            arcade_targets.setdefault(key, []).append(proposal)
    for group in arcade_targets.values():
        if (len({row.get('thumbnail_source') for row in group}) > 1
                and all(row.get('match_source') != 'manual_override' for row in group)):
            for row in group:
                row['new_label'] += '（' + rom_title(row['path']) + '）'
    if verify_artwork and thumbnails_dir:
        from playlist_browser import open_artwork_reader, artwork_statuses
        from playlist_artwork import cover_preview_url
        readers = {}
        for proposal in proposed_changes:
            system = proposal['system']
            if system not in readers:
                readers[system] = open_artwork_reader(thumbnails_dir, system)
            reader, image_lookups, image_error = readers[system]
            proposal['artwork'] = artwork_statuses(proposal['new_label'], proposal['path'], reader, image_lookups, thumbnails_dir, system)
            boxart = proposal['artwork']['Named_Boxarts']
            proposal['cover_exists'] = proposal['thumbnail_exists'] = proposal['local_thumbnail_exists'] = boxart['status'] == 'exists'
            proposal['cover_path'] = boxart['path']
            proposal['cover_preview_url'] = cover_preview_url(boxart['path'])
            from artwork_provenance import mark_stale
            mark_stale(proposal)
            if image_error:
                proposal['artwork_message'] = image_error
    targets = {}
    for proposal in proposed_changes:
        key = (proposal['system'], sanitize_filename(proposal['new_label']).casefold())
        targets.setdefault(key, []).append(proposal)
    for group in targets.values():
        if len({row.get('thumbnail_source') for row in group}) > 1:
            for proposal in group:
                proposal.update(match_status='review', needs_review=True, match_score=60)
                proposal['match_reason'] += '；不同图片源会写入同名文件，请保留地区或版本信息'
    for translator in translators.values():
        if hasattr(translator.db, 'close'):
            translator.db.close()
    from library_model import build_library_model
    from preview_identity import identity_state
    model = build_library_model(source_playlist_path or str(playlist_path), playlist_system, items)
    bindings = model['entries']
    for proposal in proposed_changes:
        binding = bindings[proposal['index']]
        for key in ('game_id', 'disc_id', 'content_id'):
            proposal[key] = binding[key]
        proposal['identity'] = identity_state(proposal)
        if (not proposal['identity']['requires_review'] and not proposal.get('thumbnail_source')
                and proposal.get('artwork_identity_status') == 'resolved'
                and proposal.get('artwork_gallery_status') == 'ambiguous' and proposal.get('artwork_candidates')):
            from title_family import recommend_source
            proposal['thumbnail_source'] = recommend_source(proposal['artwork_candidates'])
            proposal['artwork_recommended'] = True
            proposal['match_reason'] = '游戏名称已识别，已推荐匹配封面，可单独更换'
    return proposed_changes
