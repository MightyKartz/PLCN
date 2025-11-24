import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'src'))
from translator import Translator

def debug():
    rom_name_cn_path = "data/rom-name-cn"
    system_name = "Sega - Saturn"
    
    print(f"Initializing Translator for {system_name}...")
    translator = Translator(rom_name_cn_path, system_name)
    
    print(f"Loaded {len(translator.translation_map)} translations.")
    print(f"Loaded {len(translator.normalization_map)} normalization entries.")
    
    test_str = "CN [Dragon_Force]"
    print(f"\nTesting translation for: '{test_str}'")
    
    norm = translator.normalize_name(test_str)
    print(f"Normalized '{test_str}' -> '{norm}'")
    
    if norm in translator.normalization_map:
        std_en = translator.normalization_map[norm]
        print(f"Found in normalization_map: '{std_en}'")
        if std_en in translator.translation_map:
            print(f"Translation: '{translator.translation_map[std_en]}'")
        else:
            print(f"Standard EN '{std_en}' NOT found in translation_map!")
    else:
        print(f"Normalized '{norm}' NOT found in normalization_map.")
        # Check if 'dragonforce' is in the map at all
        if 'dragonforce' in translator.normalization_map:
             print("Wait, 'dragonforce' IS in the map. Why didn't it match?")
        else:
             print("'dragonforce' is NOT in the map.")
             # Print some keys to see what's going on
             print("Sample normalization keys:", list(translator.normalization_map.keys())[:10])

if __name__ == "__main__":
    debug()
