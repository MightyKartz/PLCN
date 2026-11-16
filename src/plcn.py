"""Command-line argument parsing and dispatch for PLCN."""
import argparse
import json
import os
import sys

import app_paths
from manual_overrides import default_overrides_path
from playlist_service import process_directory, process_playlist

CONFIG_FILE = str(app_paths.config_path())


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def main():
    app_paths.initialize()
    if len(sys.argv) > 1 and sys.argv[1] == 'data':
        from data_pack import main as data_main
        data_main(sys.argv[2:])
        return
    if len(sys.argv) == 1 or sys.argv[1] == 'ui':
        from server import run_server
        run_server(open_browser=True)
        return

    config = load_config()

    parser = argparse.ArgumentParser(description="RetroArch Assistant — game library and handheld management (legacy plcn CLI)")
    parser.add_argument("command", nargs="?", help="Subcommand: 'ui' to open Web UI")
    parser.add_argument("--playlist", help="Path to the RetroArch playlist file (.lpl)")
    parser.add_argument("--system", help="System name (e.g., 'Sega - Saturn')")
    parser.add_argument("--thumbnails-dir", help="Directory to save thumbnails")
    parser.add_argument("--rom-name-cn-path", help="Path to rom-name-cn repository")
    parser.add_argument("--batch-dir", help="Directory containing multiple .lpl files for batch processing")

    args = parser.parse_args()

    # Determine values from args or config
    # Priority: Args > Config

    rom_name_cn_path = args.rom_name_cn_path or config.get("rom_name_cn_path")
    if not rom_name_cn_path:
        if getattr(sys, 'frozen', False):
            rom_name_cn_path = os.path.join(sys._MEIPASS, "data", "rom-name-cn")
        else:
            rom_name_cn_path = str(app_paths.default_source())

    # Check for batch mode
    batch_dir = args.batch_dir or config.get("batch_dir")

    if batch_dir:
        process_directory(batch_dir, args.thumbnails_dir or config.get("thumbnails_dir"),
                          rom_name_cn_path, config.get("manual_overrides_path") or default_overrides_path())
    else:
        # Single file mode
        playlist_path = args.playlist or config.get("playlist_path")
        system_name = args.system or config.get("system_name")
        thumbnails_dir = args.thumbnails_dir or config.get("thumbnails_dir")

        if not playlist_path or not system_name or not thumbnails_dir:
            print("Error: Missing required configuration. Please provide --playlist, --system, and --thumbnails-dir arguments, or set them in config.json via the Web UI.")
            return

        process_playlist(playlist_path, system_name, thumbnails_dir, rom_name_cn_path, config.get("manual_overrides_path") or default_overrides_path())


if __name__ == "__main__":
    main()
