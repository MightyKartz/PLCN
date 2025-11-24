import os
import sys

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from translator import Translator

def test_matching_logic():
    # Mock translator with some data
    # We pass a dummy system name, but we are manually injecting data anyway so it doesn't matter for this test
    # unless we want to test the loading logic itself.
    # For now, let's just keep the manual injection but update the constructor call.
    translator = Translator("data/rom-name-cn", "Sega - Saturn")
    # Manually inject some test data
    translator.translation_map = {
        "Dragon Force": "龙之力量",
        "CorrectGameName": "正确游戏名",
        "Super Robot Taisen F (Japan) (Rev A) (10M, 11M, 12M, 13M)": "超级机器人大战F"
    }
    translator.normalization_map = {
        "dragonforce": "Dragon Force",
        "correctgamename": "CorrectGameName"
    }
    
    test_cases = [
        {
            "path": "/roms/Saturn/CorrectGameName/weird_file_name.iso",
            "label": "Weird Label",
            "expected_match": "正确游戏名", # Should match directory "CorrectGameName" -> normalized "correctgamename"
            "desc": "Directory Match"
        },
        {
            "path": "/roms/Saturn/SomeDir/CN [Dragon_Force].iso",
            "label": "Dragon Force",
            "expected_match": "龙之力量", # Should match filename "CN [Dragon_Force]" -> normalized "dragonforce"
            "desc": "Filename Normalization"
        },
        {
            "path": "/roms/Saturn/SomeDir/SRWF.iso",
            "label": "SRWF",
            "expected_match": "超级机器人大战F", # Should match acronym "SRWF"
            "desc": "Acronym Match"
        }
    ]
    
    print("Running Matching Logic Verification...")
    
    for case in test_cases:
        path = case['path']
        original_label = case['label']
        expected = case['expected_match']
        
        print(f"\nTest Case: {case['desc']}")
        print(f"Path: {path}")
        print(f"Label: {original_label}")
        
        # Replicate logic from plcn.py
        candidates = []
        if path:
            filename_no_ext = os.path.splitext(os.path.basename(path))[0]
            if filename_no_ext:
                candidates.append(filename_no_ext)
        
        if original_label and original_label not in candidates:
            candidates.append(original_label)
            
        if path:
            parent_dir = os.path.basename(os.path.dirname(path))
            if parent_dir and parent_dir not in candidates:
                candidates.append(parent_dir)
        
        print(f"Candidates: {candidates}")
        
        matched = None
        matched_std_en = None
        for candidate in candidates:
            translation, std_en = translator.translate(candidate)
            if translation != candidate:
                matched = translation
                matched_std_en = std_en
                print(f"Matched candidate '{candidate}' -> '{translation}' (Standard EN: '{std_en}')")
                break
        
        if matched == expected:
            print("RESULT: PASS")
        else:
            print(f"RESULT: FAIL (Expected '{expected}', got '{matched}')")

if __name__ == "__main__":
    test_matching_logic()
