import argparse
import json
import os
import sys
import glob
from playlist_manager import PlaylistManager
from translator import Translator
from thumbnail_downloader import ThumbnailDownloader
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

def analyze_playlist(playlist_path, system_name, rom_name_cn_path):
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

    for i, item in enumerate(items):
        original_label = item.get('label')
        path = item.get('path')
        
        new_label = original_label
        thumbnail_source = None
        
        # Special handling for FBNeo/Arcade games
        # These games have region codes like "(World 900227)" that need to be removed
        is_arcade = 'Arcade' in normalized_system or 'FBNeo' in normalized_system
        
        if is_arcade and original_label and not any('\u4e00' <= char <= '\u9fff' for char in original_label):
            # Clean the arcade name (remove region codes and dates)
            cleaned_name = clean_arcade_name(original_label)
            print(f"  [{i}] Arcade game detected: '{original_label}' -> '{cleaned_name}'")
            
            # Try to translate the cleaned name
            translated_cn, english_name = translator.translate(cleaned_name)
            
            # Check if we found a match
            if translated_cn and translated_cn != cleaned_name:
                # Found Chinese translation
                new_label = translated_cn
                thumbnail_source = english_name if english_name else cleaned_name
                print(f"  [{i}] Found Chinese translation: '{translated_cn}'")
            elif english_name and english_name != cleaned_name:
                # No Chinese translation, but found standardized English name
                new_label = english_name
                thumbnail_source = english_name
                print(f"  [{i}] Using standardized English name: '{english_name}'")
            else:
                # No match found, use cleaned name as label for consistency
                new_label = cleaned_name
                thumbnail_source = cleaned_name
                print(f"  [{i}] No match found, using cleaned name")
            
            proposed_changes.append({
                'index': i,
                'original_label': original_label,
                'path': path,
                'new_label': new_label,
                'thumbnail_source': thumbnail_source,
                'system': system_name
            })
            continue
        
        # Priority 0: If original_label already contains Chinese and is not empty, use it
        # This preserves user's manual edits from previous runs
        if original_label and any('\u4e00' <= char <= '\u9fff' for char in original_label):
            print(f"  [{i}] Using existing Chinese label: '{original_label}'")
            new_label = original_label
            # Try to find English name for thumbnail
            translated_cn, english_name = translator.translate(original_label)
            # Check if we found a match (either name changed from original)
            if (translated_cn and translated_cn != original_label) or (english_name and english_name != original_label):
                # We found a match in database
                if english_name and english_name != original_label:
                    thumbnail_source = english_name
                    print(f"  [{i}] Found thumbnail source: '{english_name}'")
                # Update to standardized Chinese name if available
                if translated_cn and translated_cn != original_label:
                    new_label = translated_cn
                    print(f"  [{i}] Updated to standardized Chinese name: '{translated_cn}'")
            else:
                # No match found, keep original label but still try to download thumbnails
                print(f"  [{i}] No thumbnail source found for '{original_label}'")
                thumbnail_source = original_label  # Try with Chinese name as fallback

            
            proposed_changes.append({
                'index': i,
                'original_label': original_label,
                'path': path,
                'new_label': new_label,
                'thumbnail_source': thumbnail_source,
                'system': system_name
            })
            continue
        
        # Logic to determine new label and thumbnail source from filename
        # Priority 1: Check if filename (without extension) contains Chinese characters
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
                
                proposed_changes.append({
                    'index': i,
                    'original_label': original_label,
                    'path': path,
                    'new_label': new_label,
                    'thumbnail_source': thumbnail_source,
                    'system': system_name
                })
                continue
        
        # Priority 2: Check if parent directory name contains Chinese characters
        if path:
            parent_dir = os.path.basename(os.path.dirname(path))
            if parent_dir and any('\u4e00' <= char <= '\u9fff' for char in parent_dir):
                new_label = parent_dir
                
                # Use translator.translate for fuzzy matching
                translated_cn, english_name = translator.translate(parent_dir)
                # Check if we found a match
                if translated_cn and translated_cn != parent_dir:
                    # Found Chinese translation
                    new_label = translated_cn
                    thumbnail_source = english_name if english_name else parent_dir
                elif english_name and english_name != parent_dir:
                    # No Chinese, but found standardized English name
                    new_label = english_name
                    thumbnail_source = english_name
                else:
                    # Try translating candidates
                    filename_no_ext = os.path.splitext(os.path.basename(path))[0] if path else None
                    candidates = []
                    if filename_no_ext: candidates.append(filename_no_ext)
                    if original_label and original_label != filename_no_ext: candidates.append(original_label)
                    
                    for candidate in candidates:
                        _, std_en = translator.translate(candidate)
                        if std_en and std_en != candidate:
                            thumbnail_source = std_en
                            break
                    
                    if not thumbnail_source:
                        thumbnail_source = filename_no_ext if filename_no_ext else original_label

                proposed_changes.append({
                    'index': i,
                    'original_label': original_label,
                    'path': path,
                    'new_label': new_label,
                    'thumbnail_source': thumbnail_source,
                    'system': system_name
                })
                continue

        # Priority 3: Translation
        candidates = []
        if path:
            filename_no_ext = os.path.splitext(os.path.basename(path))[0]
            if filename_no_ext: candidates.append(filename_no_ext)
        if original_label and original_label not in candidates:
            candidates.append(original_label)
        if path:
            parent_dir = os.path.basename(os.path.dirname(path))
            if parent_dir and parent_dir not in candidates:
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
        if translated_label:
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
        
        proposed_changes.append({
            'index': i,
            'original_label': original_label,
            'path': path,
            'new_label': new_label,
            'thumbnail_source': thumbnail_source,
            'system': system_name
        })

    return proposed_changes

def apply_changes(playlist_path, changes, thumbnails_dir, backup=True, progress_callback=None):
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
        
        # Update label
        if new_label:
            playlist_manager.update_label(index, new_label)
            
        # Collect download task
        if thumbnail_source and new_label:
            download_tasks.append((system, thumbnail_source, new_label))
            
    # Save playlist
    playlist_manager.save(playlist_path)
    print(f"Saved updated playlist to {playlist_path}")
    
    # Batch download
    if download_tasks:
        downloader.download_batch(download_tasks, progress_callback=progress_callback)

def process_playlist(playlist_path, system_name, thumbnails_dir, rom_name_cn_path):
    print(f"Analyzing playlist: {playlist_path}")
    changes = analyze_playlist(playlist_path, system_name, rom_name_cn_path)
    
    print(f"Applying {len(changes)} changes...")
    apply_changes(playlist_path, changes, thumbnails_dir)

if __name__ == "__main__":
    main()
