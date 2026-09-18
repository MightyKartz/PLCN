# PLCN

GitHub shows the Chinese README by default. To return to Chinese, open [README.md](README.md).

PLCN is a local RetroArch game-list localization and artwork management tool. It reads `.lpl` playlists, proposes reviewable Chinese display names and official English artwork sources, then writes confirmed changes back and downloads box art, screenshots, and title images.

> PLCN is an external local helper. It does not modify RetroArch itself.

## Latest Release: v3.2.0

v3.2.0 combines device connection, game browsing, batch repair, and single-game artwork repair. At startup, choose a connected Android device, a recent folder, or a local directory. Selecting a system opens its current game list, and each row can repair missing or incorrect artwork from the official Libretro thumbnail library or a local image.

![Open a library](DOC/assets/library-home.png)

![Game library](DOC/assets/game-library.png)

![Single-game artwork repair](DOC/assets/artwork-dialog.png)

- The home page lists connected devices, recent folders, and local directories.
- The game list shows artwork, playlist name, ROM filename, and missing/problem image status.
- Single-game repair supports official-library search, local PNG/JPEG/WebP import, and renaming; it previews before writing and backs up replaced images.
- Artwork lookup follows RetroArch's ROM-filename-first matching order so PLCN and the handheld show the same image.
- Playlist and artwork writes use backups, snapshot checks, atomic replacement, and readback verification. ADB writes stage and verify remote files.
- Desktop packages are available for Windows, macOS Intel/Apple Silicon, and Linux. macOS/Windows builds are currently unsigned and may need a manual allowance on first launch.

## Features

- **Game-list localization**: Reads `.lpl` playlists and maps labels to Chinese names.
- **Device and folder scanning**: Scans local RetroArch roots, `playlists` folders, mounted SD cards, and authorized ADB Android devices.
- **Reviewable matching**: Previews write names, artwork source names, artwork status, and repair status; rows can be selected or edited individually.
- **Smart thumbnail downloads**: Downloads box art, screenshots, and title images from the official Libretro server, with naming-difference and FBNeo/Arcade alias handling.
- **Single-game artwork and naming**: Search the official library or import a local image from a game row.
- **Batch processing**: Processes multiple `.lpl` playlists from one directory.
- **Local cache and overrides**: Manual corrections stay in the local `manual_overrides.json` file.
- **Cross-platform packages**: Windows, macOS, and Linux builds.

## Installation

Download the latest release for your platform from [Releases](https://github.com/MightyKartz/PLCN/releases):

- **Windows**: `PLCN-Windows-x64.exe`
- **macOS**: `PLCN-macOS-x64.tar.gz`
- **Linux**: `PLCN-Linux-x64.tar.gz`

Users do not need Xcode, Node.js, or license commands. On Windows run the installer; on macOS extract and double-click; on Linux extract and run. Current macOS/Windows builds are unsigned, so the first launch may need a manual allowance in system security settings.

Release packages are built by GitHub Actions; running from source does not require a packaging environment.

## Usage

1. Start PLCN and choose a connected device, recent folder, or local directory.
2. Select a system to view its current game list; use search and missing-image filters to find games.
3. Use **Organize games** to preview batch name and artwork repairs, or open the artwork dialog for one game.
4. Confirm the write names and artwork sources, then apply; PLCN writes the playlist and downloads matching artwork.

## Run from source

For development or local verification; Xcode is not required:

```bash
pip install -r requirements.txt
python3 src/plcn.py
```

Release packages are built by GitHub Actions. A local Xcode license is only needed when a maintainer manually builds a macOS DMG on their own machine.

Single playlist from the command line:

```bash
python3 src/plcn.py   --playlist "/path/to/playlist.lpl"   --system "Sony - PlayStation"   --thumbnails-dir "/path/to/RetroArch/thumbnails"
```

Batch processing:

```bash
python3 src/plcn.py   --batch-dir "/path/to/playlists"   --thumbnails-dir "/path/to/RetroArch/thumbnails"
```

## Local data

- `manual_overrides.json` stays on the local machine and stores manual corrections.
- PLCN does not use cloud sync, online matching, or external scraping APIs; local data takes priority.
- See the [desktop guide](DOC/DESKTOP_GUIDE.md) for detailed operation.

## Development

```bash
python3 -m pytest -q
python3 -m compileall -q src
python3 scripts/check_ui_js.py
git diff --check
```

## Acknowledgements

Thanks to [rom-name-cn](https://github.com/yingw/rom-name-cn) for the ROM Chinese-name data.
