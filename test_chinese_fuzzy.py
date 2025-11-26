import os
import sys
import json
sys.path.append(os.path.join(os.getcwd(), 'src'))
from database import DatabaseManager
from translator import Translator

def test_chinese_fuzzy():
    print("\n--- Testing Chinese Fuzzy Search ---")
    db_path = "test_cn_fuzzy.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    # 1. Setup DB
    db = DatabaseManager(db_path)
    cursor = db.get_connection().cursor()
    # Insert standard name
    cursor.execute("INSERT INTO translations (english_name, chinese_name, system) VALUES (?, ?, ?)", 
                   ("Fire Emblem - Monshou no Nazo", "火焰纹章 - 纹章之谜", "SNES"))
    db.get_connection().commit()
    
    # 2. Test fuzzy search directly
    print("Testing database layer...")
    result = db.fuzzy_search_by_chinese("火焰之纹章3")
    if result == "Fire Emblem - Monshou no Nazo":
        print("[PASS] Database fuzzy search works")
    else:
        print(f"[FAIL] Database fuzzy search failed. Got: {result}")
        
    # 3. Test translator layer
    print("Testing translator layer...")
    translator = Translator("dummy_path")
    translator.db = db # Inject our test db
    
    cn, en = translator.translate("火焰之纹章3")
    print(f"Translated: {cn} -> {en}")
    
    if en == "Fire Emblem - Monshou no Nazo":
        print("[PASS] Translator fuzzy search works")
    else:
        print(f"[FAIL] Translator fuzzy search failed. Got: {en}")

    db.close()
    if os.path.exists(db_path):
        os.remove(db_path)

if __name__ == "__main__":
    test_chinese_fuzzy()
