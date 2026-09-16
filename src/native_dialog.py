"""Run file selection in a helper's main thread, never an HTTP worker thread."""
import json
import os
from pathlib import Path
import subprocess
import sys


def helper_pick(kind, initial=''):
    if kind not in {'file', 'directory'}:
        raise ValueError('Invalid picker type')
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    try:
        options = {'parent': root, 'title': 'PLCN — 选择游戏列表' if kind == 'file' else 'PLCN — 选择目录'}
        if initial and Path(initial).is_dir():
            options['initialdir'] = initial
        if kind == 'file':
            return filedialog.askopenfilename(filetypes=[('RetroArch playlist', '*.lpl')], **options)
        return filedialog.askdirectory(**options)
    finally:
        root.destroy()


def pick(kind, initial=''):
    from app_paths import cache_dir
    import tempfile
    # A no-console executable has no stdout. Exchange the result through a
    # private temporary JSON file, removed regardless of cancellation/failure.
    cache_dir().mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='picker-', dir=cache_dir()) as temporary:
        result = Path(temporary) / 'result.json'
        command = [sys.executable]
        if not getattr(sys, 'frozen', False):
            command.append(str(Path(__file__).with_name('desktop.py')))
        command.extend(['--pick', kind, '--initial', initial, '--result', str(result)])
        kwargs = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
        subprocess.run(command, check=True, timeout=300, **kwargs)
        data = json.loads(result.read_text(encoding='utf-8'))
        if data.get('error'):
            raise RuntimeError(data['error'])
        return data.get('path', '')
