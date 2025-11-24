# PLCN

PLCN is a powerful tool designed for RetroArch users to automatically translate game names in playlists to Chinese and download matching thumbnails from the official Libretro server.

[中文说明 (Chinese Readme)](README.md)

## Features

- **Automatic Translation**: Translates game names in `.lpl` playlists to Chinese using a local database.
- **Smart Thumbnail Downloading**: 
  - Automatically identifies the standard English name of the game (even if the file is named in Chinese).
  - Downloads thumbnails (Boxart, Snap, Title) from the official Libretro server.
  - Fixes common naming issues (e.g., "Rage Racer" -> "Ridge Racer") using the official `libretro-database`.
- **Batch Processing**: Process multiple playlists at once.
- **Web UI**: User-friendly web interface for easy configuration and execution.
- **Cross-Platform**: Available for Windows, macOS, and Linux.

## Installation

Download the latest release for your platform from the [Releases](https://github.com/MightyKartz/PLCN/releases) page.

- **Windows**: Download `PLCN-Windows.exe`
- **macOS**: Download `PLCN-macOS`
- **Linux**: Download `PLCN-Linux`

## Usage

1. **Run the application**:
   - Windows: Double-click `PLCN-Windows.exe`.
   - macOS/Linux: Run `./PLCN-macOS` or `./PLCN-Linux` in the terminal.
   
   *Note: On first run, it will open a Web UI in your default browser.*

2. **Configure via Web UI**:
   - **Single Mode**: Select a single `.lpl` file, choose the system (e.g., `Sony - PlayStation`), and set the thumbnails directory.
   - **Batch Mode**: Select a directory containing multiple `.lpl` files to process them all.

3. **Start Processing**:
   - Click "Start Run" to begin.
   - View real-time logs in the browser window.

## Credits & Acknowledgements

Special thanks to **yingw** for the comprehensive ROM name translation database:
- [rom-name-cn](https://github.com/yingw/rom-name-cn)

This project uses the data from `rom-name-cn` to provide accurate Chinese translations for thousands of retro games.
