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

### Quick Start

1. **Download and Extract**: Download the latest release from the [Releases](https://github.com/MightyKartz/PLCN/releases) page.

2. **Grant Execute Permission** (macOS/Linux):
   ```bash
   # macOS
   chmod +x PLCN-macOS
   
   # Linux
   chmod +x PLCN-Linux
   ```
   
   > **macOS Security Note**: When running for the first time, if you see "cannot be opened because the developer cannot be verified", go to **System Preferences > Security & Privacy** and click "Open Anyway".

3. **Run the Application**:
   - **Windows**: Double-click `PLCN-Windows.exe` or run from command line
   - **macOS**: Double-click `PLCN-macOS` or run `./PLCN-macOS` in terminal
   - **Linux**: Run `./PLCN-Linux` in terminal
   
   The Web UI will automatically open in your default browser.

### Web Interface

1. **Configuration**:
   - **Single Mode**: Select a single `.lpl` file, choose the system (e.g., `Sony - PlayStation`), and set the thumbnails directory.
   - **Batch Mode**: Select a directory containing multiple `.lpl` files to process them all.

2. **Start Processing**:
   - Click "Start Run" to begin.
   - View real-time logs in the browser window.

## Credits & Acknowledgements

Special thanks to **yingw** for the comprehensive ROM name translation database:
- [rom-name-cn](https://github.com/yingw/rom-name-cn)

This project uses the data from `rom-name-cn` to provide accurate Chinese translations for thousands of retro games.
