import os
import sys
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import re

class LibretroDB:
    # No system mappings needed - main DAT files contain all games
    SYSTEM_MAPPINGS = {}
    
    def __init__(self, storage_path):
        self.storage_path = storage_path
        self.dat_dir = os.path.join(storage_path, "libretro-db", "dat")
        os.makedirs(self.dat_dir, exist_ok=True)
        self.standard_names = {} # normalized_name -> standard_english_name
        
    def get_dat_path(self, system_name):
        """Returns the path to the DAT file for the given system."""
        # Check if running in frozen mode (PyInstaller)
        if getattr(sys, 'frozen', False):
            # Check bundled data first
            bundled_path = os.path.join(sys._MEIPASS, 'data', 'libretro-db', 'dat', f'{system_name}.dat')
            if os.path.exists(bundled_path):
                return bundled_path
                
        # Check local data directory
        return os.path.join(self.dat_dir, f'{system_name}.dat')
        
    def download_dat(self, system_name, specific_url=None):
        """Downloads the DAT file for the given system from GitHub, trying multiple locations."""
        
        target_path = self.get_dat_path(system_name)
        
        if specific_url:
            print(f"Downloading DAT for {system_name} from specific URL: {specific_url}...")
            try:
                urllib.request.urlretrieve(specific_url, target_path)
                print(f"Downloaded to {target_path}")
                return True
            except Exception as e:
                print(f"Failed to download from {specific_url}: {e}")
                return False

        # URL encode the system name for the URL
        encoded_name = urllib.parse.quote(system_name)
        
        # Special handling for FBNeo and other arcade systems
        base_urls = []
        
        # FBNeo Arcade Games has special location
        if 'FBNeo' in system_name or system_name in ['Arcade - CPS1', 'Arcade - CPS2', 'Arcade - CPS3', 'Arcade - NEOGEO']:
            base_urls.append(f"https://raw.githubusercontent.com/libretro/libretro-database/master/metadat/fbneo-split/{encoded_name}.dat")
        
        # SNK Neo Geo has its own location
        if 'Neo Geo' in system_name or 'NEOGEO' in system_name:
            base_urls.append(f"https://raw.githubusercontent.com/libretro/libretro-database/master/dat/SNK%20-%20Neo%20Geo.dat")
        
        # Standard locations
        # Standard locations - Prioritize specific collections over generic 'dat' folder
        # The generic 'dat' folder sometimes contains incomplete files (e.g. NEC - PC-98)
        base_urls.extend([
            f"https://raw.githubusercontent.com/libretro/libretro-database/master/metadat/libretro-dats/{encoded_name}.dat",
            f"https://raw.githubusercontent.com/libretro/libretro-database/master/metadat/no-intro/{encoded_name}.dat",
            f"https://raw.githubusercontent.com/libretro/libretro-database/master/metadat/tosec/{encoded_name}.dat",
            f"https://raw.githubusercontent.com/libretro/libretro-database/master/metadat/redump/{encoded_name}.dat",
            f"https://raw.githubusercontent.com/libretro/libretro-database/master/dat/{encoded_name}.dat",
        ])
        
        for url in base_urls:
            print(f"Trying to download DAT for {system_name} from {url}...")
            try:
                urllib.request.urlretrieve(url, target_path)
                print(f"Downloaded to {target_path}")
                return True
            except Exception as e:
                # print(f"Failed to download from {url}: {e}")
                continue
                
        print(f"Failed to download DAT for {system_name} from all known locations.")
        return False
            
    def load_system_dat(self, system_name):
        """Loads the DAT file(s) for the system, downloading if necessary.
        For mapped systems (like FBNeo), loads all mapped system DATs plus the main system DAT."""
        
        self.standard_names = {} # Clear previous entries before loading new system(s)
        
        # Check if this is a mapped system
        base_system = system_name.split('(')[0].strip()
        
        if base_system in self.SYSTEM_MAPPINGS:
            # For mapped systems, try to load the main system DAT first
            print(f"Loading main DAT for {base_system}...")
            loaded_count = 0
            
            # Try loading the main system DAT (e.g., "FBNeo - Arcade Games")
            if self._load_single_dat(base_system):
                loaded_count += 1
                print(f"Loaded main {base_system} DAT")
            
            # Also load all mapped subsystems
            mapped_systems = self.SYSTEM_MAPPINGS[base_system]
            print(f"Loading {len(mapped_systems)} subsystem DAT files...")
            
            for mapped_system in mapped_systems:
                if self._load_single_dat(mapped_system):
                    loaded_count += 1
            
            total_entries = len(self.standard_names)
            print(f"Loaded {loaded_count} DAT file(s) with {total_entries} total entries for {base_system}.")
            return loaded_count > 0
        else:
            # Single system
            success = self._load_single_dat(base_system)
            
            # Special handling for NEC - PC-98 to load Redump DAT as well
            if base_system == "NEC - PC-98":
                print(f"Loading supplemental Redump DAT for {base_system}...")
                redump_system = f"{base_system} (Redump)"
                redump_url = f"https://raw.githubusercontent.com/libretro/libretro-database/master/metadat/redump/{urllib.parse.quote(base_system)}.dat"
                if self._load_single_dat(redump_system, specific_url=redump_url):
                    success = True
                    print(f"Loaded Redump DAT for {base_system}")
            
            return success
    
    def _load_single_dat(self, system_name, specific_url=None):
        """Loads a single DAT file for the system, downloading it if necessary."""
        dat_path = self.get_dat_path(system_name)
        
        # Check if DAT exists (either bundled or previously downloaded)
        if not os.path.exists(dat_path):
            print(f"DAT file not found at {dat_path}, attempting download...")
            if not self.download_dat(system_name, specific_url=specific_url):
                return False
                
        try:
            # Parse clrmamepro format (text-based)
            # Format:
            # game (
            #   name "Game Name"
            #   description "Full Game Title"
            #   ...
            # )
            
            with open(dat_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                
            # Iterate line by line
            current_block = None
            current_name = None
            current_desc = None
            
            for line in content.splitlines():
                line = line.strip()
                if line.startswith('game ('):
                    current_block = 'game'
                    current_name = None
                    current_desc = None
                elif line.startswith(')'):
                    if current_block == 'game' and current_name:
                        # If we have a description, use it as the standard name (common for Arcade)
                        # Otherwise use the name
                        standard_name = current_desc if current_desc else current_name
                        
                        # Store mapping: normalized(name) -> standard_name
                        # This allows looking up by zip name ("aof3") to get "Art of Fighting 3"
                        norm_name = self.normalize_name(current_name)
                        if norm_name not in self.standard_names:
                            self.standard_names[norm_name] = []
                        if standard_name not in self.standard_names[norm_name]:
                            self.standard_names[norm_name].append(standard_name)
                            
                        # ALSO store mapping: normalized(description) -> standard_name
                        # This allows looking up by full title ("Art of Fighting 3") to get "Art of Fighting 3"
                        if current_desc:
                            norm_desc = self.normalize_name(current_desc)
                            if norm_desc not in self.standard_names:
                                self.standard_names[norm_desc] = []
                            if standard_name not in self.standard_names[norm_desc]:
                                self.standard_names[norm_desc].append(standard_name)
                                
                    current_block = None
                elif current_block == 'game':
                    if line.startswith('name'):
                        match = re.search(r'name\s+"(.*?)"', line)
                        if match:
                            current_name = match.group(1)
                    elif line.startswith('description'):
                        match = re.search(r'description\s+"(.*?)"', line)
                        if match:
                            current_desc = match.group(1)
            
            print(f"Loaded {len(self.standard_names)} normalized entries from {system_name}.dat")
            return True
        except Exception as e:
            print(f"Error parsing DAT file {dat_path}: {e}")
            return False
            
    def normalize_name(self, name):
        """
        Normalizes a game name for fuzzy matching.
        Same logic as Translator.normalize_name to ensure consistency.
        """
        # Strategy 1: Aggressive (Remove content in brackets/parentheses)
        name_clean = re.sub(r'\[.*?\]', '', name)
        name_clean = re.sub(r'\(.*?\)', '', name_clean)
        
        # Remove 'CN' prefix/suffix
        name_clean = re.sub(r'\bCN\b', '', name_clean, flags=re.IGNORECASE)
        
        # Replace underscores and dots
        name_clean = name_clean.replace('_', ' ').replace('.', ' ')
        
        # Remove non-alphanumeric
        clean_name = re.sub(r'[^a-zA-Z0-9]', '', name_clean).lower()
        
        if clean_name:
            return clean_name
            
        # Strategy 2: Fallback
        name_fallback = name
        name_fallback = name_fallback.replace('[', ' ').replace(']', ' ').replace('(', ' ').replace(')', ' ')
        name_fallback = re.sub(r'\bCN\b', '', name_fallback, flags=re.IGNORECASE)
        name_fallback = name_fallback.replace('_', ' ').replace('.', ' ')
        clean_name_fallback = re.sub(r'[^a-zA-Z0-9]', '', name_fallback).lower()
        
        return clean_name_fallback

    def get_standard_name(self, name):
        """
        Returns the standard English name for a given input name (fuzzy matched).
        Uses multiple strategies: exact match, prefix match, fuzzy match.
        Returns None if no match found.
        """
        if not self.standard_names:
            return None
        
        norm_name = self.normalize_name(name)
        
        # Strategy 1: Try exact normalized match
        candidates = self.standard_names.get(norm_name)
        
        if not candidates:
            # Strategy 2: Try prefix match (for ROM names like "1943kai" matching "1943kaimidwaykaisen")
            # This handles "shortname" matching "shortname: Full Title"
            for db_norm, db_names in self.standard_names.items():
                if db_norm.startswith(norm_name) and len(norm_name) >= 4:  # Minimum 4 chars to avoid false positives
                    candidates = db_names
                    print(f"LibretroDB prefix match: '{name}' (norm: '{norm_name}') -> '{db_norm}' -> '{db_names[0]}'")
                    break
        
        if not candidates:
            # Strategy 3: Try fuzzy matching on normalized names
            try:
                from rapidfuzz import process, fuzz
                result = process.extractOne(
                    norm_name,
                    list(self.standard_names.keys()),
                    scorer=fuzz.ratio
                )
                
                if result and result[1] >= 80:  # High threshold for LibretroDB
                    matched_norm = result[0]
                    candidates = self.standard_names[matched_norm]
                    print(f"LibretroDB fuzzy match: '{name}' (norm: '{norm_name}') -> '{matched_norm}' (Score: {result[1]})")
                else:
                    return None
            except ImportError:
                return None
        
        if not candidates:
            return None
            
        if len(candidates) == 1:
            return candidates[0]
            
        # Try to match region
        # If no region match, or no region in input, prefer USA -> Europe -> Japan -> World
        # Or just return the first one (which is usually the first one found in DAT)
        # Let's try to be smart: if input has no region, maybe default to World or USA?
        # For now, just return the first one if no region match found.
        # Extract region from input name if possible
        # Look for (Japan), (USA), (Europe), etc.
        regions = re.findall(r'\((.*?)\)', name)
        
        if regions:
            region = regions[-1] # Use last region found
            # Filter candidates by region
            region_candidates = [c for c in candidates if region in c]
            if region_candidates:
                return region_candidates[0]
                
        # Default to first candidate
        return candidates[0]

    def search(self, keyword, limit=20):
        """
        Searches for standard names matching the keyword.
        Returns a list of matching names.
        """
        if not self.standard_names:
            return []
            
        # Collect all unique standard names
        all_names = set()
        for names in self.standard_names.values():
            all_names.update(names)
        all_names = list(all_names)
        
        # Use rapidfuzz for searching

        # Strict Token Search Logic
        # 1. Parse Query
        # User requested NO stop word removal (e.g. "king of" -> "king" AND "of")
        # stop_words = {"the", "of", "and", "a", "an", "in", "on", "at", "to", "for", "is", "are", "with", "by", "-"}
        
        # Normalize query: remove special chars (except spaces) for tokenization?
        # Actually, let's just split by whitespace and handle non-alphanumeric in regex
        raw_tokens = keyword.lower().split()
        tokens = raw_tokens # No filtering
        if not tokens: return []
        
        # 2. Build Regexes for each token (enforce word boundary)
        try:
            regexes = [re.compile(r'\b' + re.escape(t) + r'\b', re.IGNORECASE) for t in tokens]
        except re.error:
            # Fallback if regex compilation fails (e.g. bad escape)
            return []
            
        # 3. Search
        results = []
        exact_phrase_matches = []
        token_matches = []
        
        # Compile regex for exact phrase with word boundaries
        try:
            phrase_regex = re.compile(r'\b' + re.escape(keyword) + r'\b', re.IGNORECASE)
        except re.error:
            phrase_regex = None
        
        for name in all_names:
            # Check 1: Exact phrase match (highest priority, with word boundaries)
            # "Age" matches "Age of Heroes", but NOT "Savage"
            if phrase_regex and phrase_regex.search(name):
                exact_phrase_matches.append(name)
                continue
                
            # Check 2: All tokens match (word boundary enforced)
            if regexes and all(regex.search(name) for regex in regexes):
                token_matches.append(name)
        
        # 4. Rank and Combine
        # Sort by length (shorter names usually more relevant)
        exact_phrase_matches.sort(key=len)
        token_matches.sort(key=len)
        
        # Combine unique results
        seen = set()
        final_results = []
        
        for name in exact_phrase_matches:
            if name not in seen:
                final_results.append(name)
                seen.add(name)
                
        for name in token_matches:
            if name not in seen:
                final_results.append(name)
                seen.add(name)
                
        return final_results[:limit]
