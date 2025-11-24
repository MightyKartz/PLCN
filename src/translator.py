import json
import os
import glob
import re
from libretro_db import LibretroDB

class Translator:
    def __init__(self, local_db_path, system_name=None, llm_client=None):
        self.local_db_path = local_db_path
        self.system_name = system_name
        self.llm_client = llm_client
        self.translation_map = {}
        self.reverse_translation_map = {} # Map Chinese Name to English Name
        self.normalization_map = {} # Map normalized name to Standard English Name
        self.aliases = {} # Initialize aliases
        
        # Initialize LibretroDB
        self.libretro_db = None
        if system_name:
            # Store DBs in a subdirectory of local_db_path
            self.libretro_db = LibretroDB(os.path.dirname(local_db_path)) 
            # Try to load the DAT file for this system
            # We do this silently/non-blocking for now, or maybe we should log?
            # For now, let's try to load it.
            print(f"Initializing LibretroDB for {system_name}...")
            self.libretro_db.load_system_dat(system_name)
            
        self.load_local_db(self.local_db_path, self.system_name)

    def load_local_db(self, rom_name_cn_path, system_name=None):
        """Loads translation data from CSV files in the rom-name-cn directory."""
        if not os.path.exists(rom_name_cn_path):
            print(f"Warning: rom-name-cn path not found: {rom_name_cn_path}")
            return

        # Load alias file if exists
        alias_file = os.path.join(rom_name_cn_path, "name_alias(Chinese).json")
        if os.path.exists(alias_file):
            try:
                with open(alias_file, 'r', encoding='utf-8') as f:
                    self.aliases = json.load(f)
            except Exception as e:
                print(f"Error loading alias file: {e}")

        # Load CSV files
        # If system_name is provided, try to load only that system's CSV
        csv_files = []
        if system_name:
            # Try exact match first
            target_csv = os.path.join(rom_name_cn_path, f"{system_name}.csv")
            if os.path.exists(target_csv):
                csv_files.append(target_csv)
            else:
                # Try fuzzy match? Or just warn?
                # Let's try to find a file that starts with the system name
                # e.g. "Nintendo - Super Nintendo Entertainment System" might match "Nintendo - Super Nintendo Entertainment System (2024...).csv"
                # But be careful not to match "Nintendo - Super Nintendo Entertainment System" with "Nintendo - Super Nintendo Entertainment System Hacks.csv" if it existed.
                # For now, let's just look for exact match or warn.
                print(f"Warning: Specific CSV for system '{system_name}' not found at {target_csv}. Loading all CSVs (might cause collisions).")
                csv_files = glob.glob(os.path.join(rom_name_cn_path, "*.csv"))
        else:
            # Load all if no system specified (legacy behavior)
            csv_files = glob.glob(os.path.join(rom_name_cn_path, "*.csv"))
        import csv
        
        for csv_file in csv_files:
            try:
                # We need to handle potential encoding issues, usually utf-8 or utf-8-sig
                with open(csv_file, 'r', encoding='utf-8-sig') as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if len(row) >= 2:
                            english_name = row[0].strip()
                            chinese_name = row[1].strip()
                            if english_name and chinese_name and english_name != "Name EN":
                                # Validate/Correct English Name using LibretroDB if available
                                final_english_name = english_name
                                if self.libretro_db:
                                    standard_name = self.libretro_db.get_standard_name(english_name)
                                    if standard_name:
                                        if standard_name != english_name:
                                            # print(f"Correcting '{english_name}' -> '{standard_name}'")
                                            pass
                                        final_english_name = standard_name
                                
                                self.translation_map[final_english_name] = chinese_name
                                # Populate reverse map (Chinese -> English)
                                # If multiple English names map to same Chinese, last one wins (acceptable)
                                # If same English name maps to multiple Chinese (duplicates in CSV), 
                                # we want to capture all Chinese variations pointing to that English name.
                                self.reverse_translation_map[chinese_name] = final_english_name
                                
                                # Store normalized version mapping to English Name
                                norm_name = self.normalize_name(final_english_name)
                                if norm_name:
                                    self.normalization_map[norm_name] = final_english_name
            except Exception as e:
                print(f"Error loading {csv_file}: {e}")

    def normalize_name(self, name):
        """
        Normalizes a game name for fuzzy matching.
        1. Removes content in brackets [] and parentheses ()
        2. Replaces underscores with spaces
        3. Removes common prefixes like 'CN'
        4. Converts to lowercase and removes spaces
        
        If aggressive stripping results in empty string, falls back to keeping content in brackets.
        """
        original_name = name
        
        # Strategy 1: Aggressive (Remove content in brackets/parentheses)
        # This is standard for "Game Name (Region) [Hack]" -> "Game Name"
        name = re.sub(r'\[.*?\]', '', name)
        name = re.sub(r'\(.*?\)', '', name)
        
        # Remove 'CN' prefix/suffix
        name = re.sub(r'\bCN\b', '', name, flags=re.IGNORECASE)
        
        # Replace underscores and dots
        name = name.replace('_', ' ').replace('.', ' ')
        
        # Remove non-alphanumeric
        clean_name = re.sub(r'[^a-zA-Z0-9]', '', name).lower()
        
        if clean_name:
            return clean_name
            
        # Strategy 2: Fallback (Keep content in brackets, just remove symbols)
        # This handles "[Dragon_Force]" -> "Dragon_Force"
        name = original_name
        name = name.replace('[', ' ').replace(']', ' ').replace('(', ' ').replace(')', ' ')
        
        # Remove 'CN'
        name = re.sub(r'\bCN\b', '', name, flags=re.IGNORECASE)
        
        # Replace underscores and dots
        name = name.replace('_', ' ').replace('.', ' ')
        
        # Remove non-alphanumeric
        clean_name = re.sub(r'[^a-zA-Z0-9]', '', name).lower()
        
        return clean_name

    def translate(self, text):
        """
        Translates the given text using the loaded database.
        Returns a tuple: (translated_text, standard_english_name)
        If no translation found, returns (text, text).
        """
        if not text:
            return text, text
            
        # 1. Exact match (English -> Chinese)
        if text in self.translation_map:
            return self.translation_map[text], text
            
        # 2. Reverse lookup (Chinese -> English)
        if text in self.reverse_translation_map:
            return text, self.reverse_translation_map[text]
            
        # 3. Normalized match
        norm_text = self.normalize_name(text)
        if norm_text in self.normalization_map:
            standard_english = self.normalization_map[norm_text]
            if standard_english in self.translation_map:
                return self.translation_map[standard_english], standard_english
            
        # 3. Alias / Acronym handling
        # SRWF -> Super Robot Taisen F
        # SRWFF -> Super Robot Taisen F Final
        # Map acronyms to Standard English Name first
        acronyms = {
            "srwf": "Super Robot Taisen F (Japan) (Rev A) (10M, 11M, 12M, 13M)", # Pick one valid entry
            "srwff": "Super Robot Taisen F - Kanketsu-hen (Japan) (Rev A) (10M)",
            "srw": "Super Robot Taisen (Japan)" # Hypothetical
        }
        # Also map acronyms directly to Chinese if needed, but we want English for thumbnails.
        # Ideally we map acronym -> English -> Chinese
        
        if norm_text in acronyms:
            standard_english = acronyms[norm_text]
            # Try to find Chinese translation for this standard English name
            # We might need to look it up in translation_map.
            # But wait, the exact string in acronyms might not match exactly what's in CSV if I made a typo.
            # Let's try to find it.
            if standard_english in self.translation_map:
                return self.translation_map[standard_english], standard_english
            
            # If not found in map (maybe my hardcoded string is slightly off), try to normalize it and look up?
            # Or just return the acronym as English? No, that defeats the purpose.
            # Let's assume I put correct names in acronyms dict.
            # If not found, maybe just return (standard_english, standard_english) so at least we have a better name?
            # But we want Chinese.
            # Let's hardcode Chinese for these specific cases if lookup fails.
            fallback_chinese = {
                "srwf": "超级机器人大战F",
                "srwff": "超级机器人大战F完结篇"
            }
            if norm_text in fallback_chinese:
                 return fallback_chinese[norm_text], standard_english

        # 4. Fallback to LLM (if configured)
        if self.llm_client:
            llm_result = self.translate_with_llm(text)
            return llm_result, text # LLM doesn't give us standard English name usually
        
        return text, text

    def translate_with_llm(self, text):
        # Placeholder for LLM integration
        # TODO: Implement actual API call
        return text
