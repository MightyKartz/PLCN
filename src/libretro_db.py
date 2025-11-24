import os
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import re

class LibretroDB:
    def __init__(self, storage_path):
        self.storage_path = storage_path
        self.dat_dir = os.path.join(storage_path, "libretro-db", "dat")
        os.makedirs(self.dat_dir, exist_ok=True)
        self.standard_names = {} # normalized_name -> standard_english_name
        
    def get_dat_path(self, system_name):
        return os.path.join(self.dat_dir, f"{system_name}.dat")
        
    def download_dat(self, system_name):
        """Downloads the DAT file for the given system from GitHub, trying multiple locations."""
        # URL encode the system name for the URL
        encoded_name = urllib.parse.quote(system_name)
        
        base_urls = [
            f"https://raw.githubusercontent.com/libretro/libretro-database/master/dat/{encoded_name}.dat",
            f"https://raw.githubusercontent.com/libretro/libretro-database/master/metadat/redump/{encoded_name}.dat",
            f"https://raw.githubusercontent.com/libretro/libretro-database/master/metadat/no-intro/{encoded_name}.dat",
            f"https://raw.githubusercontent.com/libretro/libretro-database/master/metadat/libretro-dats/{encoded_name}.dat",
            f"https://raw.githubusercontent.com/libretro/libretro-database/master/metadat/tosec/{encoded_name}.dat",
        ]
        
        target_path = self.get_dat_path(system_name)
        
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
        """Loads the DAT file for the system, downloading it if necessary."""
        dat_path = self.get_dat_path(system_name)
        
        if not os.path.exists(dat_path):
            if not self.download_dat(system_name):
                return False
                
        try:
            self.standard_names = {}
            
            # Parse clrmamepro format (text-based)
            # We can use regex or simple line parsing
            # Format:
            # game (
            #   name "Game Name"
            #   ...
            # )
            
            with open(dat_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                
            # Regex to find all game entries
            # We look for 'game (' then capture content until ')'
            # But nested parenthesis might be an issue? 
            # Usually clrmamepro doesn't nest ')' inside game block except in strings.
            # Let's just regex for 'name "..."' inside the file, assuming 'name' property belongs to a game.
            # This is a heuristic but usually works for these DATs.
            
            # Regex to match: name "Value"
            # We need to be careful not to match header name.
            # But header is 'clrmamepro ( name ... )'
            # Games are 'game ( name ... )'
            
            # Let's iterate line by line for better control
            current_block = None
            for line in content.splitlines():
                line = line.strip()
                if line.startswith('game ('):
                    current_block = 'game'
                elif line.startswith(')'):
                    current_block = None
                elif current_block == 'game' and line.startswith('name'):
                    # Extract name: name "Game Name"
                    match = re.search(r'name\s+"(.*?)"', line)
                    if match:
                        name = match.group(1)
                        # Store mapping: normalized -> list of standard names
                        norm_name = self.normalize_name(name)
                        if norm_name not in self.standard_names:
                            self.standard_names[norm_name] = []
                        self.standard_names[norm_name].append(name)
            
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
        If multiple matches, tries to match region.
        Returns None if no match found.
        """
        norm_name = self.normalize_name(name)
        candidates = self.standard_names.get(norm_name)
        
        if not candidates:
            return None
            
        if len(candidates) == 1:
            return candidates[0]
            
        # Try to match region
        # Extract region from input name if possible
        # Look for (Japan), (USA), (Europe), etc.
        regions = re.findall(r'\((.*?)\)', name)
        
        if regions:
            for region in regions:
                for candidate in candidates:
                    if f"({region})" in candidate:
                        return candidate
                        
        # If no region match, or no region in input, prefer USA -> Europe -> Japan -> World
        # Or just return the first one (which is usually the first one found in DAT)
        # Let's try to be smart: if input has no region, maybe default to World or USA?
        # For now, just return the first one if no region match found.
        return candidates[0]
