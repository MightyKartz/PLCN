import os
import sys
import json
sys.path.append(os.path.join(os.getcwd(), 'src'))
from database import DatabaseManager

def test_search_results():
    print("\n--- Testing Search Results Structure ---")
    db_path = "test_search.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    db = DatabaseManager(db_path)
    cursor = db.get_connection().cursor()
    cursor.execute("INSERT INTO translations (english_name, chinese_name, system) VALUES (?, ?, ?)", 
                   ("Test Game", "测试游戏", "NES"))
    db.get_connection().commit()
    
    results = db.search_by_keyword("Test")
    if len(results) > 0:
        first_result = results[0]
        print(f"Result: {first_result}")
        if 'system' in first_result and first_result['system'] == 'NES':
            print("[PASS] System field present and correct")
        else:
            print("[FAIL] System field missing or incorrect")
    else:
        print("[FAIL] No results found")
        
    db.close()
    if os.path.exists(db_path):
        os.remove(db_path)

if __name__ == "__main__":
    test_search_results()
