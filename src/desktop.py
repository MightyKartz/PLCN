"""No-console desktop entry; CLI remains available through plcn.py."""
import argparse
import json
from pathlib import Path
import sys
import traceback

import app_paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pick', choices=['file', 'directory'])
    parser.add_argument('--initial', default='')
    parser.add_argument('--result')
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--no-browser', action='store_true', help='Start the local service without opening a browser')
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
        assert (app_paths.resource_root() / 'src/templates/plcn.html').is_file()
        assert app_paths.default_source().is_dir()
        app_paths.initialize()
        Path(app_paths.user_data_dir() / 'self-check.json').write_text(json.dumps({'ok': True, 'platform': sys.platform}), encoding='utf-8')
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
            import server
            server.run_server(open_browser=not args.no_browser)
        except Exception:
            traceback.print_exc()
            try:
                from tkinter import Tk, messagebox
                root = Tk()
                root.withdraw()
                messagebox.showerror('PLCN 启动失败', f'请查看日志：{log_path}')
                root.destroy()
            except Exception:
                pass
        finally:
            sys.stdout, sys.stderr = original_stdout, original_stderr


if __name__ == '__main__':
    main()
