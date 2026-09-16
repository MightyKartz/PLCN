import sqlite3
import os
import csv
import glob
import json
import re
from contextlib import nullcontext, closing
from pathlib import Path
from safe_io import file_lock

class DatabaseManager:
    DB_FILE = os.path.join('.plcn_runtime', 'plcn.db')
    
    
    # System mappings for known discrepancies
    SYSTEM_MAPPINGS = {
        # NEC
        "NEC - PC Engine - TurboGrafx 16": ["NEC - PC Engine - TurboGrafx-16"],
        "NEC - PC Engine CD - TurboGrafx-CD": ["NEC - PC Engine CD & TurboGrafx CD"], # Map CD to standard PCE CSV
        
        # Sega
        "Sega - Mega Drive - Genesis": ["Sega - Mega Drive - Genesis"],
        "Sega - Mega-CD - Sega CD": ["Sega - Mega CD & Sega CD"],
        "Sega - Saturn": ["Sega - Saturn"],
        "Sega - Dreamcast": ["Sega - Dreamcast"],
        "Sega - Game Gear": ["Sega - Game Gear"],
        
        # Nintendo
        "Nintendo - Game Boy Advance": ["Nintendo - Game Boy Advance"],
        "Nintendo - Game Boy Color": ["Nintendo - Game Boy Color"],
        "Nintendo - Game Boy": ["Nintendo - Game Boy"],
        "Nintendo - Nintendo Entertainment System": ["Nintendo - Nintendo Entertainment System"],
        "Nintendo - Super Nintendo Entertainment System": ["Nintendo - Super Nintendo Entertainment System"],
        "Nintendo - GameCube": ["Nintendo - GameCube"],
        "Nintendo - Nintendo 64": ["Nintendo - Nintendo 64"],
        "Nintendo - Wii": ["Nintendo - Wii"],
        "Nintendo - Wii U": ["Nintendo - Wii U"],
        
        # Sony
        "Sony - PlayStation": ["Sony - PlayStation"],
        "Sony - PlayStation Portable": ["Sony - PlayStation Portable"],
        
        # Arcade
        "Arcade": ["FBNeo - Arcade Games", "MAME", "Arcade - CPS1", "Arcade - CPS2", "Arcade - CPS3", "Arcade - NEOGEO"],
        "FBNeo - Arcade Games": ["FBNeo - Arcade Games", "Arcade - CPS1", "Arcade - CPS2", "Arcade - CPS3", "Arcade - NEOGEO"],
        "MAME": ["MAME", "Arcade - CPS1", "Arcade - CPS2", "Arcade - CPS3", "Arcade - NEOGEO"],
        "SNK - Neo Geo": ["Arcade - NEOGEO"]
    }

    def __init__(self, db_path=None, read_only=False):
        self.read_only = read_only
        if db_path:
            self.db_path = db_path
        else:
            # Default to same directory as config or executable
            base_path = os.getcwd()
            self.db_path = os.path.join(base_path, self.DB_FILE)
        
        self.conn = None
        if not read_only:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.english_names_cache = None
        self.chinese_names_cache = None
        if not read_only:
            self.init_db()
    
    def expand_system_mapping(self, system):
        """
        Expands a system name to a list of systems to search.
        If system is in SYSTEM_MAPPINGS, returns the mapped list.
        Otherwise, returns a list with just the original system.
        """
        if not system:
            return []
        
        # Check if system matches a mapped system (with or without timestamp suffix)
        base_system = system.split('(')[0].strip()
        
        if base_system in self.SYSTEM_MAPPINGS:
            systems = list(self.SYSTEM_MAPPINGS[base_system])
        else:
            systems = [system]
            
        return systems

    def get_connection(self):
        if self.conn is None:
            self.conn = sqlite3.connect(Path(self.db_path).resolve().as_uri() + '?mode=ro' if self.read_only else self.db_path, uri=self.read_only, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.conn.create_function("system_base", 1, lambda value: re.sub(r"\s*\(\d{8}-\d{6}\).*$", "", value or "").strip())
        return self.conn

    def init_db(self):
        """Initialize the database schema."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        migrated = self._migrate_schema(conn)

        # Main translation table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS translations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                english_name TEXT NOT NULL,
                chinese_name TEXT NOT NULL,
                system TEXT NOT NULL DEFAULT '',
                UNIQUE(system, english_name)
            )
        ''')
        
        # Table: aliases
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alias TEXT NOT NULL,
                english_name TEXT NOT NULL,
                normalized_alias TEXT NOT NULL,
                system TEXT,
                UNIQUE(system, alias, english_name, normalized_alias)
            )
        ''')
        
        # Indexes for speed
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_translations_english ON translations(english_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_translations_chinese ON translations(chinese_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_aliases_normalized ON aliases(normalized_alias)')
        
        # FTS Table (Virtual Table)
        try:
            cursor.execute('''
                CREATE VIRTUAL TABLE IF NOT EXISTS translations_fts USING fts5(english_name, chinese_name, content='translations', content_rowid='id')
            ''')
            
            # Triggers to keep FTS in sync
            cursor.execute('''
                CREATE TRIGGER IF NOT EXISTS translations_ai AFTER INSERT ON translations BEGIN
                  INSERT INTO translations_fts(rowid, english_name, chinese_name) VALUES (new.id, new.english_name, new.chinese_name);
                END;
            ''')
            cursor.execute('''
                CREATE TRIGGER IF NOT EXISTS translations_ad AFTER DELETE ON translations BEGIN
                  INSERT INTO translations_fts(translations_fts, rowid, english_name, chinese_name) VALUES('delete', old.id, old.english_name, old.chinese_name);
                END;
            ''')
            cursor.execute('''
                CREATE TRIGGER IF NOT EXISTS translations_au AFTER UPDATE ON translations BEGIN
                  INSERT INTO translations_fts(translations_fts, rowid, english_name, chinese_name) VALUES('delete', old.id, old.english_name, old.chinese_name);
                  INSERT INTO translations_fts(rowid, english_name, chinese_name) VALUES (new.id, new.english_name, new.chinese_name);
                END;
            ''')
        except sqlite3.OperationalError:
            print("Warning: FTS5 not supported by this SQLite version. Manual search might be slower.")

        if migrated:
            try:
                conn.execute("INSERT INTO translations_fts(translations_fts) VALUES('rebuild')")
            except sqlite3.OperationalError:
                pass
        conn.execute('PRAGMA user_version=2')
        conn.commit()

    def _migrate_schema(self, conn):
        existing = conn.execute("SELECT sql FROM sqlite_master WHERE name='translations'").fetchone()
        if not existing or 'english_name TEXT NOT NULL UNIQUE' not in existing[0]:
            return
        with file_lock(self.db_path):
            from datetime import datetime
            backup = self.db_path + '.bak-schema1-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            with closing(sqlite3.connect(backup)) as target:
                conn.backup(target)
            with conn:
                conn.execute('BEGIN IMMEDIATE')
                for trigger in ['translations_ai', 'translations_ad', 'translations_au']:
                    conn.execute('DROP TRIGGER IF EXISTS ' + trigger)
                conn.execute('DROP TABLE IF EXISTS translations_fts')
                conn.execute("CREATE TABLE translations_v2 (id INTEGER PRIMARY KEY AUTOINCREMENT, english_name TEXT NOT NULL, chinese_name TEXT NOT NULL, system TEXT NOT NULL DEFAULT '', UNIQUE(system, english_name))")
                conn.execute("INSERT INTO translations_v2 SELECT id, english_name, chinese_name, COALESCE(system, '') FROM translations")
                alias_exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='aliases'").fetchone()
                if alias_exists:
                    conn.execute('CREATE TABLE aliases_v2 (id INTEGER PRIMARY KEY AUTOINCREMENT, alias TEXT NOT NULL, english_name TEXT NOT NULL, normalized_alias TEXT NOT NULL, system TEXT, UNIQUE(system, alias, english_name, normalized_alias))')
                    conn.execute('INSERT OR IGNORE INTO aliases_v2 SELECT a.id, a.alias, a.english_name, a.normalized_alias, t.system FROM aliases a JOIN translations_v2 t ON a.english_name=t.english_name')
                    conn.execute('DROP TABLE aliases')
                    conn.execute('ALTER TABLE aliases_v2 RENAME TO aliases')
                conn.execute('DROP TABLE translations')
                conn.execute('ALTER TABLE translations_v2 RENAME TO translations')
            print(f'Database migrated; backup: {backup}')
            return True

    def import_csvs(self, rom_name_cn_path, commit=True):
        """Import complete records without inventing translations for blank fields."""
        from itertools import chain
        conn = self.get_connection()
        count = 0
        self.english_names_cache = self.chinese_names_cache = None
        with conn if commit else nullcontext():
            for csv_file in sorted(Path(rom_name_cn_path).glob('*.csv')):
                system = re.sub(r'\s*\(\d{8}-\d{6}\).*$', '', csv_file.stem).strip()
                with csv_file.open(encoding='utf-8-sig', newline='') as handle:
                    reader = csv.reader(handle)
                    first = next(reader, [])
                    if not first:
                        continue
                    arcade = len(first) >= 3 and 'mame' in first[0].lower()
                    header = first[0].strip() == 'Name EN' or arcade
                    for row in reader if header else chain([first], reader):
                        if not row or not row[0].strip() or row[0].startswith('#'):
                            continue
                        if len(row) < (3 if arcade else 2):
                            raise ValueError(f'Malformed CSV row: {csv_file.name}:{reader.line_num}')
                        english, chinese = (row[1].strip(), row[2].strip()) if arcade else (row[0].strip(), row[1].strip())
                        if not english:
                            continue
                        conn.execute('INSERT INTO translations (english_name, chinese_name, system) VALUES (?, ?, ?) ON CONFLICT(system, english_name) DO UPDATE SET chinese_name=excluded.chinese_name', (english, chinese, system))
                        conn.execute('DELETE FROM aliases WHERE english_name=? AND system=?', (english, system))
                        for alias in dict.fromkeys([english, row[0].strip()] if arcade else [english]):
                            conn.execute('INSERT INTO aliases (alias, english_name, normalized_alias, system) VALUES (?, ?, ?, ?)', (alias, english, self.normalize_name(alias), system))
                        count += 1
        print(f'Imported {count} records into database.')
        return count

    def normalize_name(self, name):
        """
        Normalizes a game name for fuzzy matching.
        Duplicated from Translator to ensure consistency in DB generation.
        """
        import re
        # Strategy 1: Aggressive
        name_clean = re.sub(r'\[.*?\]', '', name)
        name_clean = re.sub(r'\(.*?\)', '', name_clean)
        name_clean = re.sub(r'\bCN\b', '', name_clean, flags=re.IGNORECASE)
        name_clean = name_clean.replace('_', ' ').replace('.', ' ')
        clean_name = re.sub(r'[^a-zA-Z0-9]', '', name_clean).lower()
        
        if clean_name:
            return clean_name
            
        # Strategy 2: Fallback
        name_fallback = name.replace('[', ' ').replace(']', ' ').replace('(', ' ').replace(')', ' ')
        name_fallback = re.sub(r'\bCN\b', '', name_fallback, flags=re.IGNORECASE)
        name_fallback = name_fallback.replace('_', ' ').replace('.', ' ')
        clean_name_fallback = re.sub(r'[^a-zA-Z0-9]', '', name_fallback).lower()
        
        return clean_name_fallback

    def search_by_english(self, english_name, system=None):
        cursor = self.get_connection().cursor()
        if system:
            systems = self.expand_system_mapping(system)
            if len(systems) > 1:
                # Multiple systems: use OR condition
                placeholders = ' OR '.join(['system_base(system) = ?' for _ in systems])
                query = f'SELECT chinese_name FROM translations WHERE english_name = ? AND ({placeholders})'
                params = [english_name] + [s for s in systems]
                cursor.execute(query, params)
            else:
                cursor.execute('SELECT chinese_name FROM translations WHERE english_name = ? AND system_base(system) = ?', (english_name, systems[0]))
        else:
            cursor.execute('SELECT chinese_name FROM translations WHERE english_name = ?', (english_name,))
        names = {row['chinese_name'] for row in cursor.fetchall()}
        return next(iter(names)) if len(names) == 1 else None

    def search_by_chinese(self, chinese_name, system=None):
        cursor = self.get_connection().cursor()
        if system:
            systems = self.expand_system_mapping(system)
            if len(systems) > 1:
                # Multiple systems: use OR condition
                placeholders = ' OR '.join(['system_base(system) = ?' for _ in systems])
                query = f'SELECT english_name FROM translations WHERE chinese_name = ? AND ({placeholders})'
                params = [chinese_name] + [s for s in systems]
                print(f"      DB Query: chinese_name='{chinese_name}', systems={systems}")
                cursor.execute(query, params)
            else:
                print(f"      DB Query: chinese_name='{chinese_name}', system LIKE '{systems[0]}%'")
                cursor.execute('SELECT english_name FROM translations WHERE chinese_name = ? AND system_base(system) = ?', (chinese_name, systems[0]))
        else:
            cursor.execute('SELECT english_name FROM translations WHERE chinese_name = ?', (chinese_name,))
        names = {row['english_name'] for row in cursor.fetchall()}
        result = next(iter(names)) if len(names) == 1 else None
        if result:
            print(f"      DB Result: Found '{result}'")
        else:
            print(f"      DB Result: No match")
        return result

    def search_by_normalized_alias(self, normalized_name, system=None):
        cursor = self.get_connection().cursor()
        # Join to get chinese name directly
        if system:
            systems = self.expand_system_mapping(system)
            if len(systems) > 1:
                # Multiple systems: use OR condition
                placeholders = ' OR '.join(['system_base(t.system) = ?' for _ in systems])
                query = f'''
                    SELECT t.chinese_name, t.english_name 
                    FROM aliases a
                    JOIN translations t ON a.english_name = t.english_name
                    AND (a.system = t.system OR (a.system IS NULL AND (SELECT COUNT(*) FROM translations u WHERE u.english_name=a.english_name)=1))
                    WHERE a.normalized_alias = ? AND ({placeholders})
                '''
                params = [normalized_name] + [s for s in systems]
                cursor.execute(query, params)
            else:
                query = '''
                    SELECT t.chinese_name, t.english_name 
                    FROM aliases a
                    JOIN translations t ON a.english_name = t.english_name
                    AND (a.system = t.system OR (a.system IS NULL AND (SELECT COUNT(*) FROM translations u WHERE u.english_name=a.english_name)=1))
                    WHERE a.normalized_alias = ? AND system_base(t.system) = ?
                '''
                cursor.execute(query, (normalized_name, systems[0]))
        else:
            query = '''
                SELECT t.chinese_name, t.english_name 
                FROM aliases a
                JOIN translations t ON a.english_name = t.english_name
                    AND (a.system = t.system OR (a.system IS NULL AND (SELECT COUNT(*) FROM translations u WHERE u.english_name=a.english_name)=1))
                WHERE a.normalized_alias = ?
            '''
            cursor.execute(query, (normalized_name,))
        matches = {(row['chinese_name'], row['english_name']) for row in cursor.fetchall()}
        # Removing region/version tags can collapse distinct releases. Such a
        # match is a candidate, never a deterministic identity lookup.
        return next(iter(matches)) if len(matches) == 1 else (None, None)

    def fuzzy_search_by_english(self, query, threshold=50, system=None):
        """
        Fuzzy search for English name in the database using normalized matching.
        Returns the Chinese name if a match is found with score >= threshold.
        
        Uses normalized names (alphanumeric only, lowercase) to better handle
        variations like "1943kai" vs "1943 Kai" or "metalslug" vs "Metal Slug".
        """
        try:
            from rapidfuzz import process, fuzz
        except ImportError:
            print("rapidfuzz not installed, skipping fuzzy search")
            return None

        # Build candidates list (optionally filtered by system)
        cursor = self.get_connection().cursor()
        if system:
            systems = self.expand_system_mapping(system)
            if len(systems) > 1:
                placeholders = ' OR '.join(['system_base(system) = ?' for _ in systems])
                query_sql = f'SELECT english_name, chinese_name FROM translations WHERE {placeholders}'
                params = [s for s in systems]
                cursor.execute(query_sql, params)
            else:
                cursor.execute('SELECT english_name, chinese_name FROM translations WHERE system_base(system) = ?', (systems[0],))
        else:
            cursor.execute('SELECT english_name, chinese_name FROM translations')
        
        candidates = [(row[0], row[1]) for row in cursor.fetchall()]
        
        if not candidates:
            return None
        
        # Normalize query
        norm_query = self.normalize_name(query)
        
        # Create mapping: normalized_name -> (original_english, chinese)
        norm_map = {}
        for eng, cn in candidates:
            norm_eng = self.normalize_name(eng)
            if norm_eng not in norm_map:
                norm_map[norm_eng] = (eng, cn)
        
        # Fuzzy match on normalized names
        norm_candidates = list(norm_map.keys())
        result = process.extractOne(norm_query, norm_candidates, scorer=fuzz.ratio)
        
        if result:
            match_norm, score, _ = result
            if score >= threshold:
                original_eng, chinese = norm_map[match_norm]
                print(f"Fuzzy match found: '{query}' (norm: '{norm_query}') -> '{original_eng}' (norm: '{match_norm}') (Score: {score})")
                return chinese
        
        return None

    def fuzzy_search_by_chinese(self, query, threshold=65, system=None):
        """
        Fuzzy search for Chinese name in the database.
        Returns the English name if a match is found with score >= threshold.
        """
        try:
            from rapidfuzz import process, fuzz
        except ImportError:
            print("rapidfuzz not installed, skipping fuzzy search")
            return None

        # Build candidates list (optionally filtered by system)
        cursor = self.get_connection().cursor()
        if system:
            systems = self.expand_system_mapping(system)
            if len(systems) > 1:
                placeholders = ' OR '.join(['system_base(system) = ?' for _ in systems])
                query_sql = f'SELECT chinese_name FROM translations WHERE {placeholders}'
                params = [s for s in systems]
                cursor.execute(query_sql, params)
            else:
                cursor.execute('SELECT chinese_name FROM translations WHERE system_base(system) = ?', (systems[0],))
        else:
            cursor.execute('SELECT chinese_name FROM translations')
        
        candidates = [row[0] for row in cursor.fetchall()]
        
        if not candidates:
            return None
            
        # Extract best match
        # WRatio handles partial matches and other heuristics better for mixed content
        result = process.extractOne(query, candidates, scorer=fuzz.WRatio)
        
        if result:
            match, score, _ = result
            if score >= threshold:
                print(f"Fuzzy match (CN) found: '{query}' -> '{match}' (Score: {score})")
                english_name = self.search_by_chinese(match, system=system)
                return (match, english_name) if english_name else None
        
        return None

    def search_by_keyword(self, keyword, limit=20, system=None):
        """
        Search for games by keyword using fuzzy matching only.
        Optionally filter by system.
        """
        try:
            from rapidfuzz import process, fuzz
        except ImportError:
            print("rapidfuzz not installed, skipping search")
            return []

        cursor = self.get_connection().cursor()
        results = []
        
        # Determine if keyword is Chinese or English
        is_chinese = any(ord(c) >= 128 for c in keyword)
        
        print(f"DEBUG search_by_keyword: keyword='{keyword}', system='{system}', is_chinese={is_chinese}")
        
        if is_chinese:
            # Build Chinese names cache (optionally filtered by system)
            if system:
                systems = self.expand_system_mapping(system)
                if len(systems) > 1:
                    placeholders = ' OR '.join(['system_base(system) = ?' for _ in systems])
                    query = f'SELECT chinese_name, english_name, system FROM translations WHERE {placeholders}'
                    params = [s for s in systems]
                    cursor.execute(query, params)
                else:
                    cursor.execute('SELECT chinese_name, english_name, system FROM translations WHERE system_base(system) = ?', (systems[0],))
            else:
                cursor.execute('SELECT chinese_name, english_name, system FROM translations')
            
            candidates = [(row[0], row[1], row[2]) for row in cursor.fetchall()]
            chinese_names = [c[0] for c in candidates]
            
            print(f"DEBUG search_by_keyword: Found {len(candidates)} candidates")
            
            if not chinese_names:
                return []
            
            # Fuzzy search on Chinese names
            matches = process.extract(keyword, chinese_names, scorer=fuzz.WRatio, limit=limit)
            
            print(f"DEBUG search_by_keyword: Top 5 matches: {matches[:5]}")
            
            # Build results from matches
            for match_name, score, candidate_index in matches:
                if score >= 65:  # Use threshold (lowered from 70)
                    cn, en, matched_system = candidates[candidate_index]
                    results.append({
                        'chinese_name': cn,
                        'english_name': en,
                        'system': matched_system
                    })
        else:
            # Build English names cache (optionally filtered by system)
            if system:
                systems = self.expand_system_mapping(system)
                if len(systems) > 1:
                    placeholders = ' OR '.join(['system_base(system) = ?' for _ in systems])
                    query = f'SELECT english_name, chinese_name, system FROM translations WHERE {placeholders}'
                    params = [s for s in systems]
                    cursor.execute(query, params)
                else:
                    cursor.execute('SELECT english_name, chinese_name, system FROM translations WHERE system_base(system) = ?', (systems[0],))
            else:
                cursor.execute('SELECT english_name, chinese_name, system FROM translations')
            
            candidates = [(row[0], row[1], row[2]) for row in cursor.fetchall()]
            english_names = [c[0] for c in candidates]
            
            print(f"DEBUG search_by_keyword: Found {len(candidates)} candidates")
            
            if not english_names:
                return []

            norm_keyword = self.normalize_name(keyword)
            exact_matches = [
                (en, cn, sys)
                for en, cn, sys in candidates
                if en.casefold() == keyword.casefold() or self.normalize_name(en) == norm_keyword
            ]

            if exact_matches:
                for en, cn, sys in exact_matches[:limit]:
                    results.append({
                        'english_name': en,
                        'chinese_name': cn,
                        'system': sys
                    })
                print(f"DEBUG search_by_keyword: Returning {len(results)} exact result(s)")
                return results
            
            # Fuzzy search on English names
            # Hybrid approach:
            # 1. For short queries (< 5 chars), use partial_ratio with word boundary check
            # 2. For long queries, use token_sort_ratio to avoid "contained" matches in unrelated long titles
            
            is_short_query = len(keyword) < 5
            
            if is_short_query:
                # Use partial_ratio for short queries to find "Age" in "Age of Empires"
                matches = process.extract(keyword, english_names, scorer=fuzz.partial_ratio, limit=limit*2)
                keyword_regex = re.compile(r'\b' + re.escape(keyword), re.IGNORECASE)
            else:
                # Use WRatio for better matching (handles partials, token sort, etc.)
                matches = process.extract(keyword, english_names, scorer=fuzz.WRatio, limit=limit*2)

            print(f"DEBUG search_by_keyword: Top matches (before filtering): {[(m[0], m[1]) for m in matches[:5]]}")

            noise_tokens = {
                "usa", "us", "japan", "jpn", "europe", "eur", "world", "asia",
                "korea", "hong", "kong", "china", "taiwan", "ver", "version",
                "rev", "set", "bootleg", "prototype", "proto", "beta", "demo",
                "the", "and", "of", "no", "with", "conversion", "buggy"
            }
            query_tokens = [
                token.lower()
                for token in re.findall(r"[A-Za-z][A-Za-z0-9]+", keyword)
                if len(token) >= 3 and token.lower() not in noise_tokens
            ]
            required_token = query_tokens[0] if query_tokens else ""
            
            # Build results from matches
            count = 0
            for match_name, score, _ in matches:
                if score < 60: continue

                if required_token and required_token not in self.normalize_name(match_name):
                    print(f"DEBUG search_by_keyword: Skipping '{match_name}' (score {score}) - missing required token '{required_token}'")
                    continue
                
                # Apply stricter filtering for short queries
                if is_short_query:
                    # For short queries, require word boundary match
                    if not keyword_regex.search(match_name):
                        print(f"DEBUG search_by_keyword: Skipping '{match_name}' (score {score}) - failed word boundary check")
                        continue
                
                print(f"DEBUG search_by_keyword: Accepting match '{match_name}' with score {score}")
                
                # Find the corresponding record
                for en, cn, sys in candidates:
                    if en == match_name:
                        results.append({
                            'english_name': en,
                            'chinese_name': cn,
                            'system': sys
                        })
                        count += 1
                        break
                
                if count >= limit:
                    break
            
        print(f"DEBUG search_by_keyword: Returning {len(results)} results")
        return results

    def close(self):
        if self.conn:
            self.conn.close()
