# PLCN

[中文](README.md) · [Download](https://github.com/MightyKartz/PLCN/releases/latest)

Manage RetroArch playlist names and artwork in a local browser UI. Launch the desktop package with a double click; Python, Node.js and Xcode are not required.

## Install

Download a **Release asset**, not the Source code archive. Public downloads do not require a GitHub account.

| Platform | Asset | Launch |
|---|---|---|
| Windows 10/11 x64 | `PLCN-Windows-x64-Setup.exe` | Install, then open from Start |
| Windows portable | `PLCN-Windows-x64-Portable.zip` | Extract everything, open `PLCN.exe` |
| Apple Silicon Mac | `PLCN-macOS-arm64.dmg` | Drag PLCN to Applications, then open |
| Intel Mac | `PLCN-macOS-x64.dmg` | Same as above |
| Linux x64 CLI | `PLCN-Linux-x64.tar.gz` | Extract, run `./plcn --help` |

GitHub-built Windows/macOS packages currently have no distribution certificate signature; macOS builds are not notarized. System security may block first launch. Consult [Apple](https://support.apple.com/102445) or [Microsoft](https://support.microsoft.com/en-us/windows/security/threat-malware-protection/smart-app-control-frequently-asked-questions). Corporate policies and Smart App Control can prevent execution; disabling protection is not recommended.

Starting with v3.2.4, Windows/macOS packages include ADB. Android USB access still requires USB debugging and authorization on the device; some Windows devices require vendor drivers. Local folders and SD cards do not require ADB.

## Use

1. Open a connected device or a local RetroArch/playlists folder.
2. Select a system and browse games. Repair artwork individually or use bulk preview.
3. Review and apply changes. Quit RetroArch before writing to avoid stale playlist overwrites.

Artwork searches prioritize Libretro, with alternate-source previews and local import available. Source and edition hints are shown before confirmation. Writes remove matching raw-disc companion entries such as CUE/BIN, without deleting ROM files or merging editions/discs just because their translated labels match.

Settings and recovery data remain local. Artwork searches/downloads use the network; ROMs are not uploaded. See [desktop guide](DOC/DESKTOP_GUIDE.md).

## Development

```sh
pip install -r requirements.txt
python3 src/plcn.py
python3 -m pytest -q
python3 scripts/check_ui_js.py
```

CI builds on each target OS and checks bundled resources/ADB, service lifecycle, isolated profiles and installation. These checks do not certify every OS security policy or USB device.

Thanks to [rom-name-cn](https://github.com/yingw/rom-name-cn) and [Libretro](https://www.libretro.com/). ADB notices ship in `platform-tools/NOTICE.txt`.
