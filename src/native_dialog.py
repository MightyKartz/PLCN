"""Run file selection in a helper's main thread, never an HTTP worker thread."""
import json
import os
from pathlib import Path
import subprocess
import sys


PICK_KINDS = ('file', 'files', 'rom', 'directory', 'executable')


def helper_pick(kind, initial=''):
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    try:
        options = {'title': {'files':'RetroArch 助手 — 选择游戏文件', 'file':'RetroArch 助手 — 选择游戏列表', 'rom':'RetroArch 助手 — 选择新版 ROM','directory':'RetroArch 助手 — 选择目录','executable':'RetroArch 助手 — 选择 chdman 程序'}[kind]}
        # On macOS, a parent makes the native panel a sheet attached to that
        # window. Our hidden helper window has no usable on-screen position;
        # let macOS place a standalone panel instead of an off-screen sheet.
        if sys.platform != 'darwin':
            options['parent'] = root
        if initial and Path(initial).is_dir():
            options['initialdir'] = initial
        if kind == 'executable':
            return filedialog.askopenfilename(filetypes=[('chdman executable', '*')], **options)
        if kind == 'rom':
            return filedialog.askopenfilename(**options)
        if kind == 'file':
            return filedialog.askopenfilename(filetypes=[('RetroArch playlist', '*.lpl')], **options)
        if kind == 'files':
            return list(filedialog.askopenfilenames(**options))
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
