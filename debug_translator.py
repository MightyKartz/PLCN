import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'src'))
from translator import Translator

def test_translation():
    translator = Translator("data/rom-name-cn", "Sony - PlayStation")
    
    chinese_name = "少年佣兵团"
    print(f"Testing reverse lookup for: '{chinese_name}'")
    
    # Check if it exists in reverse map
    if chinese_name in translator.reverse_translation_map:
        english_name = translator.reverse_translation_map[chinese_name]
        print(f"Found in reverse map: '{english_name}'")
        print(f"Expected: 'Soeldnerschild Special (Japan)'")
        print(f"Match: {english_name == 'Soeldnerschild Special (Japan)'}")
    else:
        print("Not found in reverse map!")
        
    # Print all keys in reverse map that contain '少年'
    print("\nSearching for keys containing '少年':")
    for key in translator.reverse_translation_map:
        if "少年" in key:
            print(f"Key: '{key}', Value: '{translator.reverse_translation_map[key]}'")
            print(f"Key hex: {key.encode('utf-8').hex()}")

if __name__ == "__main__":
    test_translation()
