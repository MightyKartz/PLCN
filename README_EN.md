# PLCN

GitHub shows the Chinese README by default. To return to Chinese, open [README.md](README.md).

PLCN is a local RetroArch game-list localization and thumbnail matching tool. It currently runs as a Python CLI plus local Web UI: it reads `.lpl` game lists, proposes Chinese display names and standard English thumbnail sources from local data and Libretro databases, then writes the confirmed changes back and downloads matching artwork.

> Current implementation note: PLCN is an external local helper for RetroArch playlists and thumbnail folders. It is not an in-RetroArch plugin and does not modify RetroArch itself.

## Latest Version: v3.1.1

- Fixed regular ROM playlist scans where Chinese parent folders such as `gba中文游戏`, `中文游戏`, or `游戏合集` could be written as every game's display name.
- Fixed playlists already polluted by older versions: when the current label is a generic collection folder name, preview now repairs it from the ROM filename and database match.
- Adjusted matching priority so ROM filenames, valid existing labels, Libretro DAT evidence, and the local Chinese database win over generic Chinese collection folders.
- Preserved the v3.1 status-driven repair workbench, immediate cover-state refresh, separated **Write Name / Cover Source Name** fields, and FBNeo/Arcade matching improvements.
- Added regression coverage for GBA Chinese parent folders and polluted labels so a whole scanned list cannot collapse to one folder name again.

## Features

- **Game-list localization**: Reads RetroArch `.lpl` game lists and maps game labels to Chinese names.
- **RetroArch directory scanning**: The Web UI can scan local RetroArch roots, `playlists` folders, mounted device folders, and authorized ADB Android handhelds/devices, then list detected `.lpl` game lists.
- **Reviewable matching workbench**: The Web UI supports single-list and batch workflows with preview, row-level selection, change table, detail panel, progress logs, and real download summaries.
- **Smart thumbnail downloading**:
  - Attempts to recover the standard English game name even when the ROM filename or current label is Chinese.
  - Downloads `Named_Boxarts`, `Named_Snaps`, and `Named_Titles` from the official Libretro thumbnail server.
  - Uses `libretro-database` data to reduce naming mismatches and missing thumbnails.
  - Regular ROM playlists prioritize ROM filenames and database evidence so collection folders like `gba中文游戏` cannot overwrite every game's display name.
  - For FBNeo/Arcade games, PLCN now prioritizes the `.lpl` ROM path, zip short name, RetroArch `crc32` field, local zip-entry CRCs, and DAT checksum aliases to recover the standard title and reduce artwork-source errors caused by arcade short names.
  - PLCN remains local/offline-first and does not integrate the ScreenScraper/Skraper API; matching diagnostics explain whether a row came from a DAT hit, an unreadable ROM fingerprint, or manual-review fallback.
- **Batch processing**: Processes multiple `.lpl` game lists from one directory.
- **Local data cache**: Uses SQLite to cache translation and matching data.
- **Local manual overrides**: Manual corrections can be saved to the local `manual_overrides.json` file and prioritized in later previews.
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
   - Review current names, write names, cover source names, cover status, and repair status.
   - Uncheck rows you do not want to write back; unchecked rows are excluded from apply and download.
   - Edit uncertain write names or cover sources directly; once a row reaches an actionable status, add it to the apply queue.

4. **Apply and download**:
   - Write confirmed labels back to the game list.
   - Download box art, gameplay snapshots, and title images.
   - Check progress logs, success/failure/skip statistics, and download details in the UI.

### Local Data Note

- `manual_overrides.json` stays on this machine. If no path is configured, PLCN stores it in the launch directory; a local config can point it elsewhere.
- Each record stores system, ROM path/name, CRC, write name, cover source, and update time. Within the same system, CRC matches win first, then ROM filename matches.
- This file preserves manual corrections only; PLCN does not use cloud sync, online matching, or external scraping.

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
python3 -m pytest -q
python3 -m py_compile src/*.py
git diff --check
```

If you touch `src/templates/plcn.html`, also syntax-check its inline JavaScript; see [RELEASE_GUIDE.md](RELEASE_GUIDE.md) for the full pre-release check command.

## Credits & Acknowledgements

Special thanks to **yingw** for the comprehensive ROM name translation database:

- [rom-name-cn](https://github.com/yingw/rom-name-cn)

This project uses `rom-name-cn` data as the foundation for Chinese game-name translation.
