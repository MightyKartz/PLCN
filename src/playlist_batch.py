"""Command-line single-playlist and directory processing, independent of HTTP."""
import glob
import json
import os
from playlist_analysis import (
    analyze_playlist,
)
from playlist_writeback import (
    apply_changes,
)


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


def process_playlist(playlist_path, system_name, thumbnails_dir, rom_name_cn_path, manual_overrides_path=None):
    print(f"Analyzing playlist: {playlist_path}")
    changes = analyze_playlist(playlist_path, system_name, rom_name_cn_path, thumbnails_dir, manual_overrides_path=manual_overrides_path)

    print(f"Applying {len(changes)} changes...")
    apply_changes(playlist_path, changes, thumbnails_dir)


def process_directory(batch_dir, thumbnails_dir, rom_name_cn_path, manual_overrides_path=None):
    print(f"Batch mode enabled. Processing playlists in: {batch_dir}")
    if not os.path.exists(batch_dir):
        print(f"Error: Batch directory not found: {batch_dir}")
        return

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
        process_playlist(lpl_file, system_name, thumbnails_dir, rom_name_cn_path, manual_overrides_path)
