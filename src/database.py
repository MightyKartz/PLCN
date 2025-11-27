import sqlite3
import os
import csv
import glob
import json
import re

class DatabaseManager:
    DB_FILE = "plcn.db"
    
    # System mapping: maps virtual system names to multiple actual CSV system names
    SYSTEM_MAPPINGS = {
        "FBNeo - Arcade Games": [
            "FBNeo - Arcade Games",
            "Arcade - CPS1",
            "Arcade - CPS2",
            "Arcade - CPS3",
            "Arcade - NEOGEO"
        ]
    }

    def __init__(self, db_path=None):
        if db_path:
            self.db_path = db_path
        else:
            # Default to same directory as config or executable
            base_path = os.getcwd()
            self.db_path = os.path.join(base_path, self.DB_FILE)
        
        self.conn = None
        self.english_names_cache = None
        self.chinese_names_cache = None
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
            return self.SYSTEM_MAPPINGS[base_system]
        
        return [system]

    def get_connection(self):
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
        return self.conn

    def init_db(self):
        """Initialize the database schema."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Main translation table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS translations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                english_name TEXT NOT NULL UNIQUE,
                chinese_name TEXT NOT NULL,
                system TEXT
            )
        ''')
        
        # Table: aliases
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alias TEXT NOT NULL,
                english_name TEXT NOT NULL,
                normalized_alias TEXT NOT NULL,
                FOREIGN KEY(english_name) REFERENCES translations(english_name)
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

        conn.commit()

    def import_csvs(self, rom_name_cn_path):
        """Imports data from CSV files into the database."""
        if not os.path.exists(rom_name_cn_path):
            print(f"Error: CSV path not found: {rom_name_cn_path}")
            return

        print(f"Importing CSVs from {rom_name_cn_path} into SQLite...")
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Invalidate cache
        self.english_names_cache = None
        self.chinese_names_cache = None
        
        # 1. Load Aliases from JSON if exists
        alias_file = os.path.join(rom_name_cn_path, "name_alias(Chinese).json")
        if os.path.exists(alias_file):
            try:
                with open(alias_file, 'r', encoding='utf-8') as f:
                    aliases_data = json.load(f)
                    pass
            except Exception as e:
                print(f"Error loading alias file: {e}")

        # 2. Load CSVs
        csv_files = glob.glob(os.path.join(rom_name_cn_path, "*.csv"))
        count = 0
        
        for csv_file in csv_files:
            try:
                # Determine system from filename
                system_name = os.path.splitext(os.path.basename(csv_file))[0]
                
                with open(csv_file, 'r', encoding='utf-8-sig') as f:
                    reader = csv.reader(f)
                    
                    # Read first row to detect format
                    first_row = next(reader, None)
                    if not first_row:
                        continue
                    
                    # Detect CSV format based on header or column count
                    is_3_column_arcade = False
                    if len(first_row) >= 3 and ('MAME' in first_row[0] or 'mame' in first_row[0].lower()):
                        # 3-column arcade format: MAME Name, EN Name, CN Name
                        is_3_column_arcade = True
                        # Skip header row
                    elif first_row[0] == "Name EN" or "Name" in first_row[0]:
                        # 2-column format with header: Name EN, Name CN
                        # Skip header row
                        pass
                    else:
                        # No header, rewind by using first row as data
                        # For 2-column format
                        if len(first_row) >= 2:
                            english_name = first_row[0].strip()
                            chinese_name = first_row[1].strip()
                            if not chinese_name:
                                chinese_name = english_name
                            
                            if english_name:
                                try:
                                    cursor.execute('''
                                        INSERT OR IGNORE INTO translations (english_name, chinese_name, system)
                                        VALUES (?, ?, ?)
                                    ''', (english_name, chinese_name, system_name))
                                    norm_name = self.normalize_name(english_name)
                                    cursor.execute('''
                                        INSERT OR IGNORE INTO aliases (alias, english_name, normalized_alias)
                                        VALUES (?, ?, ?)
                                    ''', (english_name, english_name, norm_name))
                                    count += 1
                                except sqlite3.Error:
                                    pass
                    
                    # Process remaining rows
                    for row in reader:
                        if is_3_column_arcade:
                            # 3-column: MAME Name, EN Name, CN Name
                            if len(row) >= 3:
                                mame_name = row[0].strip()
                                english_name = row[1].strip()
                                chinese_name = row[2].strip()
                                if not chinese_name:
                                    chinese_name = english_name
                                
                                if mame_name and english_name:
                                    try:
                                        # Store EN Name as english_name, CN Name as chinese_name
                                        cursor.execute('''
                                            INSERT OR IGNORE INTO translations (english_name, chinese_name, system)
                                            VALUES (?, ?, ?)
                                        ''', (english_name, chinese_name, system_name))
                                        
                                        # Add english name as alias
                                        norm_name = self.normalize_name(english_name)
                                        cursor.execute('''
                                            INSERT OR IGNORE INTO aliases (alias, english_name, normalized_alias)
                                            VALUES (?, ?, ?)
                                        ''', (english_name, english_name, norm_name))
                                        
                                        # Also add MAME name as alias pointing to the english name
                                        norm_mame = self.normalize_name(mame_name)
                                        cursor.execute('''
                                            INSERT OR IGNORE INTO aliases (alias, english_name, normalized_alias)
                                            VALUES (?, ?, ?)
                                        ''', (mame_name, english_name, norm_mame))
                                        
                                        count += 1
                                    except sqlite3.Error:
                                        pass
                        else:
                            # 2-column format: Name EN, Name CN
                            if len(row) >= 2:
                                english_name = row[0].strip()
                                chinese_name = row[1].strip()
                                if not chinese_name:
                                    chinese_name = english_name
                                
                                if english_name:
                                    try:
                                        cursor.execute('''
                                            INSERT OR IGNORE INTO translations (english_name, chinese_name, system)
                                            VALUES (?, ?, ?)
                                        ''', (english_name, chinese_name, system_name))
                                        
                                        norm_name = self.normalize_name(english_name)
                                        cursor.execute('''
                                            INSERT OR IGNORE INTO aliases (alias, english_name, normalized_alias)
                                            VALUES (?, ?, ?)
                                        ''', (english_name, english_name, norm_name))
                                        
                                        count += 1
                                    except sqlite3.Error:
                                        pass
            except Exception as e:
                print(f"Error processing {csv_file}: {e}")
        
        # Rebuild FTS index if needed (though triggers handle new inserts, existing data might need sync if table was empty but FTS wasn't)
        # For simplicity, we assume fresh import populates triggers.
        # If we want to be safe:
        try:
            cursor.execute("INSERT INTO translations_fts(translations_fts) VALUES('rebuild')")
        except:
            pass
            
        conn.commit()
        print(f"Imported {count} entries into database.")

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
                placeholders = ' OR '.join(['system LIKE ?' for _ in systems])
                query = f'SELECT chinese_name FROM translations WHERE english_name = ? AND ({placeholders})'
                params = [english_name] + [f'{s}%' for s in systems]
                cursor.execute(query, params)
            else:
                cursor.execute('SELECT chinese_name FROM translations WHERE english_name = ? AND system LIKE ?', (english_name, f'{systems[0]}%'))
        else:
            cursor.execute('SELECT chinese_name FROM translations WHERE english_name = ?', (english_name,))
        row = cursor.fetchone()
        return row['chinese_name'] if row else None

    def search_by_chinese(self, chinese_name, system=None):
        cursor = self.get_connection().cursor()
        if system:
            systems = self.expand_system_mapping(system)
            if len(systems) > 1:
                # Multiple systems: use OR condition
                placeholders = ' OR '.join(['system LIKE ?' for _ in systems])
                query = f'SELECT english_name FROM translations WHERE chinese_name = ? AND ({placeholders})'
                params = [chinese_name] + [f'{s}%' for s in systems]
                print(f"      DB Query: chinese_name='{chinese_name}', systems={systems}")
                cursor.execute(query, params)
            else:
                print(f"      DB Query: chinese_name='{chinese_name}', system LIKE '{systems[0]}%'")
                cursor.execute('SELECT english_name FROM translations WHERE chinese_name = ? AND system LIKE ?', (chinese_name, f'{systems[0]}%'))
        else:
            cursor.execute('SELECT english_name FROM translations WHERE chinese_name = ?', (chinese_name,))
        row = cursor.fetchone()
        result = row['english_name'] if row else None
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
                placeholders = ' OR '.join(['t.system LIKE ?' for _ in systems])
                query = f'''
                    SELECT t.chinese_name, t.english_name 
                    FROM aliases a
                    JOIN translations t ON a.english_name = t.english_name
                    WHERE a.normalized_alias = ? AND ({placeholders})
                    LIMIT 1
                '''
                params = [normalized_name] + [f'{s}%' for s in systems]
                cursor.execute(query, params)
            else:
                query = '''
                    SELECT t.chinese_name, t.english_name 
                    FROM aliases a
                    JOIN translations t ON a.english_name = t.english_name
                    WHERE a.normalized_alias = ? AND t.system LIKE ?
                    LIMIT 1
                '''
                cursor.execute(query, (normalized_name, f'{systems[0]}%'))
        else:
            query = '''
                SELECT t.chinese_name, t.english_name 
                FROM aliases a
                JOIN translations t ON a.english_name = t.english_name
                WHERE a.normalized_alias = ?
                LIMIT 1
            '''
            cursor.execute(query, (normalized_name,))
        row = cursor.fetchone()
        return (row['chinese_name'], row['english_name']) if row else (None, None)

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
                placeholders = ' OR '.join(['system LIKE ?' for _ in systems])
                query_sql = f'SELECT english_name, chinese_name FROM translations WHERE {placeholders}'
                params = [f'{s}%' for s in systems]
                cursor.execute(query_sql, params)
            else:
                cursor.execute('SELECT english_name, chinese_name FROM translations WHERE system LIKE ?', (f'{systems[0]}%',))
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
                placeholders = ' OR '.join(['system LIKE ?' for _ in systems])
                query_sql = f'SELECT chinese_name FROM translations WHERE {placeholders}'
                params = [f'{s}%' for s in systems]
                cursor.execute(query_sql, params)
            else:
                cursor.execute('SELECT chinese_name FROM translations WHERE system LIKE ?', (f'{systems[0]}%',))
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
                    placeholders = ' OR '.join(['system LIKE ?' for _ in systems])
                    query = f'SELECT chinese_name, english_name, system FROM translations WHERE {placeholders}'
                    params = [f'{s}%' for s in systems]
                    cursor.execute(query, params)
                else:
                    cursor.execute('SELECT chinese_name, english_name, system FROM translations WHERE system LIKE ?', (f'{systems[0]}%',))
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
            for match_name, score, _ in matches:
                if score >= 65:  # Use threshold (lowered from 70)
                    # Find the corresponding record
                    for cn, en, sys in candidates:
                        if cn == match_name:
                            results.append({
                                'chinese_name': cn,
                                'english_name': en,
                                'system': sys
                            })
                            break
        else:
            # Build English names cache (optionally filtered by system)
            if system:
                systems = self.expand_system_mapping(system)
                if len(systems) > 1:
                    placeholders = ' OR '.join(['system LIKE ?' for _ in systems])
                    query = f'SELECT english_name, chinese_name, system FROM translations WHERE {placeholders}'
                    params = [f'{s}%' for s in systems]
                    cursor.execute(query, params)
                else:
                    cursor.execute('SELECT english_name, chinese_name, system FROM translations WHERE system LIKE ?', (f'{systems[0]}%',))
            else:
                cursor.execute('SELECT english_name, chinese_name, system FROM translations')
            
            candidates = [(row[0], row[1], row[2]) for row in cursor.fetchall()]
            english_names = [c[0] for c in candidates]
            
            print(f"DEBUG search_by_keyword: Found {len(candidates)} candidates")
            
            if not english_names:
                return []
            
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
                # Use token_sort_ratio for long queries to penalize length mismatches
                # e.g. "The Age of Heroes" vs "Marvel Vs. Capcom..."
                matches = process.extract(keyword, english_names, scorer=fuzz.token_sort_ratio, limit=limit*2)

            print(f"DEBUG search_by_keyword: Top matches (before filtering): {[(m[0], m[1]) for m in matches[:5]]}")
            
            # Build results from matches
            count = 0
            for match_name, score, _ in matches:
                if score < 60: continue
                
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
