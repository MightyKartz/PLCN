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

def process_playlist(playlist_path, system_name, thumbnails_dir, rom_name_cn_path):
    # 1. Initialize components
    playlist_manager = PlaylistManager(playlist_path)
    translator = Translator(rom_name_cn_path, system_name)
    downloader = ThumbnailDownloader(thumbnails_dir)

    # 2. Deduplicate items (remove duplicate entries for same game with different file extensions)
    removed_count = playlist_manager.deduplicate_items()
    if removed_count > 0:
        print(f"Removed {removed_count} duplicate entries (e.g., .bin files when .cue exists)")

    # 3. Process playlist
    items = playlist_manager.get_items()
    print(f"Found {len(items)} items in playlist.")

    for i, item in enumerate(items):
        original_label = item.get('label')
        path = item.get('path')
        
        # Priority 1: Check if filename (without extension) contains Chinese characters
        if path:
            filename_no_ext = os.path.splitext(os.path.basename(path))[0]
            if filename_no_ext and any('\u4e00' <= char <= '\u9fff' for char in filename_no_ext):
                # Extract clean game name by removing tags in square brackets
                # Example: "[Wii]胧村正[贴吧中文典藏版]" -> "胧村正"
                import re
                clean_name = re.sub(r'\[.*?\]', '', filename_no_ext).strip()
                
                # If after removing brackets we still have Chinese text, use it
                if clean_name and any('\u4e00' <= char <= '\u9fff' for char in clean_name):
                    print(f"Using Chinese filename: '{clean_name}' (extracted from '{filename_no_ext}')")
                    playlist_manager.update_label(i, clean_name)
                    
                    # Need to find English name for thumbnail download
                    # Try reverse lookup: Chinese -> English in translation_map
                    english_name = translator.reverse_translation_map.get(clean_name)
                    if english_name:
                        print(f"  Found English name via reverse lookup: '{english_name}'")
                    
                    # If not found via reverse lookup, try using original_label if it's English
                    if not english_name and original_label and not any('\u4e00' <= char <= '\u9fff' for char in original_label):
                        english_name = original_label
                        print(f"  Using original label as English name: '{english_name}'")
                    
                    # Download thumbnail using English name
                    if english_name:
                        downloader.download_thumbnail(system_name, english_name, clean_name)
                    else:
                        print(f"  Warning: No English name found for '{clean_name}', skipping thumbnail download")
                    continue
                else:
                    # If no clean Chinese name extracted, use full filename
                    print(f"Using Chinese filename: '{filename_no_ext}' for '{original_label}'")
                    playlist_manager.update_label(i, filename_no_ext)
                    
                    # Try reverse lookup with full filename
                    english_name = translator.reverse_translation_map.get(filename_no_ext)
                    if english_name:
                        print(f"  Found English name via reverse lookup: '{english_name}'")
                    
                    if not english_name and original_label and not any('\u4e00' <= char <= '\u9fff' for char in original_label):
                        english_name = original_label
                        print(f"  Using original label as English name: '{english_name}'")
                    
                    if english_name:
                        downloader.download_thumbnail(system_name, english_name, filename_no_ext)
                    else:
                        print(f"  Warning: No English name found for '{filename_no_ext}', skipping thumbnail download")
                    continue
        
        # Priority 2: Check if parent directory name contains Chinese characters
        if path:
            parent_dir = os.path.basename(os.path.dirname(path))
            # Check if parent_dir contains Chinese characters
            if parent_dir and any('\u4e00' <= char <= '\u9fff' for char in parent_dir):
                print(f"Using Chinese parent directory name: '{parent_dir}' for '{original_label}'")
                playlist_manager.update_label(i, parent_dir)
                
                # Need to get standard English name for thumbnail download
                # Try reverse lookup first: Chinese parent dir -> English in translation_map
                standard_english_name = translator.reverse_translation_map.get(parent_dir)
                if standard_english_name:
                    print(f"  Found English name via reverse lookup: '{standard_english_name}'")
                
                # If not found via reverse lookup, try translating the original label or filename
                if not standard_english_name:
                    filename_no_ext = os.path.splitext(os.path.basename(path))[0] if path else None
                    candidates = []
                    if filename_no_ext:
                        candidates.append(filename_no_ext)
                    if original_label and original_label != filename_no_ext:
                        candidates.append(original_label)
                    
                    # Try to find standard English name through translation (uses normalization internally)
                    for candidate in candidates:
                        _, std_en = translator.translate(candidate)
                        # Only accept if we got a different result (meaning translation was found)
                        if std_en and std_en != candidate:
                            standard_english_name = std_en
                            print(f"  Using standard English name for thumbnail: '{standard_english_name}'")
                            break
                
                # Use standard English name if found, otherwise use filename or original label
                download_name = standard_english_name if standard_english_name else (filename_no_ext if filename_no_ext else original_label)
                if not standard_english_name:
                    print(f"  Warning: No standard English name found, using '{download_name}' for thumbnail download")
                    
                downloader.download_thumbnail(system_name, download_name, parent_dir)
                continue
        
        # Candidates for translation matching:
        # Priority:
        # 1. The filename without extension (Most accurate usually)
        # 2. The original label (Might be custom)
        # 3. The parent directory name (Fallback)
        candidates = []
        
        if path:
            filename_no_ext = os.path.splitext(os.path.basename(path))[0]
            if filename_no_ext:
                candidates.append(filename_no_ext)
        
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
                translated_label = translation
                matched_english_name = candidate
                standard_english_name = std_en
                break
        
        if translated_label:
            print(f"Translating: '{matched_english_name}' -> '{translated_label}' (Standard EN: '{standard_english_name}')")
            playlist_manager.update_label(i, translated_label)
            
            # 3. Download thumbnails
            # We use the STANDARD English name (from DB) to find the thumbnail on the server
            # And save it with the TRANSLATED label (Chinese)
            # If standard_english_name is None (shouldn't happen if translated), fallback to matched_english_name
            download_name = standard_english_name if standard_english_name else matched_english_name
            downloader.download_thumbnail(system_name, download_name, translated_label)
        else:
            print(f"No translation found for: '{original_label}' (checked candidates: {candidates})")

    # 4. Save playlist
    # Overwrite the original file as requested
    output_path = playlist_path
    playlist_manager.save(output_path)
    print(f"Saved translated playlist to {output_path}")

if __name__ == "__main__":
    main()
