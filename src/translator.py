import json
import os
import re
from libretro_db import LibretroDB
from database import DatabaseManager

class Translator:
    def __init__(self, rom_name_cn_path, system_name=None, llm_client=None):
        self.rom_name_cn_path = rom_name_cn_path
        self.system_name = system_name
        self.llm_client = llm_client
        
        # Initialize Database
        self.db = DatabaseManager()
        
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
            self.libretro_db = LibretroDB(os.path.dirname(rom_name_cn_path)) 
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
        if not text:
            return text, text
            
        # 1. Exact match (English -> Chinese)
        chinese = self.db.search_by_english(text, system=self.system_name)
        if chinese:
            return chinese, text
            
        # 2. Reverse lookup (Chinese -> English)
        english = self.db.search_by_chinese(text, system=self.system_name)
        if english:
            return text, english
            
        # 3. Normalized match (Alias lookup)
        norm_text = self.normalize_name(text)
        chinese, english = self.db.search_by_normalized_alias(norm_text, system=self.system_name)
        if chinese and english:
            return chinese, english
            
        # 3. Alias / Acronym handling (Hardcoded fallbacks)
        # SRWF -> Super Robot Taisen F
        acronyms = {
            "srwf": "Super Robot Taisen F (Japan) (Rev A) (10M, 11M, 12M, 13M)",
            "srwff": "Super Robot Taisen F - Kanketsu-hen (Japan) (Rev A) (10M)",
            "srw": "Super Robot Taisen (Japan)"
        }
        
        if norm_text in acronyms:
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

        # 4. Try fuzzy matching
        # If text contains non-ASCII characters, try Chinese fuzzy search
        if any(ord(c) >= 128 for c in text):
             result = self.db.fuzzy_search_by_chinese(text, system=self.system_name)
             if result:
                 standard_cn, english = result
                 return standard_cn, english
        else:
             # Otherwise try English fuzzy search
             fuzzy_cn = self.db.fuzzy_search_by_english(norm_text, system=self.system_name)
             if fuzzy_cn:
                 return fuzzy_cn, text

        # 5. Try LibretroDB for standard English name
        # This helps games without Chinese translations get standardized names
        if self.libretro_db:
            standard_name = self.libretro_db.get_standard_name(text)
            if standard_name and standard_name != text:
                # Found standard English name in LibretroDB
                # No Chinese translation available, use standard English as both label and thumbnail source
                print(f"LibretroDB standard name: '{text}' -> '{standard_name}'")
                return standard_name, standard_name

        # 6. Fallback to LLM (if configured)
        if self.llm_client:
            llm_result = self.translate_with_llm(text)
            if llm_result:
                return llm_result, text 
        
        return text, text

    def translate_with_llm(self, text):
        # Placeholder for LLM integration
        return text

