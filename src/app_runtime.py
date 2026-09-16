"""OS-owned single-instance lock; a process crash releases ownership automatically."""
import json
import os
from pathlib import Path
import sys
import time
import urllib.parse

import requests

from safe_io import atomic_write_json


class InstanceLock:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.handle = None
        self.state_path = self.directory / 'instance.json'

    def acquire(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        self.handle = (self.directory / 'instance.lock').open('a+b')
        self.handle.seek(0, 2)
        if self.handle.tell() == 0:
            self.handle.write(b'0')
            self.handle.flush()
        self.handle.seek(0)
        try:
            if sys.platform == 'win32':
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            self.handle = None
            return False
        return True

    def publish(self, url, instance_id):
        atomic_write_json(self.state_path, {'url': url, 'instance_id': instance_id, 'pid': os.getpid()})

    def existing_url(self, attempts=25):
        for _ in range(attempts):
            try:
                state = json.loads(self.state_path.read_text(encoding='utf-8'))
                parsed = urllib.parse.urlparse(state['url'])
                if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port or parsed.path not in ('', '/'):
                    raise ValueError('Invalid local instance URL')
                with requests.Session() as session:
                    session.trust_env = False
                    session.get(state['url'], timeout=1).raise_for_status()
                    reply = session.get(state['url'] + '/api/instance', timeout=1).json()
                if reply['instance_id'] == state['instance_id']:
                    return state['url']
            except (OSError, ValueError, KeyError, requests.RequestException):
                time.sleep(.1)
        raise RuntimeError('PLCN 已在运行或正在启动，请稍后重试。日志位于用户数据目录。')

    def close(self):
        if self.handle:
            self.state_path.unlink(missing_ok=True)
            self.handle.close()
            self.handle = None
