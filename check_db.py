import sys
import os
sys.path.append(os.path.abspath("src"))

from database import DatabaseManager

# Initialize DB
db = DatabaseManager()

# Check if we have arcade data
cursor = db.get_connection().cursor()

# Count total records
cursor.execute("SELECT COUNT(*) FROM translations")
total = cursor.fetchone()[0]
print(f"Total translations in database: {total}")

# Check for arcade systems
arcade_systems = ["Arcade - CPS1", "Arcade - CPS2", "Arcade - CPS3", "Arcade - NEOGEO"]
for system in arcade_systems:
    cursor.execute("SELECT COUNT(*) FROM translations WHERE system LIKE ?", (f"{system}%",))
    count = cursor.fetchone()[0]
    print(f"{system}: {count} records")

# Search for "1941" explicitly
print("\n--- Searching for '1941' ---")
cursor.execute("SELECT english_name, chinese_name, system FROM translations WHERE english_name LIKE '1941%' LIMIT 5")
results = cursor.fetchall()
for row in results:
    print(f"EN: {row['english_name']}")
    print(f"CN: {row['chinese_name']}")
    print(f"System: {row['system']}")
    print()

db.close()
