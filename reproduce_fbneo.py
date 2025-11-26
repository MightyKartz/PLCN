import sys
import os
import re

# Add src to path
sys.path.append(os.path.abspath("src"))

from translator import Translator
from database import DatabaseManager

def clean_arcade_name(game_name):
    """
    Cleans arcade game names by removing region codes, version info, and dates.
    """
    # Remove region and date codes like (World 900227), (USA 920313), (Japan), etc.
    cleaned = re.sub(r'\s*\([^)]*\d{6}[^)]*\)$', '', game_name)  # Remove (Region YYMMDD)
    cleaned = re.sub(r'\s*\([^)]*\)$', '', cleaned)  # Remove remaining (Region) or (version)
    return cleaned.strip()

def test_fbneo_translation():
    print("Testing FBNeo Translation...")
    
    # Initialize DB and Translator
    # Assuming data/rom-name-cn exists and is populated
    translator = Translator("data/rom-name-cn", "FBNeo - Arcade Games")
    
    test_cases = [
        "1941: Counter Attack (World 900227)",
        "Street Fighter II' - Champion Edition (USA 920313)",
        "Super Sidekicks 3 - The Next Glory / Tokuten Ou 3 - Eikou e no Michi",
        "Vampire: The Night Warriors (Japan 940705 alt)"
    ]
    
    for original in test_cases:
        print(f"\nOriginal: '{original}'")
        cleaned = clean_arcade_name(original)
        print(f"Cleaned:  '{cleaned}'")
        
        cn, en = translator.translate(cleaned)
        print(f"Result:   CN='{cn}', EN='{en}'")
        
        if cn == cleaned and en == cleaned:
            print("-> NO MATCH")
        else:
            print("-> MATCH FOUND")

if __name__ == "__main__":
    test_fbneo_translation()
