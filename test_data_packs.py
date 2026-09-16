import csv
import json
from pathlib import Path
import sqlite3
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent / 'src'))
from database import DatabaseManager
from data_pack import build_pack, validate_pack, activate_pack, rollback_pack, compare_packs, open_database


def source(tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    for system, cn in [('Nintendo - Game Boy', '掌机'), ('Nintendo - Game Boy Advance', '高级掌机')]:
        with (root / (system + '.csv')).open('w', encoding='utf-8', newline='') as handle:
            csv.writer(handle).writerows([['Name EN', 'Name CN'], ['Same Game', cn], ['Untranslated', '']])
    (root / 'README.md').write_text('upstream attribution', encoding='utf-8')
    return root


def test_pack_isolated_systems_blank_translations_and_read_only(tmp_path):
    root = source(tmp_path)
    pack = tmp_path / 'pack'
    manifest = build_pack(root, pack)
    assert manifest['systems']['Nintendo - Game Boy']['untranslated'] == 1
    db = open_database(pack / 'rom-name-cn')
    try:
        assert db.search_by_english('Same Game', 'Nintendo - Game Boy') == '掌机'
        assert db.search_by_english('Same Game', 'Nintendo - Game Boy Advance') == '高级掌机'
        assert db.search_by_normalized_alias('samegame', 'Nintendo - Game Boy') == ('掌机', 'Same Game')
        assert not db.search_by_english('Untranslated', 'Nintendo - Game Boy')
        with pytest.raises(sqlite3.OperationalError):
            db.get_connection().execute('DELETE FROM translations')
    finally:
        db.close()
    assert (pack / 'rom-name-cn' / 'README.md').read_text() == 'upstream attribution'
    validate_pack(pack)


def test_tampering_rejected_before_activation(tmp_path):
    pack = tmp_path / 'pack'
    build_pack(source(tmp_path), pack)
    (pack / 'catalog.sqlite3').write_bytes(b'broken')
    with pytest.raises(ValueError, match='校验失败'):
        activate_pack(pack, tmp_path / 'config.json')
    assert not (tmp_path / 'config.json').exists()


def test_update_compare_and_rollback_preserve_config(tmp_path):
    root = source(tmp_path)
    before, after = tmp_path / 'before', tmp_path / 'after'
    build_pack(root, before)
    with (root / 'Nintendo - Game Boy.csv').open('a', encoding='utf-8') as handle:
        handle.write('New Game,新游戏\n')
    build_pack(root, after)
    assert compare_packs(before, after) == {'added': 1, 'removed': 0, 'changed': 0, 'untranslated': 2}
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'rom_name_cn_path': str(root), 'manual_overrides_path': 'mine.json'}))
    activate_pack(before, config)
    activate_pack(after, config)
    rollback_pack(config)
    restored = json.loads(config.read_text())
    assert restored['rom_name_cn_path'] == str(before / 'rom-name-cn')
    assert restored['manual_overrides_path'] == 'mine.json'


def test_legacy_database_migration_keeps_data_and_backup(tmp_path):
    path = tmp_path / 'legacy.db'
    conn = sqlite3.connect(path)
    conn.executescript("CREATE TABLE translations (id INTEGER PRIMARY KEY AUTOINCREMENT, english_name TEXT NOT NULL UNIQUE, chinese_name TEXT NOT NULL, system TEXT); CREATE TABLE aliases (id INTEGER PRIMARY KEY, alias TEXT, english_name TEXT, normalized_alias TEXT); INSERT INTO translations VALUES(1, 'Same', 'Old', 'NES'); INSERT INTO aliases VALUES(1, 'Same', 'Same', 'same');")
    conn.close()
    db = DatabaseManager(str(path))
    try:
        conn = db.get_connection()
        conn.execute("INSERT INTO translations(english_name, chinese_name, system) VALUES('Same', 'New', 'SNES')")
        conn.commit()
        assert db.search_by_english('Same', 'NES') == 'Old'
        assert db.search_by_normalized_alias('same', 'NES') == ('Old', 'Same')
        assert db.search_by_normalized_alias('same', 'SNES') == (None, None)
        assert conn.execute("SELECT count(*) FROM translations_fts WHERE translations_fts MATCH 'Same'").fetchone()[0] == 2
    finally:
        db.close()
    assert len(list(tmp_path.glob('legacy.db.bak-schema1-*'))) == 1


def test_changed_source_rebuilds_cache(tmp_path):
    root = source(tmp_path)
    cache = str(tmp_path / 'cache.db')
    db = open_database(root, cache)
    db.close()
    file = root / 'Nintendo - Game Boy.csv'
    file.write_text('Name EN,Name CN\nReplacement,新记录\n', encoding='utf-8')
    db = open_database(root, cache)
    try:
        assert db.search_by_english('Replacement', 'Nintendo - Game Boy') == '新记录'
        assert db.search_by_english('Same Game', 'Nintendo - Game Boy') is None
    finally:
        db.close()


def test_default_cache_keeps_existing_job_on_its_source_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(DatabaseManager, 'DB_FILE', str(tmp_path / 'runtime' / 'plcn.db'))
    root = source(tmp_path)
    first = open_database(root)
    (root / 'Nintendo - Game Boy.csv').write_text('Name EN,Name CN\nSame Game,修改后\n', encoding='utf-8')
    second = open_database(root)
    try:
        assert first.db_path != second.db_path
        assert first.search_by_english('Same Game', 'Nintendo - Game Boy') == '掌机'
        assert second.search_by_english('Same Game', 'Nintendo - Game Boy') == '修改后'
    finally:
        first.close()
        second.close()


def test_region_alias_collision_is_ambiguous_and_search_keeps_candidates(tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    (root / 'NES.csv').write_text('Name EN,Name CN\nGame (USA),同名游戏\nGame (Japan),同名游戏\n', encoding='utf-8')
    db = open_database(root, str(tmp_path / 'catalog.db'))
    try:
        assert db.search_by_normalized_alias('game', 'NES') == (None, None)
        assert db.search_by_chinese('同名游戏', 'NES') is None
        assert {row['english_name'] for row in db.search_by_keyword('同名游戏', system='NES')} == {'Game (USA)', 'Game (Japan)'}
    finally:
        db.close()
