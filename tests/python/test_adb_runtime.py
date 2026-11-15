from pathlib import Path
import pytest
import adb_runtime as adb


def test_bundle_wins_over_system_path(tmp_path, monkeypatch):
    monkeypatch.setattr(adb.app_paths, 'resource_root', lambda: tmp_path)
    path = adb.bundled_adb()
    path.parent.mkdir()
    path.write_bytes(b'fixture')
    monkeypatch.setattr(adb.shutil, 'which', lambda _: '/unrelated/adb')
    assert adb.adb_executable() == str(path)
    assert adb.adb_available()


def test_frozen_package_cannot_hide_missing_adb_with_host_install(tmp_path, monkeypatch):
    monkeypatch.setattr(adb.app_paths, 'resource_root', lambda: tmp_path)
    monkeypatch.setattr(adb.sys, 'platform', 'darwin')
    monkeypatch.setattr(adb.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(adb.shutil, 'which', lambda _: '/unrelated/adb')
    with pytest.raises(FileNotFoundError):
        adb.adb_executable()


def test_empty_macos_usb_enumeration_means_no_devices(monkeypatch):
    from types import SimpleNamespace
    import adb_runtime
    monkeypatch.setattr(adb_runtime.sys,'platform','darwin')
    monkeypatch.setattr(adb_runtime.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(stdout=b'',returncode=0))
    assert adb_runtime.usb_android_devices()==[]
