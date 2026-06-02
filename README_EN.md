# PLCN

[中文 README](README.md)

PLCN is a local RetroArch game-list localization and thumbnail matching tool. It currently runs as a Python CLI plus local Web UI: it reads `.lpl` game lists, proposes Chinese display names and standard English thumbnail sources from local data and Libretro databases, then writes the confirmed changes back and downloads matching artwork.

> Current implementation note: PLCN is an external local helper for RetroArch playlists and thumbnail folders. It is not an in-RetroArch plugin and does not modify RetroArch itself.

## Latest Version: v3.0.0

- Added the PLCN v3.0 device-library workbench for scanning RetroArch game lists from local folders, mounted devices, and authorized ADB Android handhelds/devices.
- Reworked the Web UI information architecture with device/directory entry on the left, game-library scan in the center, on-demand repair preview on the right, and task progress at the bottom.
- Improved row-level repair flows with system abbreviation tabs, cover thumbnails, cover status, manual confirmation, selected-item apply, and automatic database search using the default English game name.
- Refined light/dark themes, UI language switching, button semantics, table alignment, and narrow-screen behavior.
- Added regression tests for device scanning, UI information architecture, and dark-theme active states.

## Features

- **Game-list localization**: Reads RetroArch `.lpl` game lists and maps game labels to Chinese names.
- **RetroArch directory scanning**: The Web UI can scan local RetroArch roots, `playlists` folders, mounted device folders, and authorized ADB Android handhelds/devices, then list detected `.lpl` game lists.
- **Reviewable matching workbench**: The Web UI supports single-list and batch workflows with preview, row-level selection, change table, detail panel, progress logs, and real download summaries.
- **Smart thumbnail downloading**:
  - Attempts to recover the standard English game name even when the ROM filename or current label is Chinese.
  - Downloads `Named_Boxarts`, `Named_Snaps`, and `Named_Titles` from the official Libretro thumbnail server.
  - Uses `libretro-database` data to reduce naming mismatches and missing thumbnails.
- **Batch processing**: Processes multiple `.lpl` game lists from one directory.
- **Local data cache**: Uses SQLite to cache translation and matching data.
- **Cross-platform packaging**: Distributed for Windows, macOS, and Linux through PyInstaller builds.

## Installation

Download the latest release for your platform from the [Releases](https://github.com/MightyKartz/PLCN/releases) page.

- **Windows**: Download `PLCN-Windows-x64.exe`
- **macOS**: Download `PLCN-macOS-x64.tar.gz`
- **Linux**: Download `PLCN-Linux-x64.tar.gz`

## Usage

### Quick Start

1. **Download and extract**: Download the latest release from the [Releases](https://github.com/MightyKartz/PLCN/releases) page.

2. **Grant execute permission** (macOS/Linux):

   ```bash
   # macOS, after extracting PLCN-macOS-x64.tar.gz
   chmod +x PLCN-macOS

   # Linux, after extracting PLCN-Linux-x64.tar.gz
   chmod +x PLCN-Linux
   ```

   > **macOS security note**: On first launch, if macOS reports that the developer cannot be verified, open **System Settings > Privacy & Security** and allow the app to open.

3. **Run the application**:
   - **Windows**: Double-click `PLCN-Windows-x64.exe` or run it from a terminal.
   - **macOS**: Double-click `PLCN-macOS` or run `./PLCN-macOS` from a terminal.
   - **Linux**: Run `./PLCN-Linux` from a terminal.

   The Web UI will open in your default browser.

### Web UI

1. **Scan device and folders**:
   - Choose a RetroArch root, a `playlists` folder, or a mounted SD-card/handheld RetroArch directory from the left-side device panel.
   - Use **Auto Detect** to scan common local/mounted locations. If an Android device has already granted ADB authorization, PLCN can also detect common paths such as `/sdcard/RetroArch`.
   - Use **Scan Directory** to detect the game-list directory, thumbnail directory, `retroarch.cfg`, and discovered `.lpl` files.
   - Selecting a game list fills the system, playlist path, and thumbnail directory automatically, then starts the preview flow.

2. **Configure paths and system**:
   - Single repair: manually choose one `.lpl` game list, a system such as `Sony - PlayStation`, and a thumbnail output directory.
   - Batch repair: choose a directory containing `.lpl` files and a thumbnail output directory.

3. **Preview and review**:
   - Generate a preview before applying changes.
   - Review original labels, proposed Chinese labels, thumbnail sources, and match status.
   - Uncheck rows you do not want to write back; unchecked rows are excluded from apply and download.

4. **Apply and download**:
   - Write confirmed labels back to the game list.
   - Download box art, gameplay snapshots, and title images.
   - Check progress logs, success/failure/skip statistics, and download details in the UI.

### Run from source

```bash
pip install -r requirements.txt

# Start the local Web UI with no arguments
python3 src/plcn.py

# Or start it explicitly
python3 src/plcn.py ui

# Process one game list from the CLI
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
- RetroArch directory scanning lives in `src/retroarch_scanner.py`; it currently supports shallow local/mounted scans and authorized ADB device scans. SSH/SFTP remote connections remain planned follow-up work.
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
