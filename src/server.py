import http.server
import socketserver
import json
import os
import sys
import glob
import subprocess
import sqlite3
import tempfile

PORT = 7777
CONFIG_FILE = "config.json"

def get_base_path():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TEMPLATE_DIR = os.path.join(get_base_path(), "src", "templates")

# Job Management
import threading
import time
import uuid
import urllib.parse
from http.server import BaseHTTPRequestHandler

class JobManager:
    def __init__(self):
        self.jobs = {}
        self.lock = threading.Lock()

    def create_job(self):
        job_id = str(uuid.uuid4())
        with self.lock:
            self.jobs[job_id] = {
                'status': 'pending',
                'progress': 0,
                'total': 0,
                'message': '',
                'result': None,
                'error': None
            }
        return job_id

    def update_job(self, job_id, progress, total, message):
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id]['progress'] = progress
                self.jobs[job_id]['total'] = total
                self.jobs[job_id]['message'] = message
                self.jobs[job_id]['status'] = 'running'

    def complete_job(self, job_id, result=None):
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id]['status'] = 'completed'
                self.jobs[job_id]['result'] = result
                self.jobs[job_id]['progress'] = self.jobs[job_id]['total']

    def fail_job(self, job_id, error):
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id]['status'] = 'failed'
                self.jobs[job_id]['error'] = str(error)

    def get_job(self, job_id):
        with self.lock:
            return self.jobs.get(job_id)

job_manager = JobManager()

class ConfigHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        query_params = urllib.parse.parse_qs(parsed_path.query)

        if path == "/":
            self.path = "/plcn.html"
            return self.serve_template()
        elif path == "/api/config":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    self.wfile.write(f.read().encode())
            else:
                self.wfile.write(b"{}")
            return
        elif path == "/api/stats":
            self.get_stats()
        elif path == "/api/device/scan":
            target_path = query_params.get('path', [''])[0]
            self.scan_device(target_path)
        elif path == "/api/fs/list":
            target_path = query_params.get('path', ['.'])[0]
            self.list_files(target_path)
        elif path == "/api/systems":
            self.list_systems()
        elif path == "/api/playlist/detect":
            target_path = query_params.get('path', [''])[0]
            self.detect_system(target_path)
        elif path == "/api/search":
            keyword = query_params.get('query', [''])[0]
            system = query_params.get('system', [None])[0]
            self.search_db(keyword, system)
        elif path == "/api/progress":
            job_id = query_params.get('job_id', [''])[0]
            self.stream_progress(job_id)
        elif path == "/api/execute":
            # Legacy execute endpoint (SSE)
            self.send_response(200)
            self.send_header("Content-type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            # For compatibility, we just send a message
            self.wfile.write(b"data: " + json.dumps({"message": "Please use the new UI flow."}).encode() + b"\n\n")
            self.wfile.write(b"data: " + json.dumps({"done": True}).encode() + b"\n\n")
        else:
            # Default behavior for other files (e.g., static assets)
            return super().do_GET()

    def list_files(self, path):
        # Simple file system browser API
        # Query param: path (default to current dir)
        
        if not os.path.exists(path):
            path = '.'
        
        path = os.path.abspath(path)
        
        try:
            items = []
            # Add parent directory
            parent = os.path.dirname(path)
            items.append({"name": "..", "path": parent, "is_dir": True})
            
            with os.scandir(path) as it:
                for entry in it:
                    items.append({
                        "name": entry.name,
                        "path": entry.path,
                        "is_dir": entry.is_dir()
                    })
            
            # Sort: directories first, then files
            items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
            
            response = {
                "current_path": path,
                "items": items
            }
            
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def get_stats(self):
        try:
            config = {}
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)

            base_path = os.getcwd()
            rom_db_path = config.get("rom_name_cn_path") or config.get("single_rom_name_cn_path") or "data/rom-name-cn"
            if getattr(sys, 'frozen', False) and not os.path.isabs(rom_db_path):
                rom_db_path = os.path.join(sys._MEIPASS, rom_db_path)

            db_path = os.path.join(base_path, "plcn.db")
            database_count = 0
            database_ready = os.path.exists(db_path)
            database_error = None
            if database_ready:
                try:
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM translations")
                    database_count = cursor.fetchone()[0]
                    conn.close()
                except Exception as e:
                    database_error = str(e)

            dat_dir = os.path.join(base_path, "data", "libretro-db", "dat")
            if getattr(sys, 'frozen', False):
                dat_dir = os.path.join(sys._MEIPASS, "data", "libretro-db", "dat")
            dat_count = len(glob.glob(os.path.join(dat_dir, "*.dat"))) if os.path.exists(dat_dir) else 0
            csv_count = len(glob.glob(os.path.join(rom_db_path, "*.csv"))) if os.path.exists(rom_db_path) else 0
            offline_available = (database_count > 0 or csv_count > 0) and dat_count > 0

            response = {
                "database_count": database_count,
                "database_ready": database_ready and not database_error,
                "database_error": database_error,
                "dat_count": dat_count,
                "csv_count": csv_count,
                "offline_available": offline_available,
                "paths": {
                    "database": db_path,
                    "dat_dir": dat_dir,
                    "rom_name_cn": rom_db_path
                }
            }

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def scan_device(self, target_path):
        try:
            from retroarch_scanner import scan_retroarch_target
            scan = scan_retroarch_target(target_path or None)

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(scan, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}, ensure_ascii=False).encode("utf-8"))

    def list_systems(self):
        # List available systems from rom-name-cn directory
        try:
            config = {}
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
            
            rom_db_path = config.get("rom_name_cn_path", "data/rom-name-cn")
            if getattr(sys, 'frozen', False) and not os.path.isabs(rom_db_path):
                rom_db_path = os.path.join(sys._MEIPASS, rom_db_path)
            
            systems = []
            if os.path.exists(rom_db_path):
                # Look for CSV files
                files = glob.glob(os.path.join(rom_db_path, "*.csv"))
                for f in files:
                    # Filename without extension is the system name
                    name = os.path.splitext(os.path.basename(f))[0]
                    systems.append(name)
            
            # Add mapped systems from DatabaseManager
            from database import DatabaseManager
            for mapped_system in DatabaseManager.SYSTEM_MAPPINGS.keys():
                if mapped_system not in systems:
                    systems.append(mapped_system)
            
            systems.sort()
            
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"systems": systems}).encode())
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def detect_system(self, path):
        # Detect system from playlist file content
        if not path or not os.path.exists(path):
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error": "Invalid path"}')
            return

        try:
            system_name = ""
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                items = data.get('items', [])
                if items:
                    # Try to get db_name from the first item
                    # Format is usually "System Name.lpl"
                    db_name = items[0].get('db_name', '')
                    if db_name:
                        system_name = os.path.splitext(db_name)[0]
            
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"system_name": system_name}).encode())
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def search_db(self, keyword, system=None):
        try:
            # Load config to get rom_name_cn_path
            config = {}
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
            
            rom_name_cn_path = config.get("rom_name_cn_path", "data/rom-name-cn")
            print(f"DEBUG search_db: Original rom_name_cn_path = {rom_name_cn_path}")
            print(f"DEBUG search_db: sys.frozen = {getattr(sys, 'frozen', False)}")
            print(f"DEBUG search_db: sys._MEIPASS = {getattr(sys, '_MEIPASS', 'Not set')}")
            
            if getattr(sys, 'frozen', False) and not os.path.isabs(rom_name_cn_path):
                rom_name_cn_path = os.path.join(sys._MEIPASS, rom_name_cn_path)
                print(f"DEBUG search_db: Updated rom_name_cn_path = {rom_name_cn_path}")
            
            print(f"DEBUG search_db: Final rom_name_cn_path = {rom_name_cn_path}")
            print(f"DEBUG search_db: Path exists = {os.path.exists(rom_name_cn_path)}")
            if os.path.exists(rom_name_cn_path):
                csv_files = glob.glob(os.path.join(rom_name_cn_path, "*.csv"))
                print(f"DEBUG search_db: Found {len(csv_files)} CSV files")

            # Manual search now ONLY uses LibretroDB for comprehensive game coverage
            results = []
            
            if not system:
                self.send_response(400)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "System parameter required for search"}).encode())
                return
            
            print(f"DEBUG search_db: Searching LibretroDB for keyword='{keyword}', system='{system}'")
            
            try:
                # Create LibretroDB instance
                from libretro_db import LibretroDB
                storage_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
                libretro_db = LibretroDB(storage_path)
                
                # Load DAT file for the specified system
                print(f"DEBUG search_db: Loading DAT for system '{system}'...")
                if libretro_db.load_system_dat(system):
                    print(f"DEBUG search_db: DAT loaded successfully, searching...")
                    libretro_results = libretro_db.search(keyword, limit=50)
                    
                    print(f"DEBUG search_db: Found {len(libretro_results)} matches in LibretroDB")
                    
                    # Initialize DatabaseManager
                    from database import DatabaseManager
                    db_manager = DatabaseManager()
                    conn = db_manager.get_connection()
                    cursor = conn.cursor()
                    
                    # Track added English names to avoid duplicates
                    added_names = set()
                    
                    # 1. Process LibretroDB results
                    for name in libretro_results:
                        # Look up Chinese translation
                        cursor.execute("SELECT chinese_name FROM translations WHERE english_name = ?", (name,))
                        row = cursor.fetchone()
                        chinese_name = row[0] if row else ""
                        
                        results.append({
                            'english_name': name,
                            'chinese_name': chinese_name,
                            'system': system
                        })
                        added_names.add(name)
                        
                    # 2. Search Local Database (includes missing_games.csv)
                    # This allows finding games that are NOT in LibretroDB but are in our local files
                    print(f"DEBUG search_db: Searching local DB for '{keyword}'...")
                    local_results = db_manager.search_by_keyword(keyword, system=system, limit=20)
                    print(f"DEBUG search_db: Found {len(local_results)} matches in local DB")
                    
                    for item in local_results:
                        if item['english_name'] not in added_names:
                            results.append({
                                'english_name': item['english_name'],
                                'chinese_name': item['chinese_name'],
                                'system': system
                            })
                            added_names.add(item['english_name'])
                            
                else:
                    print(f"ERROR search_db: Failed to load DAT for system '{system}'")
                    
            except Exception as e:
                import traceback
                print(f"ERROR searching LibretroDB: {e}")
                print(traceback.format_exc())

            
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"results": results}).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def stream_progress(self, job_id):
        self.send_response(200)
        self.send_header("Content-type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        while True:
            job = job_manager.get_job(job_id)
            if not job:
                self.wfile.write(b"data: " + json.dumps({"error": "Job not found"}).encode() + b"\n\n")
                break
            
            data = {
                "status": job['status'],
                "progress": job['progress'],
                "total": job['total'],
                "message": job['message'],
                "result": job['result'],
                "error": job['error']
            }
            
            try:
                self.wfile.write(b"data: " + json.dumps(data).encode() + b"\n\n")
                self.wfile.flush()
            except BrokenPipeError:
                break

            if job['status'] in ['completed', 'failed']:
                break
            
            time.sleep(0.5)

    def do_POST(self):
        if self.path == "/api/fs/open":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)

            try:
                data = json.loads(post_data)
                target_path = data.get("path")
                if not target_path:
                    self.send_response(400)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Path is required"}).encode())
                    return

                target_path = os.path.abspath(target_path)
                if not os.path.exists(target_path):
                    self.send_response(404)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Path does not exist"}).encode())
                    return
                if not os.path.isdir(target_path):
                    target_path = os.path.dirname(target_path)

                if sys.platform == "darwin":
                    subprocess.Popen(["open", target_path])
                elif os.name == "nt":
                    os.startfile(target_path)
                else:
                    subprocess.Popen(["xdg-open", target_path])

                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "path": target_path}).encode())
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
            return

        if self.path == "/api/config":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                config_data = json.loads(post_data)
                with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                    json.dump(config_data, f, indent=4, ensure_ascii=False)
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status": "success"}')
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f'{{"status": "error", "message": "{str(e)}"}}'.encode())
            return
            
        elif self.path == "/api/playlist/preview":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data)
                playlist_path = data.get('playlist_path')
                system_name = data.get('system_name')
                
                config = {}
                if os.path.exists(CONFIG_FILE):
                    with open(CONFIG_FILE, 'r') as f:
                        config = json.load(f)
                rom_name_cn_path = config.get("rom_name_cn_path", "data/rom-name-cn")
                if getattr(sys, 'frozen', False) and not os.path.isabs(rom_name_cn_path):
                     rom_name_cn_path = os.path.join(sys._MEIPASS, rom_name_cn_path)

                from retroarch_scanner import is_adb_uri, materialize_adb_file
                effective_playlist_path = materialize_adb_file(playlist_path) if is_adb_uri(playlist_path) else playlist_path

                import plcn
                changes = plcn.analyze_playlist(effective_playlist_path, system_name, rom_name_cn_path)
                
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "changes": changes,
                    "source": {
                        "playlist_path": playlist_path,
                        "local_playlist_path": effective_playlist_path if is_adb_uri(playlist_path) else None,
                        "transport": "adb" if is_adb_uri(playlist_path) else "local"
                    }
                }).encode())
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
            return

        elif self.path == "/api/playlist/apply":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data)
                playlist_path = data.get('playlist_path')
                changes = data.get('changes')
                thumbnails_dir = data.get('thumbnails_dir')
                options = data.get('options') or {}
                download_thumbnails = options.get('download_thumbnails', True)
                
                # Create Job
                job_id = job_manager.create_job()
                
                def run_job(jid, p_path, chgs, t_dir, should_download):
                    try:
                        import plcn
                        from retroarch_scanner import (
                            backup_adb_file,
                            is_adb_uri,
                            materialize_adb_file,
                            push_adb_directory,
                            push_adb_file,
                        )
                        def progress_cb(curr, tot, msg):
                            job_manager.update_job(jid, curr, tot, msg)

                        remote_playlist = is_adb_uri(p_path)
                        remote_thumbnails = is_adb_uri(t_dir)
                        effective_playlist_path = p_path
                        effective_thumbnails_dir = t_dir

                        if remote_playlist:
                            job_manager.update_job(jid, 0, len(chgs or []), "正在读取实机游戏列表...")
                            effective_playlist_path = materialize_adb_file(p_path)

                        if remote_playlist and remote_thumbnails:
                            effective_thumbnails_dir = tempfile.mkdtemp(prefix="plcn-adb-thumbnails-")

                        summary = plcn.apply_changes(
                            effective_playlist_path,
                            chgs,
                            effective_thumbnails_dir,
                            progress_callback=progress_cb,
                            download_thumbnails=should_download
                        )

                        remote_backup = None
                        if remote_playlist:
                            job_manager.update_job(jid, len(chgs or []), len(chgs or []), "正在备份并写回实机游戏列表...")
                            remote_backup = backup_adb_file(p_path)
                            push_adb_file(effective_playlist_path, p_path)

                        if remote_playlist and remote_thumbnails and should_download:
                            job_manager.update_job(jid, len(chgs or []), len(chgs or []), "正在推送缩略图到实机...")
                            push_adb_directory(effective_thumbnails_dir, t_dir)

                        job_manager.complete_job(jid, {
                            "applied_count": len(chgs or []),
                            "download_summary": summary,
                            "transport": "adb" if remote_playlist else "local",
                            "remote_backup": remote_backup
                        })
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        job_manager.fail_job(jid, str(e))

                # Start background thread
                thread = threading.Thread(target=run_job, args=(job_id, playlist_path, changes, thumbnails_dir, download_thumbnails))
                thread.start()
                
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"job_id": job_id}).encode())
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
            return

        elif self.path == "/api/batch/apply":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data)
                batch_dir = data.get('batch_dir')
                thumbnails_dir = data.get('thumbnails_dir')
                rom_name_cn_path = data.get('rom_name_cn_path') or "data/rom-name-cn"
                options = data.get('options') or {}
                backup = options.get('backup', True)
                continue_on_error = options.get('continue_on_error', True)
                download_thumbnails = options.get('download_thumbnails', True)
                
                # Handle PyInstaller path for rom_name_cn_path
                if getattr(sys, 'frozen', False) and not os.path.isabs(rom_name_cn_path):
                     rom_name_cn_path = os.path.join(sys._MEIPASS, rom_name_cn_path)

                # Create Job
                job_id = job_manager.create_job()
                
                def run_batch_job(jid, b_dir, t_dir, r_path, use_backup, keep_going, should_download):
                    try:
                        import plcn
                        import glob
                        from thumbnail_downloader import ThumbnailDownloader
                        
                        # Find all .lpl files
                        playlist_files = glob.glob(os.path.join(b_dir, "*.lpl"))
                        total_files = len(playlist_files)
                        
                        if total_files == 0:
                            job_manager.fail_job(jid, "No .lpl files found in directory.")
                            return

                        job_manager.update_job(jid, 0, total_files, f"Found {total_files} playlists.")
                        
                        summaries = []
                        errors = []

                        for i, playlist_path in enumerate(playlist_files):
                            filename = os.path.basename(playlist_path)
                            job_manager.update_job(jid, i, total_files, f"Processing {filename}...")
                            
                            system_name = os.path.splitext(filename)[0]
                            
                            try:
                                # 1. Analyze
                                changes = plcn.analyze_playlist(playlist_path, system_name, r_path)
                                
                                # 2. Apply (with backup)
                                # We pass a dummy progress callback or None, as we track file-level progress here.
                                # Or we could aggregate progress? For simplicity, just file-level.
                                summary = plcn.apply_changes(
                                    playlist_path,
                                    changes,
                                    t_dir,
                                    backup=use_backup,
                                    download_thumbnails=should_download
                                )
                                summaries.append(summary)
                                
                            except Exception as e:
                                print(f"Error processing {filename}: {e}")
                                errors.append(f"{filename}: {e}")
                                if not keep_going:
                                    raise
                                
                        merged_summary = ThumbnailDownloader.merge_summaries(summaries)
                        job_manager.complete_job(jid, {
                            "processed_count": total_files,
                            "errors": errors,
                            "download_summary": merged_summary
                        })
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        job_manager.fail_job(jid, str(e))

                # Start background thread
                thread = threading.Thread(
                    target=run_batch_job,
                    args=(job_id, batch_dir, thumbnails_dir, rom_name_cn_path, backup, continue_on_error, download_thumbnails)
                )
                thread.start()
                
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"job_id": job_id}).encode())
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
            return

    def serve_template(self):
        try:
            with open(os.path.join(TEMPLATE_DIR, "plcn.html"), 'rb') as f:
                content = f.read()
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(content)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Template not found")

def run_server():
    # Change to the directory where we want to store config.json
    if getattr(sys, 'frozen', False):
        # If frozen, use the executable's directory
        exe_dir = os.path.dirname(sys.executable)
        os.chdir(exe_dir)
    else:
        # Development mode: use project root
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        os.chdir(project_root)
    
    print(f"DEBUG: sys.frozen = {getattr(sys, 'frozen', False)}")
    if getattr(sys, 'frozen', False):
        print(f"DEBUG: sys._MEIPASS = {getattr(sys, '_MEIPASS', 'Not Found')}")
    print(f"DEBUG: TEMPLATE_DIR = {TEMPLATE_DIR}")
    if os.path.exists(TEMPLATE_DIR):
        print(f"DEBUG: Contents of TEMPLATE_DIR: {os.listdir(TEMPLATE_DIR)}")
    else:
        print(f"DEBUG: TEMPLATE_DIR does not exist!")

    print(f"Starting server at http://localhost:{PORT}")
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), ConfigHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")

if __name__ == "__main__":
    run_server()
