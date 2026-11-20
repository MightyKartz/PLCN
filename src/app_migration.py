"""Explicit, offline migration of an existing profile to the current directories."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import shutil
import tempfile

import app_paths
from app_runtime import InstanceLock
from safe_io import atomic_write_json


def migrate(source, cache_source=None):
    source = Path(source).expanduser().resolve()
    target = app_paths.user_data_dir().resolve()
    pairs = [(source, target)]
    if cache_source:
        cache_source = Path(cache_source).expanduser().resolve()
        if not cache_source.is_relative_to(source):
            pairs.append((cache_source, app_paths.cache_dir().resolve()))
    for old, new in pairs:
        if not old.is_dir():
            raise ValueError(f'Source directory does not exist: {old}')
        if new.exists():
            raise ValueError(f'Destination already exists; migration will not overwrite it: {new}')
        if any(new.is_relative_to(origin) or origin.is_relative_to(new) for origin, _ in pairs):
            raise ValueError('Source and destination directories must not overlap')

    def relocate(value):
        if isinstance(value, str):
            for old, new in pairs:
                if value == str(old) or value.startswith(str(old) + '/') or value.startswith(str(old) + '\\'):
                    return str(new) + value[len(str(old)):]
            return value
        if isinstance(value, list):
            return [relocate(item) for item in value]
        if isinstance(value, dict):
            return {relocate(key): relocate(item) for key, item in value.items()}
        return value

    with ExitStack() as resources:
        lock = InstanceLock(source)
        if not lock.acquire():
            raise ValueError(f'Quit the running application before migration: {source}')
        resources.callback(lock.close)
        staged = []
        for old, new in pairs:
            parent_stage = next(((stage, destination) for stage, destination in staged if new.is_relative_to(destination)), None)
            if parent_stage:
                stage = parent_stage[0] / new.relative_to(parent_stage[1])
            else:
                new.parent.mkdir(parents=True, exist_ok=True)
                temporary = Path(resources.enter_context(tempfile.TemporaryDirectory(prefix='.profile-migration-', dir=new.parent)))
                stage = temporary / 'profile'
            shutil.copytree(old, stage, ignore=shutil.ignore_patterns('instance.lock'))
            # Only live indexes and stored manifests change; file payloads retain
            # their exact bytes.
            documents = list(stage.glob('*.json')) + list((stage / 'history').glob('*.json'))
            documents += [p for p in stage.glob('*/*/manifest.json') if p.parts[-3] != 'packs']
            if old != source:
                documents += list(stage.glob('secondary-artwork/*.json'))
            for path in documents:
                if path.name == 'instance.json':
                    path.unlink()
                    continue
                original = json.loads(path.read_text(encoding='utf-8-sig'))
                updated = relocate(original)
                if updated != original:
                    atomic_write_json(path, updated)
            for database in stage.rglob('plcn.db*'):
                database.rename(database.with_name(database.name.replace('plcn.db', 'library.db', 1)))
            if not parent_stage:
                staged.append((stage, new))
        for stage, new in staged:
            stage.rename(new)
    # Both new directories are complete before removing either source.
    for old, _ in reversed(pairs):
        shutil.rmtree(old)
    return {'data_dir': str(target), 'cache_dir': str(app_paths.cache_dir())}


def main(argv=None):
    parser = argparse.ArgumentParser(prog='retroarch-assistant migrate', description=__doc__)
    parser.add_argument('--from', dest='source', required=True, help='Existing data directory (application must be closed)')
    parser.add_argument('--cache-from', help='Existing separate cache directory, if present')
    args = parser.parse_args(argv)
    try:
        result = migrate(args.source, args.cache_from)
    except (OSError, ValueError) as error:
        parser.exit(1, f'Migration failed: {error}\n')
    print(json.dumps(result, ensure_ascii=False))
