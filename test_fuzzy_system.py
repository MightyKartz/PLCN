import os
import sys
sys.path.append(os.path.join(os.getcwd(), 'src'))
from database import DatabaseManager

def test_fuzzy_search_with_system():
    print("\n--- Testing Fuzzy-Only Search with System Filter ---")
    db_path = "test_fuzzy_system.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    db = DatabaseManager(db_path)
    cursor = db.get_connection().cursor()
    
    # Insert games from different systems
    cursor.execute("INSERT INTO translations (english_name, chinese_name, system) VALUES (?, ?, ?)", 
                   ("Fire Emblem - Monshou no Nazo", "火焰纹章 - 纹章之谜", "Nintendo - Super Nintendo Entertainment System"))
    cursor.execute("INSERT INTO translations (english_name, chinese_name, system) VALUES (?, ?, ?)", 
                   ("Fire Emblem - Fuuin no Tsurugi", "火焰纹章 - 封印之剑", "Nintendo - Game Boy Advance"))
    db.get_connection().commit()
    
    # Test 1: Search without system filter
    print("\n1. Search '火焰之纹章' without system filter:")
    results = db.search_by_keyword("火焰之纹章")
    print(f"   Found {len(results)} result(s):")
    for r in results:
        print(f"   - {r['chinese_name']} ({r['system']})")
    
    # Test 2: Search with SNES system filter
    print("\n2. Search '火焰之纹章' with SNES system filter:")
    results = db.search_by_keyword("火焰之纹章", system="Nintendo - Super Nintendo Entertainment System")
    print(f"   Found {len(results)} result(s):")
    for r in results:
        print(f"   - {r['chinese_name']} ({r['system']})")
        
    if len(results) == 1 and results[0]['chinese_name'] == "火焰纹章 - 纹章之谜":
        print("   [PASS] System filter works correctly")
    else:
        print("   [FAIL] System filter failed")
        
    db.close()
    if os.path.exists(db_path):
        os.remove(db_path)

if __name__ == "__main__":
    test_fuzzy_search_with_system()
