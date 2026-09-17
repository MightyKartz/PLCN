import ctypes
from types import SimpleNamespace

import pytest

from scripts.smoke_desktop_package import preserve_windows_shortcuts


def test_installer_shortcut_guard_restores_portable_install(tmp_path, monkeypatch):
    programs, desktop = tmp_path / 'Programs', tmp_path / 'Desktop'
    programs.mkdir()
    desktop.mkdir()
    shortcut = programs / 'PLCN/PLCN.lnk'
    shortcut.parent.mkdir()
    shortcut.write_bytes(b'original shortcut target and metadata')

    def get_folder(_window, folder_id, _token, _flags, buffer):
        buffer.value = str({2: programs, 16: desktop}[folder_id])
        return 0

    monkeypatch.setattr(ctypes, 'windll', SimpleNamespace(shell32=SimpleNamespace(SHGetFolderPathW=get_folder)), raising=False)
    with preserve_windows_shortcuts():
        pass
    with pytest.raises(AssertionError, match='restored originals'):
        with preserve_windows_shortcuts():
            shortcut.unlink()  # An uninstaller removed a pre-existing shortcut.
            (desktop / 'PLCN.lnk').write_bytes(b'unwanted new shortcut')
    assert shortcut.read_bytes() == b'original shortcut target and metadata'
    assert not (desktop / 'PLCN.lnk').exists()
