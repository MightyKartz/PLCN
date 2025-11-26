import http.server
import socketserver
import json
import os
import sys
import glob
import subprocess

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

            # Initialize DB
            from database import DatabaseManager
            db = DatabaseManager()
            
            # Check if database is empty and import CSVs if needed
            # Check if database needs import (run once per session or if empty)
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT count(*) FROM translations")
            count = cursor.fetchone()[0]
            print(f"DEBUG search_db: Database contains {count} translations")
            
            # Use a class attribute to track if we've checked for updates this session
            if not hasattr(self.__class__, 'db_checked'):
                self.__class__.db_checked = False
            
            if count == 0 or not self.__class__.db_checked:
                print(f"Checking for new data in {rom_name_cn_path}...")
                db.import_csvs(rom_name_cn_path)
                self.__class__.db_checked = True
                
                # Check count again after import
                cursor.execute("SELECT count(*) FROM translations")
                count = cursor.fetchone()[0]
                print(f"DEBUG search_db: After import/check, database contains {count} translations")
            
            results = db.search_by_keyword(keyword, system=system)
            db.close()
            
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
                
                import plcn
                changes = plcn.analyze_playlist(playlist_path, system_name, rom_name_cn_path)
                
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"changes": changes}).encode())
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
                
                # Create Job
                job_id = job_manager.create_job()
                
                def run_job(jid, p_path, chgs, t_dir):
                    try:
                        import plcn
                        def progress_cb(curr, tot, msg):
                            job_manager.update_job(jid, curr, tot, msg)
                            
                        plcn.apply_changes(p_path, chgs, t_dir, progress_callback=progress_cb)
                        job_manager.complete_job(jid)
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        job_manager.fail_job(jid, str(e))

                # Start background thread
                thread = threading.Thread(target=run_job, args=(job_id, playlist_path, changes, thumbnails_dir))
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
                rom_name_cn_path = data.get('rom_name_cn_path')
                
                # Handle PyInstaller path for rom_name_cn_path
                if getattr(sys, 'frozen', False) and not os.path.isabs(rom_name_cn_path):
                     rom_name_cn_path = os.path.join(sys._MEIPASS, rom_name_cn_path)

                # Create Job
                job_id = job_manager.create_job()
                
                def run_batch_job(jid, b_dir, t_dir, r_path):
                    try:
                        import plcn
                        import glob
                        
                        # Find all .lpl files
                        playlist_files = glob.glob(os.path.join(b_dir, "*.lpl"))
                        total_files = len(playlist_files)
                        
                        if total_files == 0:
                            job_manager.fail_job(jid, "No .lpl files found in directory.")
                            return

                        job_manager.update_job(jid, 0, total_files, f"Found {total_files} playlists.")
                        
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
                                plcn.apply_changes(playlist_path, changes, t_dir, backup=True)
                                
                            except Exception as e:
                                print(f"Error processing {filename}: {e}")
                                
                        job_manager.complete_job(jid, f"Processed {total_files} playlists.")
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        job_manager.fail_job(jid, str(e))

                # Start background thread
                thread = threading.Thread(target=run_batch_job, args=(job_id, batch_dir, thumbnails_dir, rom_name_cn_path))
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
