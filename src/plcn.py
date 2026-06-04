import argparse
import hashlib
import json
import os
import re
import shlex
import sys
import glob
import unicodedata
import urllib.parse
from playlist_manager import PlaylistManager
from translator import Translator
from thumbnail_downloader import ThumbnailDownloader
from rom_fingerprint import build_rom_match_candidates
import webbrowser
import server
import subprocess

CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}

def kill_process_on_port(port):
    """Kill any process using the specified port."""
    try:
        # Find process using the port
        result = subprocess.run(
            ['lsof', '-ti', f':{port}'],
            capture_output=True,
            text=True
        )
        if result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                subprocess.run(['kill', '-9', pid])
            print(f"Killed process(es) on port {port}")
    except Exception as e:
        # Ignore errors (no process on port, etc.)
        pass

def main():
    # Auto-launch UI if no arguments provided (e.g., double-click on macOS)
    if len(sys.argv) == 1:
        print("No arguments provided. Starting Web UI...")
        # Clean up any existing process on the port
        kill_process_on_port(server.PORT)
        
        url = f"http://localhost:{server.PORT}"
        print(f"Opening {url}")
        webbrowser.open(url)
        server.run_server()
        return
    
    # Check for 'ui' subcommand
    if len(sys.argv) > 1 and sys.argv[1] == 'ui':
        print("Starting Web UI...")
        
        # Clean up any existing process on the port
        kill_process_on_port(server.PORT)
        
        url = f"http://localhost:{server.PORT}"
        print(f"Opening {url}")
        webbrowser.open(url)
        server.run_server()
        return

    config = load_config()
    
    parser = argparse.ArgumentParser(description="RetroArch Playlist Translator and Thumbnail Downloader")
    parser.add_argument("command", nargs="?", help="Subcommand: 'ui' to open Web UI")
    parser.add_argument("--playlist", help="Path to the RetroArch playlist file (.lpl)")
    parser.add_argument("--system", help="System name (e.g., 'Sega - Saturn')")
    parser.add_argument("--thumbnails-dir", help="Directory to save thumbnails")
    parser.add_argument("--rom-name-cn-path", default="data/rom-name-cn", help="Path to rom-name-cn repository")
    parser.add_argument("--batch-dir", help="Directory containing multiple .lpl files for batch processing")

    args = parser.parse_args()

    # Determine values from args or config
    # Priority: Args > Config
    
    rom_name_cn_path = args.rom_name_cn_path or config.get("rom_name_cn_path")
    if not rom_name_cn_path:
        if getattr(sys, 'frozen', False):
            rom_name_cn_path = os.path.join(sys._MEIPASS, "data", "rom-name-cn")
        else:
            rom_name_cn_path = "data/rom-name-cn"
    
    # Check for batch mode
    batch_dir = args.batch_dir or config.get("batch_dir")
    
    if batch_dir:
        print(f"Batch mode enabled. Processing playlists in: {batch_dir}")
        if not os.path.exists(batch_dir):
            print(f"Error: Batch directory not found: {batch_dir}")
            return
            
        thumbnails_dir = args.thumbnails_dir or config.get("thumbnails_dir")
        if not thumbnails_dir:
             print("Error: Thumbnails directory is required for batch mode.")
             return

        lpl_files = glob.glob(os.path.join(batch_dir, "*.lpl"))
        print(f"Found {len(lpl_files)} playlist files.")
        
        for lpl_file in lpl_files:
            print(f"\nProcessing: {lpl_file}")
            # Detect system
            system_name = detect_system(lpl_file)
            if not system_name:
                print(f"Skipping {lpl_file}: Could not detect system name.")
                continue
                
            print(f"Detected System: {system_name}")
            process_playlist(lpl_file, system_name, thumbnails_dir, rom_name_cn_path)
            
    else:
        # Single file mode
        playlist_path = args.playlist or config.get("playlist_path")
        system_name = args.system or config.get("system_name")
        thumbnails_dir = args.thumbnails_dir or config.get("thumbnails_dir")
        
        if not playlist_path or not system_name or not thumbnails_dir:
            print("Error: Missing required configuration. Please provide --playlist, --system, and --thumbnails-dir arguments, or set them in config.json via the Web UI.")
            return

        process_playlist(playlist_path, system_name, thumbnails_dir, rom_name_cn_path)

