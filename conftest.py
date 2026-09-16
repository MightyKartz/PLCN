"""Run regression tests with isolated caches and small, deterministic DAT data."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / 'src'))


@pytest.fixture(scope='session')
def local_test_data(tmp_path_factory):
    root = tmp_path_factory.mktemp('plcn-data')
    games = [
        ('aof3', 'Art of Fighting 3 - The Path of the Warrior / Art of Fighting - Ryuuko no Ken Gaiden', '0A015CAC'),
        ('s1945', 'Strikers 1945 (World)', '11111111'),
        ('s1945ii', 'Strikers 1945 II', '22222222'),
        ('s1945p', 'Strikers 1945 Plus', '33333333'),
    ]
    dat = '\n'.join(f'game (\n name "{short}"\n description "{title}"\n rom ( name "{short}.zip" crc {crc} )\n)' for short, title, crc in games)
    (root / 'FBNeo - Arcade Games.dat').write_text(dat, encoding='utf-8')
    return root


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch, local_test_data):
    from database import DatabaseManager
    from libretro_db import LibretroDB
    monkeypatch.setattr(DatabaseManager, 'DB_FILE', str(local_test_data / 'plcn.db'))
    monkeypatch.setattr(LibretroDB, 'get_dat_path', lambda self, name: str(local_test_data / (name + '.dat')))
    monkeypatch.setattr(LibretroDB, 'download_dat', lambda *args, **kwargs: False)
