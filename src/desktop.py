"""No-console desktop entry; CLI remains available through retroarch_assistant.py."""
import argparse
import json
from pathlib import Path
import sys
import traceback

import app_paths
from app_brand import NAME
from native_dialog import PICK_KINDS


def webview2_available():
    import winreg

    key_path = r'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
    for hive, access in ((winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
                         (winreg.HKEY_CURRENT_USER, 0)):
        try:
            with winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ | access) as key:
                version, _ = winreg.QueryValueEx(key, 'pv')
        except FileNotFoundError:
            continue
        if version and version != '0.0.0.0':
            return True
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pick', choices=PICK_KINDS)
    parser.add_argument('--initial', default='')
    parser.add_argument('--result')
    parser.add_argument('--self-check', action='store_true')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--no-browser', action='store_true', help='Start the local service without opening a browser')
    mode.add_argument('--browser', action='store_true', help='Open the workbench in the default browser')
    mode.add_argument('--window', action='store_true', help='Require the standalone desktop window')
    args = parser.parse_args()
    if args.pick:
        from native_dialog import helper_pick
        try:
            data = {'path': helper_pick(args.pick, args.initial)}
        except Exception as error:
            data = {'error': str(error)}
        Path(args.result).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        return
    if args.self_check:
        import PIL.Image
        import tkinter
        import server
        import data_pack
        if sys.platform in ('darwin', 'win32') and getattr(sys, 'frozen', False):
            import webview
        assert (app_paths.resource_root() / 'src/templates/plcn.html').is_file()
        assert all((app_paths.resource_root() / 'src/templates' / name).is_file()
                   for name in server.UI_ASSETS)
        assert app_paths.default_source().is_dir()
        import hashlib
        dat_root = app_paths.resource_root() / 'data/libretro-db'
        for system, metadata in json.loads((dat_root / 'sources.json').read_text()).items():
            assert hashlib.sha256((dat_root / 'dat' / (system + '.dat')).read_bytes()).hexdigest() == metadata['sha256']
            assert hashlib.sha256((dat_root / 'supplemental' / (system + '.dat')).read_bytes()).hexdigest() == metadata['supplement_sha256']
        adb_version = None
        if getattr(sys, 'frozen', False):
            from adb_runtime import check_bundled_adb
            adb_version = check_bundled_adb()
            if sys.platform == 'darwin':
                import mtp_runtime
                mtp_runtime.library()
        app_paths.initialize()
        Path(app_paths.user_data_dir() / 'self-check.json').write_text(json.dumps({'ok': True, 'product': NAME, 'platform': sys.platform, 'adb_version': adb_version}), encoding='utf-8')
        return
    log_dir = app_paths.user_data_dir() / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / 'desktop.log'
    if not (app_paths.user_data_dir() / 'instance.json').exists() and log_path.exists() and log_path.stat().st_size > 5 * 1024 * 1024:
        log_path.replace(log_dir / 'desktop.previous.log')
    original_stdout, original_stderr = sys.stdout, sys.stderr
    with log_path.open('a', encoding='utf-8', buffering=1) as log:
        sys.stdout = sys.stderr = log
        try:
            use_window = args.window or (not (args.browser or args.no_browser) and sys.platform in ('darwin', 'win32'))
            if use_window and sys.platform == 'win32' and not webview2_available():
                if args.window:
                    raise RuntimeError('请安装 Microsoft Edge WebView2 Runtime，或使用 --browser 启动。')
                print('WebView2 Runtime unavailable; opening the default browser')
                use_window = False
            if use_window:
                from desktop_window import run_window
                run_window()
            else:
                import server
                server.run_server(open_browser=not args.no_browser)
        except Exception:
            traceback.print_exc()
            try:
                from tkinter import Tk, messagebox
                root = Tk()
                root.withdraw()
                messagebox.showerror('RetroArch 助手启动失败', f'请查看日志：{log_path}')
                root.destroy()
            except Exception:
                pass
        finally:
            sys.stdout, sys.stderr = original_stdout, original_stderr


if __name__ == '__main__':
    main()
