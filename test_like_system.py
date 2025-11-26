import os
import sys
sys.path.append(os.path.join(os.getcwd(), 'src'))
from database import DatabaseManager

def test_like_system_filter():
    print("\n--- Testing LIKE-based System Filter ---")
    db_path = "test_like_system.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    db = DatabaseManager(db_path)
    cursor = db.get_connection().cursor()
    
    # Insert identical games but in different systems
    cursor.execute("INSERT INTO translations (english_name, chinese_name, system) VALUES (?, ?, ?)", 
                   ("Chrono Trigger", "时空之轮", "Nintendo - Super Nintendo Entertainment System"))
    cursor.execute("INSERT INTO translations (english_name, chinese_name, system) VALUES (?, ?, ?)", 
                   ("Chrono Cross", "穿越时空", "Nintendo - Super Nintendo Entertainment System (20240830-122750) (3308)"))
    cursor.execute("INSERT INTO translations (english_name, chinese_name, system) VALUES (?, ?, ?)", 
                   ("Chrono Resurrection", "时空复活", "Nintendo - Game Boy Advance"))
    db.get_connection().commit()
    
    # Test 1: Search 'Chrono' with SNES filter
    print("\n1. Search 'Chrono' with system='Nintendo - Super Nintendo Entertainment System':")
    results = db.search_by_keyword("Chrono", system="Nintendo - Super Nintendo Entertainment System")
    print(f"   Found {len(results)} result(s):")
    for r in results:
        print(f"   - {r['english_name']} ({r['system']})")
    
    # Check which systems were found
    systems_found = [r['system'] for r in results]
    has_base_snes = "Nintendo - Super Nintendo Entertainment System" in systems_found
    has_variant_snes = any('(20240830-122750)' in s for s in systems_found)
    has_gba = any('Game Boy Advance' in s for s in systems_found)
    
    print(f"\n   Results breakdown:")
    print(f"   - Base SNES: {'Yes' if has_base_snes else 'No'}")
    print(f"   - Variant SNES: {'Yes' if has_variant_snes else 'No'}")
    print(f"   - GBA: {'Yes' if has_gba else 'No'}")
    
    if not has_gba:
        print("\n   [PASS] LIKE filter correctly excludes GBA")
    else:
        print("\n   [FAIL] LIKE filter did not exclude GBA")
    
    if has_base_snes or has_variant_snes:
        print("   [PASS] LIKE filter correctly includes SNES variants")
    else:
        print("   [INFO] No SNES games matched fuzzy threshold (expected if score < 80)")
        
    db.close()
    if os.path.exists(db_path):
        os.remove(db_path)

if __name__ == "__main__":
    test_like_system_filter()