def detect_system(playlist_path):
    """Detects system name from playlist file content."""
    try:
        with open(playlist_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            items = data.get('items', [])
            if items:
                db_name = items[0].get('db_name', '')
                if db_name:
                    return os.path.splitext(db_name)[0]
    except Exception as e:
        print(f"Error detecting system for {playlist_path}: {e}")
    return None

def has_chinese(text):
    return any('\u4e00' <= char <= '\u9fff' for char in (text or ''))

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

def normalize_value(value):
    return unicodedata.normalize('NFC', value or '')

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

def build_proposal_id(system_name, index, path, original_item_label, original_db_name):
    raw = "\n".join([
        normalize_value(system_name),
        str(index),
        normalize_value(path),
        normalize_value(original_item_label),
        normalize_value(original_db_name),
    ])
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]

def sanitize_thumbnail_filename(name):
    for char in ['&', '*', '/', ':', '<', '>', '?', '\\', '|']:
        name = (name or '').replace(char, '_')
    return name

def local_thumbnail_path(thumbnails_dir, system_name, label, type_name="Named_Boxarts"):
    if not thumbnails_dir or not label:
        return None
    filename = sanitize_thumbnail_filename(label) + ".png"
    return os.path.join(thumbnails_dir, system_name, type_name, filename)

def boxart_dir_path(thumbnails_dir, system_name, type_name="Named_Boxarts"):
    if not thumbnails_dir or not system_name:
        return None
    return os.path.join(thumbnails_dir, system_name, type_name)

def adb_thumbnail_exists(thumbnails_dir, system_name, label, type_name="Named_Boxarts"):
    if not thumbnails_dir or not label:
        return False, None
    try:
        from retroarch_scanner import is_adb_uri, parse_adb_uri, _adb_shell
        if not is_adb_uri(thumbnails_dir):
            return False, None
        serial, remote_dir = parse_adb_uri(thumbnails_dir)
        if not remote_dir:
            return False, None
        filename = sanitize_thumbnail_filename(label) + ".png"
        remote_path = "/".join(part.strip("/") for part in [remote_dir, system_name, type_name, filename] if part)
        remote_path = "/" + remote_path if not remote_path.startswith("/") else remote_path
        script = f"test -f {shlex.quote(remote_path)} && echo 1 || echo 0"
        exists = (_adb_shell(serial, script, timeout=8) or "").strip().splitlines()
        return (exists[0] == "1" if exists else False), remote_path
    except Exception:
        return False, None

def build_existing_boxart_lookup(thumbnails_dir, system_name, type_name="Named_Boxarts"):
    if not thumbnails_dir or not system_name:
        return {"type": "none", "base_path": None, "filenames": set()}

    try:
        from retroarch_scanner import is_adb_uri, parse_adb_uri, _adb_shell
        if is_adb_uri(thumbnails_dir):
            serial, remote_dir = parse_adb_uri(thumbnails_dir)
            if not remote_dir:
                return {"type": "adb", "base_path": None, "filenames": set()}
            remote_path = "/".join(part.strip("/") for part in [remote_dir, system_name, type_name] if part)
            remote_path = "/" + remote_path if not remote_path.startswith("/") else remote_path
            output = _adb_shell(serial, f"ls -1 {shlex.quote(remote_path)} 2>/dev/null", timeout=15)
            filenames = {os.path.basename(line.strip()) for line in (output or "").splitlines() if line.strip()}
            return {"type": "adb", "serial": serial, "base_path": remote_path, "filenames": filenames}
    except Exception:
        return {"type": "adb", "serial": None, "base_path": None, "filenames": set()}

    local_dir = boxart_dir_path(thumbnails_dir, system_name, type_name)
    if not local_dir or not os.path.isdir(local_dir):
        return {"type": "local", "base_path": local_dir, "filenames": set()}
    try:
        filenames = {name for name in os.listdir(local_dir) if os.path.isfile(os.path.join(local_dir, name))}
    except OSError:
        filenames = set()
    return {"type": "local", "base_path": local_dir, "filenames": filenames}

def find_existing_boxart(thumbnails_dir, system_name, *labels, lookup=None):
    if not thumbnails_dir:
        return False, None
    if lookup is not None:
        filenames = lookup.get("filenames") or set()
        base_path = lookup.get("base_path")
        for label in labels:
            if not label:
                continue
            filename = sanitize_thumbnail_filename(label) + ".png"
            if filename in filenames:
                if lookup.get("type") == "adb":
                    remote_path = f"{base_path.rstrip('/')}/{filename}" if base_path else filename
                    serial = lookup.get("serial")
                    if serial and remote_path.startswith("/"):
                        return True, f"adb://{serial}{remote_path}"
                    return True, remote_path
                return True, os.path.join(base_path, filename) if base_path else filename
        return False, None

    try:
        from retroarch_scanner import is_adb_uri, parse_adb_uri
        if is_adb_uri(thumbnails_dir):
            serial, _remote_dir = parse_adb_uri(thumbnails_dir)
            for label in labels:
                exists, path = adb_thumbnail_exists(thumbnails_dir, system_name, label)
                if exists:
                    return True, f"adb://{serial}{path}" if path and path.startswith("/") else path
            return False, None
    except Exception:
        pass

    for label in labels:
        path = local_thumbnail_path(thumbnails_dir, system_name, label)
        if path and os.path.exists(path):
            return True, path
    return False, None

