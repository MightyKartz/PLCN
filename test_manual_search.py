import os
import sys
sys.path.append(os.path.join(os.getcwd(), 'src'))
from database import DatabaseManager

def test_manual_search():
    print("\n--- Testing Manual Search with Fuzzy Fallback ---")
    db_path = "test_manual_search.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    db = DatabaseManager(db_path)
    cursor = db.get_connection().cursor()
    cursor.execute("INSERT INTO translations (english_name, chinese_name, system) VALUES (?, ?, ?)", 
                   ("Fire Emblem - Monshou no Nazo", "火焰纹章 - 纹章之谜", "SNES"))
    db.get_connection().commit()
    
    # Test search
    results = db.search_by_keyword("火焰之纹章3")
    
    if len(results) > 0:
        print(f"[PASS] Found {len(results)} result(s):")
        for r in results:
            print(f"  - {r['chinese_name']} ({r['english_name']}) [{r['system']}]")
    else:
        print("[FAIL] No results found")
        
    db.close()
    if os.path.exists(db_path):
        os.remove(db_path)

if __name__ == "__main__":
    test_manual_search()
