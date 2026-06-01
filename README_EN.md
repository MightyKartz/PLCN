# PLCN

PLCN is a local RetroArch playlist localization and thumbnail matching tool. It currently runs as a Python CLI plus local Web UI: it reads `.lpl` playlists, proposes Chinese display names and standard English thumbnail sources from local data and Libretro databases, then writes the confirmed changes back and downloads matching artwork.

> Current implementation note: PLCN is an external local helper for RetroArch playlists and thumbnail folders. It is not an in-RetroArch plugin and does not modify RetroArch itself.

[中文说明 (Chinese Readme)](README.md)

## Features

- **Playlist localization**: Reads RetroArch `.lpl` playlists and maps game labels to Chinese names.
- **Reviewable matching workbench**: The Web UI supports single-playlist and batch workflows with preview, row-level selection, change table, detail panel, progress logs, and real download summaries.
- **Smart thumbnail downloading**:
  - Attempts to recover the standard English game name even when the ROM filename or current label is Chinese.
  - Downloads `Named_Boxarts`, `Named_Snaps`, and `Named_Titles` from the official Libretro thumbnail server.
  - Uses `libretro-database` data to reduce naming mismatches and missing thumbnails.
- **Batch processing**: Processes multiple `.lpl` playlists from one directory.
- **Local data cache**: Uses SQLite to cache translation and matching data.
- **Cross-platform packaging**: Distributed for Windows, macOS, and Linux through PyInstaller builds.

## Installation

Download the latest release for your platform from the [Releases](https://github.com/MightyKartz/PLCN/releases) page.

- **Windows**: Download `PLCN-Windows.exe`
- **macOS**: Download `PLCN-macOS`
- **Linux**: Download `PLCN-Linux`

## Usage

### Quick Start

1. **Download and extract**: Download the latest release from the [Releases](https://github.com/MightyKartz/PLCN/releases) page.

2. **Grant execute permission** (macOS/Linux):

   ```bash
   # macOS
   chmod +x PLCN-macOS

   # Linux
   chmod +x PLCN-Linux
   ```

   > **macOS security note**: On first launch, if macOS reports that the developer cannot be verified, open **System Settings > Privacy & Security** and allow the app to open.

3. **Run the application**:
   - **Windows**: Double-click `PLCN-Windows.exe` or run it from a terminal.
   - **macOS**: Double-click `PLCN-macOS` or run `./PLCN-macOS` from a terminal.
   - **Linux**: Run `./PLCN-Linux` from a terminal.

   The Web UI will open in your default browser.

### Web UI

1. **Configure paths and system**:
   - Single mode: choose one `.lpl` playlist, a system such as `Sony - PlayStation`, and a thumbnail output directory.
   - Batch mode: choose a directory containing `.lpl` files and a thumbnail output directory.

2. **Preview and review**:
   - Generate a preview before applying changes.
   - Review original labels, proposed Chinese labels, thumbnail sources, and match status.
   - Uncheck rows you do not want to write back; unchecked rows are excluded from apply and download.

3. **Apply and download**:
   - Write confirmed labels back to the playlist.
   - Download box art, gameplay snapshots, and title images.
   - Check progress logs, success/failure/skip statistics, and download details in the UI.

### Run from source

```bash
pip install -r requirements.txt

# Start the local Web UI with no arguments
python3 src/plcn.py

# Or start it explicitly
python3 src/plcn.py ui

# Process one playlist from the CLI
python3 src/plcn.py \
  --playlist "/path/to/playlist.lpl" \
  --system "Sony - PlayStation" \
  --thumbnails-dir "/path/to/RetroArch/thumbnails"

# Process all .lpl files in a directory
python3 src/plcn.py \
  --batch-dir "/path/to/playlists" \
  --thumbnails-dir "/path/to/RetroArch/thumbnails"
```

## Development Status

- The main workflow lives in `src/plcn.py`, `src/server.py`, `src/database.py`, `src/translator.py`, `src/libretro_db.py`, and `src/thumbnail_downloader.py`.
- The Web UI currently lives in the single template `src/templates/plcn.html`; future work should split it into smaller, more maintainable pieces.
- See [DOC/OPTIMIZATION_PLAN.md](DOC/OPTIMIZATION_PLAN.md) for the follow-up optimization plan.

Common validation commands:

```bash
python3 -m py_compile src/*.py
python3 -m pytest --collect-only -q
```

## Credits & Acknowledgements

Special thanks to **yingw** for the comprehensive ROM name translation database:

- [rom-name-cn](https://github.com/yingw/rom-name-cn)

This project uses `rom-name-cn` data as the foundation for Chinese game-name translation.