def cover_preview_url(cover_path):
    if not cover_path:
        return None
    return "/api/thumbnail/preview?path=" + urllib.parse.quote(str(cover_path), safe="")

def classify_match(display_label, new_label, thumbnail_source, current_label=None, cover_exists=False):
    duplicate = bool(re.search(r'\(\d+\)$', (display_label or '').strip()) or re.search(r'\(\d+\)$', (new_label or '').strip()))
    missing_thumb = not thumbnail_source
    label_has_chinese = has_chinese(new_label)
    current_matches_new = bool(current_label and new_label and normalize_value(current_label) == normalize_value(new_label))

    if duplicate:
        return {
            "match_status": "duplicate",
            "match_score": 99,
            "needs_review": True,
            "default_reason": "检测到重复项标记，需要确认是否保留或重命名",
        }
    if current_matches_new and thumbnail_source and cover_exists and label_has_chinese:
        return {
            "match_status": "ready",
            "match_score": 100,
            "needs_review": False,
            "default_reason": "中文名、封面源和本地封面已就绪，无需修复",
        }
    if current_matches_new and thumbnail_source and label_has_chinese:
        return {
            "match_status": "download",
            "match_score": 94,
            "needs_review": False,
            "default_reason": "中文名和封面源已就绪，仅需下载封面",
        }
    if missing_thumb or not label_has_chinese:
        return {
            "match_status": "review",
            "match_score": 72 if label_has_chinese else 64,
            "needs_review": True,
            "default_reason": "缺少中文名或封面标准名，需要人工确认",
        }
    if cover_exists:
        return {
            "match_status": "rename",
            "match_score": 96,
            "needs_review": False,
            "default_reason": "封面已存在，仅需写入中文名",
        }
    return {
        "match_status": "matched",
        "match_score": 96 if thumbnail_source != display_label else 90,
        "needs_review": False,
        "default_reason": "已匹配中文名和缩略图标准名",
    }

def build_change_proposal(index, item, display_label, new_label, thumbnail_source, system_name, match_source="heuristic", match_reason=None, match_diagnostics=None, cover_exists=False, cover_path=None):
    original_item_label = item.get('label') or ''
    original_db_name = item.get('db_name') or ''
    path = item.get('path') or ''
    match_info = classify_match(display_label, new_label, thumbnail_source, current_label=original_item_label, cover_exists=cover_exists)

    return {
        'proposal_id': build_proposal_id(system_name, index, path, original_item_label, original_db_name),
        'index': index,
        'original_label': display_label,
        'original_item_label': original_item_label,
        'original_db_name': original_db_name,
        'path': path,
        'new_label': new_label,
        'thumbnail_source': thumbnail_source,
        'system': system_name,
        'match_score': match_info["match_score"],
        'match_status': match_info["match_status"],
        'match_source': match_source,
        'match_reason': match_reason or match_info["default_reason"],
        'match_diagnostics': match_diagnostics or {},
        'needs_review': match_info["needs_review"],
        'thumbnail_exists': cover_exists,
        'local_thumbnail_exists': cover_exists,
        'cover_exists': cover_exists,
        'cover_path': cover_path,
        'cover_preview_url': cover_preview_url(cover_path),
    }

def proposal_matches_item(change, item):
    expected_label = change.get('original_item_label')
    expected_db_name = change.get('original_db_name')
    expected_path = change.get('path')

    if expected_path and normalize_value(item.get('path')) != normalize_value(expected_path):
        return False
    if expected_label is not None and normalize_value(item.get('label')) != normalize_value(expected_label):
        return False
    if expected_db_name and normalize_value(item.get('db_name')) != normalize_value(expected_db_name):
        return False
    return True

