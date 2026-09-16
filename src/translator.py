import json
import os
import re
import app_paths
from libretro_db import LibretroDB
from database import DatabaseManager

class Translator:
    def __init__(self, rom_name_cn_path, system_name=None, db_path=None):
        self.rom_name_cn_path = rom_name_cn_path
        self.system_name = system_name
        
        # Initialize Database
        from data_pack import open_database
        self.db = open_database(rom_name_cn_path, db_path=db_path)
        
        # Check if we need to import data
        # For simplicity, we can check if the translations table is empty
        # Or just run import every time (it has checks? No, it inserts. We should check count)
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM translations")
        count = cursor.fetchone()[0]
        
        if count == 0:
            print("Database empty. Importing CSVs...")
            self.db.import_csvs(rom_name_cn_path)
        
        # Initialize LibretroDB
        self.libretro_db = None
        if system_name:
            # Store DBs in a subdirectory of local_db_path
            # Packs are immutable; DAT caches remain in the writable runtime directory.
            self.libretro_db = LibretroDB(str(app_paths.dat_storage()))
            # Try to load the DAT file for this system
            print(f"Initializing LibretroDB for {system_name}...")
            self.libretro_db.load_system_dat(system_name)

    def normalize_name(self, name):
        """
        Normalizes a game name for fuzzy matching.
        Delegates to DatabaseManager to ensure consistency.
        """
        return self.db.normalize_name(name)

    def translate(self, text):
        """
        Translates the given text using the database.
        Returns a tuple: (translated_text, standard_english_name)
        If no translation found, returns (text, text).
        """
        self.last_match_source = 'fallback'
        if not text:
            return text, text
            
        # 1. Exact match (English -> Chinese)
        chinese = self.db.search_by_english(text, system=self.system_name)
        if chinese:
            self.last_match_source = 'exact'
            return chinese, text
            
        # 2. Reverse lookup (Chinese -> English)
        english = self.db.search_by_chinese(text, system=self.system_name)
        if english:
            self.last_match_source = 'exact'
            return text, english
            
        # 3. Normalized match (Alias lookup)
        norm_text = self.normalize_name(text)
        chinese, english = self.db.search_by_normalized_alias(norm_text, system=self.system_name)
        if chinese and english:
            self.last_match_source = 'exact_alias'
            return chinese, english

        # Arcade ports can suggest a translation, but must never silently become
        # a confirmed identity or replace the arcade DAT thumbnail title.
        if self.system_name and any(value in self.system_name for value in ('Arcade', 'FBNeo', 'MAME')):
            rows = self.db.get_connection().execute('SELECT DISTINCT t.chinese_name, t.system FROM aliases a JOIN translations t ON a.english_name=t.english_name AND a.system=t.system WHERE a.normalized_alias=? AND t.chinese_name<>\'\' ORDER BY t.system, t.chinese_name', (norm_text,)).fetchall()
            if rows:
                self.last_match_source = 'cross_system_candidate'
                self.last_translation_candidates = list(dict.fromkeys(row[0] for row in rows))
                return rows[0][0], text

        # 5. Alias / Acronym handling (Hardcoded fallbacks)
        # SRWF -> Super Robot Taisen F
        acronyms = {
            "srwf": "Super Robot Taisen F (Japan) (Rev A) (10M, 11M, 12M, 13M)",
            "srwff": "Super Robot Taisen F - Kanketsu-hen (Japan) (Rev A) (10M)",
            "srw": "Super Robot Taisen (Japan)"
        }
        
        if norm_text in acronyms:
            self.last_match_source = 'curated_alias'
            standard_english = acronyms[norm_text]
            # Try to find Chinese translation for this standard English name in DB
            chinese = self.db.search_by_english(standard_english, system=self.system_name)
            if chinese:
                return chinese, standard_english
            
            # Fallback hardcoded Chinese
            fallback_chinese = {
                "srwf": "超级机器人大战F",
                "srwff": "超级机器人大战F完结篇"
            }
            if norm_text in fallback_chinese:
                 return fallback_chinese[norm_text], standard_english

        # 6. Try fuzzy matching
        # If text contains non-ASCII characters, try Chinese fuzzy search
        if any(ord(c) >= 128 for c in text):
             result = self.db.fuzzy_search_by_chinese(text, system=self.system_name)
             if result:
                 self.last_match_source = 'fuzzy_candidate'
                 standard_cn, english = result
                 return standard_cn, english
        else:
             # Otherwise try English fuzzy search
             fuzzy_cn = self.db.fuzzy_search_by_english(norm_text, system=self.system_name)
             if fuzzy_cn:
                 self.last_match_source = 'fuzzy_candidate'
                 return fuzzy_cn, text

        # 7. Try LibretroDB for standard English name
        # This helps games without Chinese translations get standardized names
        if self.libretro_db:
            standard_name = self.libretro_db.get_standard_name(text)
            if standard_name and standard_name != text:
                print(f"LibretroDB standard name: '{text}' -> '{standard_name}'")
                
                # Try to find Chinese translation for this standard English name
                chinese = self.db.search_by_english(standard_name, system=self.system_name)
                if chinese:
                    return chinese, standard_name
                
                # No Chinese translation available, use standard English as both label and thumbnail source
                return standard_name, standard_name

        # 8. For Arcade/FBNeo games, clean the ROM name for better presentation
        # This handles cases where LibretroDB has no data
        if self.system_name and ('Arcade' in self.system_name or 'FBNeo' in self.system_name):
            cleaned = self._clean_arcade_rom_name(text)
            if cleaned != text:
                print(f"Cleaned arcade ROM name: '{text}' -> '{cleaned}'")
                return cleaned, cleaned

        return text, text

    def _clean_arcade_rom_name(self, name):
        """
        Cleans FBNeo/MAME ROM names to be more human-readable.
        Examples:
          - "1943kai" -> "1943 Kai"
          - "sfii" -> "SFII"  (keep uppercase for well-known acronyms)
          - "metalslug" -> "Metal Slug"
        """
        if not name:
            return name
        
        import re
        
        # Add space before common suffixes
        name = re.sub(r'(\d+)(kai|ex|plus|turbo|super|special|dx)', r'\1 \2', name, flags=re.IGNORECASE)
        
        # Add space between lowercase and uppercase (camelCase -> Camel Case)
        name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
        
        # Title case if all lowercase
        if name.islower():
            # Split by common separators and title case each word
            words = re.split(r'([^a-zA-Z0-9]+)', name)
            name = ''.join(word.title() if word.isalnum() else word for word in words)
        
        return name.strip()
