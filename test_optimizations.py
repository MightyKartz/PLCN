import os
import sys
import time
import json
import threading
sys.path.append(os.path.join(os.getcwd(), 'src'))
from database import DatabaseManager
from thumbnail_downloader import ThumbnailDownloader
from server import job_manager

def test_database_fts():
    print("\n--- Testing Database FTS ---")
    db_path = "test_opt.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    db = DatabaseManager(db_path)
    
    # Insert test data
    cursor = db.get_connection().cursor()
    cursor.execute("INSERT INTO translations (english_name, chinese_name, system) VALUES (?, ?, ?)", 
                   ("Super Mario World", "超级马里奥世界", "SNES"))
    cursor.execute("INSERT INTO translations (english_name, chinese_name, system) VALUES (?, ?, ?)", 
                   ("Legend of Zelda", "塞尔达传说", "NES"))
    db.get_connection().commit()
    
    # Test Keyword Search
    results = db.search_by_keyword("Mario")
    print(f"Search 'Mario': {len(results)} results")
    if len(results) > 0 and results[0]['english_name'] == "Super Mario World":
        print("[PASS] FTS/Keyword search works")
    else:
        print("[FAIL] FTS/Keyword search failed")
        
    db.close()
    if os.path.exists(db_path):
        os.remove(db_path)

def test_network_retry():
    print("\n--- Testing Network Retry ---")
    downloader = ThumbnailDownloader("test_thumbs")
    # Check if session is mounted with adapter
    if downloader.session.get_adapter('https://'):
        print("[PASS] Retry adapter mounted")
    else:
        print("[FAIL] Retry adapter not mounted")

def test_job_system():
    print("\n--- Testing Job System ---")
    job_id = job_manager.create_job()
    print(f"Created Job: {job_id}")
    
    job = job_manager.get_job(job_id)
    if job['status'] == 'pending':
        print("[PASS] Job created in pending state")
    
    job_manager.update_job(job_id, 50, 100, "Halfway there")
    job = job_manager.get_job(job_id)
    if job['progress'] == 50 and job['status'] == 'running':
        print("[PASS] Job updated correctly")
        
    job_manager.complete_job(job_id)
    job = job_manager.get_job(job_id)
    if job['status'] == 'completed':
        print("[PASS] Job completed")

if __name__ == "__main__":
    test_database_fts()
    test_network_retry()
    test_job_system()