def analyze_playlist(playlist_path, system_name, rom_name_cn_path, thumbnails_dir=None):
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
    translator = Translator(rom_name_cn_path, normalized_system)
    
    # Deduplicate items (in memory for analysis)
    # Note: This modifies the playlist_manager's internal state
    removed_count = playlist_manager.deduplicate_items()
    if removed_count > 0:
        print(f"Removed {removed_count} duplicate entries")

    items = playlist_manager.get_items()
    proposed_changes = []
    boxart_lookup = build_existing_boxart_lookup(thumbnails_dir, system_name)

    def add_proposal(index, item, display_label, new_label, thumbnail_source, match_source, match_reason, match_diagnostics=None):
        cover_exists, cover_path = find_existing_boxart(
            thumbnails_dir,
            system_name,
            new_label,
            item.get('label') or '',
            lookup=boxart_lookup,
        )
        proposed_changes.append(build_change_proposal(
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
        ))

    def build_rom_match_diagnostics(rom_matches, dat_result, matched_candidate=None, matched_source=None):
        return {
            "candidate_count": len(rom_matches.candidates),
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
        if not value:
            return None
        basename = os.path.basename(value)
        if '#' in basename:
            basename = basename.split('#')[0]
        return os.path.splitext(basename)[0] or None

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

        if translator.system_name:
            chinese, english = translator.db.search_by_normalized_alias(normalized)
            if chinese and english:
                return english

        if translator.libretro_db:
            standard_name = translator.libretro_db.get_standard_name(candidate)
            if standard_name:
                return standard_name

        return None

    def resolve_thumbnail_source_for_chinese_label(chinese_label, path, display_label, original_label):
        exact_chinese_source = translator.db.search_by_chinese(chinese_label, system=translator.system_name)
        if exact_chinese_source:
            return exact_chinese_source

        english_candidates = []
        add_unique_candidate(english_candidates, filename_stem_from_path(path), "filename")
        add_unique_candidate(english_candidates, display_label, "display")
        add_unique_candidate(english_candidates, original_label, "playlist")

        for candidate, _ in english_candidates:
            source = resolve_exact_english_source(candidate)
            if source:
                return source

        for candidate, _ in english_candidates:
            if candidate and not is_chinese_text(candidate):
                return candidate

        return chinese_label

    for i, item in enumerate(items):
        original_label = item.get('label')
        path = item.get('path')
        
        # Extract ROM name for display (filename without extension)
        display_label = original_label
        if path:
            basename = os.path.basename(path)
            if '#' in basename:
                basename = basename.split('#')[0]
            display_label = os.path.splitext(basename)[0]
        
        new_label = original_label
        thumbnail_source = None
        
        # Special handling for FBNeo/Arcade games
        # These games have region codes like "(World 900227)" that need to be removed
        is_arcade = 'Arcade' in normalized_system or 'FBNeo' in normalized_system
        
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
            thumbnail_source = resolve_thumbnail_source_for_chinese_label(original_label, path, display_label, original_label)
            if thumbnail_source:
                print(f"  [{i}] Found thumbnail source: '{thumbnail_source}'")
            
            add_proposal(i, item, display_label, new_label, thumbnail_source, "playlist", "游戏列表已有中文标签，保留并补齐封面源")
            continue

        # Priority 2: Check if filename (without extension) contains Chinese characters
        if path:
            # Handle RetroArch archive paths (e.g. /path/to/Game.zip#Inner.nes)
            basename = os.path.basename(path)
            if '#' in basename:
                basename = basename.split('#')[0]
            
            filename_no_ext = os.path.splitext(basename)[0]
            
            if filename_no_ext and any('\u4e00' <= char <= '\u9fff' for char in filename_no_ext):
                import re
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
                
                add_proposal(i, item, display_label, new_label, thumbnail_source, "filename", "中文文件名解析后生成建议")
                continue

        # Priority 3: Translation
        candidates = []
        if path:
            filename_no_ext = os.path.splitext(os.path.basename(path))[0]
            if filename_no_ext: candidates.append(filename_no_ext)
        if original_label and original_label not in candidates and not is_generic_collection_label(original_label):
            candidates.append(original_label)
        if path:
            parent_dir = os.path.basename(os.path.dirname(path))
            # Parent folders often describe a collection, e.g. "gba中文游戏".
            # Do not let Chinese folder names override stronger ROM filename or playlist label evidence.
            if parent_dir and parent_dir not in candidates and not is_chinese_text(parent_dir):
                candidates.append(parent_dir)
        
        translated_label = None
        matched_english_name = None
        standard_english_name = None
        
        for candidate in candidates:
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
            thumbnail_source = standard_english_name if standard_english_name else matched_english_name
        elif standard_english_name and standard_english_name != matched_english_name:
            # Priority 2: Use standardized English name (if different from original)
            new_label = standard_english_name
            thumbnail_source = standard_english_name
        else:
            # No translation or standardization found, keep original
            new_label = original_label
            thumbnail_source = original_label
        
        if translated_label and has_chinese(translated_label):
            match_source = "rom-name-cn"
            match_reason = "中文库匹配"
        elif standard_english_name:
            match_source = "libretro-dat"
            match_reason = "Libretro DAT 标准名匹配"
        else:
            match_source = "fallback"
            match_reason = "未找到中文或标准英文匹配，保留原始名称"

        add_proposal(i, item, display_label, new_label, thumbnail_source, match_source, match_reason)

    return proposed_changes

def apply_changes(playlist_path, changes, thumbnails_dir, backup=True, progress_callback=None, download_thumbnails=True):
    """
    Applies the changes to the playlist and downloads thumbnails.
    """
    # 0. Backup
    if backup:
        backup_path = playlist_path + ".bak"
        import shutil
        shutil.copy2(playlist_path, backup_path)
        print(f"Backed up playlist to {backup_path}")

    playlist_manager = PlaylistManager(playlist_path)
    # Re-deduplicate to ensure indices match (assuming analyze was run on fresh load)
    # WARNING: If analyze removed items, indices in 'changes' must align with post-deduplication items.
    # Ideally, analyze should return the FULL list of items including unchanged ones, or we trust the order.
    # Since we re-instantiate PlaylistManager, we must ensure deterministic behavior.
    playlist_manager.deduplicate_items()
    
    downloader = ThumbnailDownloader(thumbnails_dir)
    download_tasks = []
    
    for change in changes:
        index = change['index']
        new_label = change['new_label']
        thumbnail_source = change['thumbnail_source']
        system = change['system']
        target_path = change.get('path')
        applied = False
        
        # Update label
        if new_label:
            # Try to find by path first (more robust)
            if target_path:
                norm_target = normalize_value(target_path)
                for item in playlist_manager.items:
                    item_path = item.get('path')
                    if item_path and normalize_value(item_path) == norm_target:
                        if not proposal_matches_item(change, item):
                            print(f"Warning: Proposal {change.get('proposal_id', index)} is stale for {os.path.basename(target_path)}. Skipping update.")
                            applied = False
                            break
                        item['label'] = new_label
                        applied = True
                        print(f"Updated label for {os.path.basename(target_path)} to '{new_label}'")
                        break
            
            # Fallback to index if path not found or not provided
            if not applied:
                if 0 <= index < len(playlist_manager.items):
                    # Verify path matches if possible
                    current_item = playlist_manager.items[index]
                    if target_path and normalize_value(current_item.get('path')) != normalize_value(target_path):
                        print(f"Warning: Index {index} path mismatch. Expected {target_path}, got {current_item.get('path')}. Skipping update.")
                    elif not proposal_matches_item(change, current_item):
                        print(f"Warning: Proposal {change.get('proposal_id', index)} no longer matches playlist item at index {index}. Skipping update.")
                    else:
                        playlist_manager.update_label(index, new_label)
                        applied = True
                        print(f"Updated label at index {index} to '{new_label}'")
                else:
                    print(f"Error: Index {index} out of bounds. Skipping update.")
            
        # Collect download task
        if applied and thumbnail_source and new_label:
            download_tasks.append((system, thumbnail_source, new_label))
            
    # Save playlist
    playlist_manager.save(playlist_path)
    print(f"Saved updated playlist to {playlist_path}")
    
    # Verify save
    try:
        import time
        mtime = os.path.getmtime(playlist_path)
        print(f"File modification time: {time.ctime(mtime)}")
        # Optional: Read back first item to verify
        # with open(playlist_path, 'r', encoding='utf-8') as f:
        #     data = json.load(f)
        #     print(f"Verification - First item label: {data['items'][0].get('label')}")
    except Exception as e:
        print(f"Verification failed: {e}")

    if not download_tasks:
        return downloader.empty_summary(0)

    if not download_thumbnails:
        return downloader.skipped_summary(download_tasks, "已按用户选项跳过下载")

    # Batch download
    return downloader.download_batch(download_tasks, progress_callback=progress_callback)

def process_playlist(playlist_path, system_name, thumbnails_dir, rom_name_cn_path):
    print(f"Analyzing playlist: {playlist_path}")
    changes = analyze_playlist(playlist_path, system_name, rom_name_cn_path)
    
    print(f"Applying {len(changes)} changes...")
    apply_changes(playlist_path, changes, thumbnails_dir)

if __name__ == "__main__":
    main()
