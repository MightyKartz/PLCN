import http.server
import socketserver
import socket
import json
import os
import sys
import glob
import mimetypes
import shlex
import subprocess
import sqlite3
import tempfile
import secrets
import hmac
import re
from http.cookies import SimpleCookie
from safe_io import file_lock, atomic_write_json
from task_control import TaskCancelled, checkpoint
import app_paths
from manual_overrides import (
    build_override_entry,
    default_overrides_path,
    load_overrides,
    save_overrides,
    upsert_override,
)

PORT = 7777
CONFIG_FILE = str(app_paths.config_path())
SESSION_TOKEN = secrets.token_urlsafe(32)


class LocalHTTPServer(http.server.ThreadingHTTPServer):
    # Windows SO_REUSEADDR can let another instance bind the same address,
    # sending a browser to the wrong profile instead of using a free port.
    allow_reuse_address = os.name != 'nt'

    def server_bind(self):
        if os.name == 'nt':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

def get_base_path():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TEMPLATE_DIR = os.path.join(get_base_path(), "src", "templates")

def load_server_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def configured_overrides_path(config=None):
    config = config if config is not None else load_server_config()
    return config.get("manual_overrides_path") or default_overrides_path()

def merge_server_config(config_data):
    merged_config = load_server_config()
    merged_config.update(config_data)
    return merged_config

def thumbnail_preview_url(path):
    if not path:
        return None
    return "/api/thumbnail/preview?path=" + urllib.parse.quote(str(path), safe="")

def annotate_download_summary_paths(summary, local_root=None, final_root=None):
    if not summary:
        return summary

    try:
        from retroarch_scanner import is_adb_uri, parse_adb_uri
    except Exception:
        is_adb_uri = lambda value: False
        parse_adb_uri = None

    adb_target = bool(final_root and is_adb_uri(final_root) and parse_adb_uri)
    local_base = os.path.abspath(local_root) if local_root else None

    for detail in summary.get("details", []):
        path = detail.get("path")
        if path and adb_target and local_base:
            try:
                path_abs = os.path.abspath(path)
                if path_abs == local_base or path_abs.startswith(local_base + os.sep):
                    serial, remote_root = parse_adb_uri(final_root)
                    rel_path = os.path.relpath(path_abs, local_base).replace(os.sep, "/")
                    remote_path = "/".join(part.strip("/") for part in [remote_root, rel_path] if part)
                    path = f"adb://{serial}/{remote_path}" if remote_path else f"adb://{serial}"
                    detail["path"] = path
            except Exception:
                pass

        if detail.get("type") == "Named_Boxarts" and detail.get("status") in {"success", "skipped"} and path:
            detail["cover_path"] = path
            detail["cover_preview_url"] = thumbnail_preview_url(path)

    return summary

def split_plcn_apply_result(result):
    if isinstance(result, dict) and "download_summary" in result and "apply" in result:
        return result.get("download_summary") or {}, result.get("apply")
    return result or {}, None

def build_apply_job_result(summary, apply_summary=None, changes=None, transport="local", remote_backup=None):
    writeback = summary.get("writeback") if isinstance(summary, dict) else None
    if isinstance(writeback, dict):
        applied_count = len(writeback.get("applied") or [])
    elif isinstance(apply_summary, dict):
        applied_count = len(apply_summary.get("applied") or [])
    else:
        applied_count = len(changes or [])

    return {
        "applied_count": applied_count,
        "download_summary": summary,
        "apply": apply_summary,
        "transport": transport,
        "remote_backup": remote_backup,
    }

# Job Management
import threading
import time
import uuid
import urllib.parse
from http.server import BaseHTTPRequestHandler

class JobManager:
    def __init__(self):
        self.jobs = {}
        self.cancel_events = {}
        self.contexts = {}
        self.stopping = False
        self.lock = threading.Lock()

    def create_job(self):
        job_id = str(uuid.uuid4())
        with self.lock:
            if self.stopping:
                raise RuntimeError('PLCN 正在退出')
            self.cancel_events[job_id] = threading.Event()
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
                self.jobs[job_id]['status'] = 'cancelled' if self.cancel_events[job_id].is_set() else 'completed'
                self.jobs[job_id]['result'] = result
                self.jobs[job_id]['progress'] = self.jobs[job_id]['total']

    def fail_job(self, job_id, error):
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id]['status'] = 'cancelled' if isinstance(error, TaskCancelled) else 'failed'
                self.jobs[job_id]['error'] = str(error)

    def cancelled(self, job_id):
        return self.cancel_events[job_id].is_set()

    def cancel(self, job_id):
        with self.lock:
            if job_id not in self.jobs:
                raise ValueError('任务不存在')
            if self.jobs[job_id]['status'] in ('pending', 'running'):
                self.cancel_events[job_id].set()
                self.jobs[job_id]['message'] = '正在取消，将在安全步骤边界停止'

    def active(self):
        with self.lock:
            return any(job['status'] in ('pending', 'running') for job in self.jobs.values())

    def snapshot(self):
        with self.lock:
            return [dict(job, id=key) for key, job in reversed(list(self.jobs.items()))][:30]

    def get_job(self, job_id):
        with self.lock:
            return self.jobs.get(job_id)

job_manager = JobManager()

class ConfigHandler(http.server.SimpleHTTPRequestHandler):
    def authorize(self, bootstrap=False):
        host = self.headers.get('Host', '')
        expected = {f'127.0.0.1:{self.server.server_address[1]}', f'localhost:{self.server.server_address[1]}'}
        origin = self.headers.get('Origin')
        if host not in expected or (origin and origin != 'http://' + host) or self.headers.get('Sec-Fetch-Site') == 'cross-site':
            self.send_error(403, 'Only same-origin local requests are allowed')
            return False
        if bootstrap:
            return True
        try:
            cookies = SimpleCookie(self.headers.get('Cookie', ''))
            token = cookies['plcn_session'].value if 'plcn_session' in cookies else ''
        except Exception:
            token = ''
        if not hmac.compare_digest(token, SESSION_TOKEN):
            self.send_error(403, 'Open the PLCN page to start a local session')
            return False
        return True

    def do_HEAD(self):
        self.send_error(405)

    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        if not self.authorize(bootstrap=path == '/'):
            return
        query_params = urllib.parse.parse_qs(parsed_path.query)
        import desktop_api
        try:
            if desktop_api.get(self, path, job_manager, CONFIG_FILE):
                return
        except Exception as error:
            desktop_api.reply(self, {'error': str(error)}, 400)
            return

        if path == "/":
            self.path = "/plcn.html"
            return self.serve_template()
        elif path in ('/assets/desktop.js', '/assets/desktop.css', '/assets/workflow.js'):
            filename = path.rsplit('/', 1)[-1]
            content = (app_paths.resource_root() / 'src' / 'templates' / filename).read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/javascript; charset=utf-8' if filename.endswith('.js') else 'text/css; charset=utf-8')
            self.end_headers()
            self.wfile.write(content)
        elif path == "/api/config":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            
            config = load_server_config()
            config.setdefault('rom_name_cn_path', str(app_paths.default_source()))
            self.wfile.write(json.dumps(config, ensure_ascii=False).encode('utf-8'))
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
        elif path == "/api/thumbnail/preview":
            target_path = query_params.get('path', [''])[0]
            self.serve_thumbnail_preview(target_path)
        elif path == "/api/overrides/list":
            self.list_overrides()
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
            self.send_error(404)

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
            rom_db_path = config.get("rom_name_cn_path") or config.get("single_rom_name_cn_path") or str(app_paths.default_source())
            if getattr(sys, 'frozen', False) and not os.path.isabs(rom_db_path):
                rom_db_path = os.path.join(sys._MEIPASS, rom_db_path)

            from data_pack import catalog_path, cache_path
            db_path = str(catalog_path(rom_db_path) or cache_path(rom_db_path))
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

            dat_dir = str(app_paths.dat_storage() / "libretro-db" / "dat")
            bundled_dat = app_paths.resource_root() / 'data' / 'libretro-db' / 'dat'
            dat_count = len({os.path.basename(file) for folder in (dat_dir, str(bundled_dat))
                             for file in glob.glob(os.path.join(folder, '*.dat'))})
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

    def serve_thumbnail_preview(self, target_path):
        allowed_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
        if not target_path:
            self.send_response(404)
            self.end_headers()
            return

        ext = os.path.splitext(urllib.parse.urlparse(target_path).path)[1].lower()
        if ext not in allowed_exts:
            self.send_response(415)
            self.end_headers()
            return

        try:
            from retroarch_scanner import is_adb_uri, parse_adb_uri

            if is_adb_uri(target_path):
                serial, remote_path = parse_adb_uri(target_path)
                if not serial or not remote_path:
                    raise FileNotFoundError(target_path)
                result = subprocess.run(
                    ["adb", "-s", serial, "exec-out", "sh", "-c", f"cat {shlex.quote(remote_path)}"],
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
                if result.returncode != 0 or not result.stdout:
                    raise FileNotFoundError(target_path)
                content = result.stdout
            else:
                local_path = os.path.abspath(os.path.expanduser(target_path))
                if not os.path.isfile(local_path):
                    raise FileNotFoundError(local_path)
                with open(local_path, "rb") as f:
                    content = f.read()

            content_type = mimetypes.guess_type(target_path)[0] or "image/png"
            self.send_response(200)
            self.send_header("Content-type", content_type)
            self.send_header("Cache-Control", "max-age=300")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception:
            self.send_response(404)
            self.end_headers()

    def list_systems(self):
        # List available systems from rom-name-cn directory
        try:
            config = {}
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            
            rom_db_path = config.get("rom_name_cn_path", str(app_paths.default_source()))
            if getattr(sys, 'frozen', False) and not os.path.isabs(rom_db_path):
                rom_db_path = os.path.join(sys._MEIPASS, rom_db_path)
            
            systems = []
            if os.path.exists(rom_db_path):
                # Look for CSV files
                files = glob.glob(os.path.join(rom_db_path, "*.csv"))
                for f in files:
                    # Filename without extension is the system name
                    name = os.path.splitext(os.path.basename(f))[0]
                    name = re.sub(r'\s*\(\d{8}-\d{6}\).*$', '', name).strip()
                    if name != 'missing_games' and name not in systems:
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

    def list_overrides(self):
        try:
            config = load_server_config()
            path = configured_overrides_path(config)
            entries = load_overrides(path)

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "entries": entries,
                "path": path,
            }, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}, ensure_ascii=False).encode("utf-8"))

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
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            
            rom_name_cn_path = config.get("rom_name_cn_path", str(app_paths.default_source()))
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

            if not system:
                self.send_error(400, 'System parameter required')
                return
            from data_pack import open_database
            from libretro_db import LibretroDB
            db = open_database(rom_name_cn_path)
            try:
                # Local search remains available even when no DAT is cached.
                results = db.search_by_keyword(keyword, system=system, limit=30)
                dat = LibretroDB(str(app_paths.dat_storage()))
                if dat.load_system_dat(system):
                    names = dat.search(keyword, limit=30)
                    exact = dat.get_standard_name(keyword)
                    if exact:
                        names = [exact] + [name for name in names if name != exact]
                    known = {row['english_name'] for row in results}
                    for name in names:
                        if name not in known:
                            results.append({'english_name': name, 'chinese_name': db.search_by_english(name, system) or '', 'system': system})
                            known.add(name)
            finally:
                db.close()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'results': results}, ensure_ascii=False).encode('utf-8'))
        except Exception as error:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(error)}).encode('utf-8'))

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

            if job['status'] in ['completed', 'failed', 'cancelled']:
                break
            
            time.sleep(0.5)

    def do_POST(self):
        if not self.authorize():
            return
        if self.headers.get_content_type() != 'application/json':
            self.send_error(415, 'Expected application/json')
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 32 * 1024 * 1024:
                raise ValueError()
        except ValueError:
            self.send_error(413)
            return
        import desktop_api
        if self.path in desktop_api.POST_ROUTES:
            try:
                payload = json.loads(self.rfile.read(length))
                desktop_api.post(self, self.path, payload, job_manager, CONFIG_FILE)
            except Exception as error:
                desktop_api.reply(self, {'error': str(error)}, 400)
            return
        if self.path == "/api/overrides/save":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)

            try:
                data = json.loads(post_data)
                config = load_server_config()
                path = configured_overrides_path(config)
                entry = build_override_entry(data)
                with file_lock(path):
                    entries = upsert_override(load_overrides(path), entry, now=entry.get("updated_at"))
                    save_overrides(path, entries)

                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "success",
                    "entry": entry,
                    "entries": entries,
                    "path": path,
                }, ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}, ensure_ascii=False).encode("utf-8"))
            return

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
                with file_lock(CONFIG_FILE):
                    merged_config = merge_server_config(config_data)
                    atomic_write_json(CONFIG_FILE, merged_config)
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
                thumbnails_dir = data.get('thumbnails_dir')
                
                config = {}
                if os.path.exists(CONFIG_FILE):
                    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                rom_name_cn_path = config.get("rom_name_cn_path", str(app_paths.default_source()))
                manual_overrides_path = configured_overrides_path(config)
                if getattr(sys, 'frozen', False) and not os.path.isabs(rom_name_cn_path):
                     rom_name_cn_path = os.path.join(sys._MEIPASS, rom_name_cn_path)

                from retroarch_scanner import is_adb_uri, materialize_adb_file
                effective_playlist_path = materialize_adb_file(playlist_path) if is_adb_uri(playlist_path) else playlist_path

                import plcn
                changes = plcn.analyze_playlist(
                    effective_playlist_path,
                    system_name,
                    rom_name_cn_path,
                    thumbnails_dir,
                    manual_overrides_path=manual_overrides_path,
                )
                
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
                write_names = options.get('write_names', True)
                
                # Create Job
                job_id = job_manager.create_job()
                job_manager.contexts[job_id] = {'thumbnails_dir': thumbnails_dir}
                
                def run_job(jid, p_path, chgs, t_dir, should_download):
                    from contextlib import ExitStack
                    with ExitStack() as resources:
                        return run_apply_job(resources, jid, p_path, chgs, t_dir, should_download)

                def run_apply_job(resources, jid, p_path, chgs, t_dir, should_download):
                    try:
                        import plcn
                        from retroarch_scanner import (
                            verified_push_adb_playlist,
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
                            import hashlib
                            lock_name = hashlib.sha256(p_path.encode('utf-8')).hexdigest()
                            resources.enter_context(file_lock(app_paths.cache_dir() / 'locks' / lock_name))
                            staging_dir = resources.enter_context(tempfile.TemporaryDirectory(prefix='plcn-adb-'))
                            effective_playlist_path = materialize_adb_file(p_path, cache_dir=staging_dir)
                            with open(effective_playlist_path, encoding='utf-8-sig') as original:
                                expected_remote = json.load(original)

                        if remote_playlist and remote_thumbnails:
                            effective_thumbnails_dir = resources.enter_context(tempfile.TemporaryDirectory(prefix='plcn-adb-thumbnails-'))

                        apply_result = plcn.apply_changes(
                            effective_playlist_path,
                            chgs,
                            effective_thumbnails_dir,
                            progress_callback=progress_cb,
                            download_thumbnails=should_download, cancel_check=lambda: job_manager.cancelled(jid),
                            write_names=write_names, record_history=not remote_playlist
                        )
                        summary, apply_summary = split_plcn_apply_result(apply_result)

                        remote_backup = None
                        if remote_playlist and apply_summary and apply_summary.get('applied'):
                            job_manager.update_job(jid, len(chgs or []), len(chgs or []), "正在备份并验证实机游戏列表...")
                            remote_backup = verified_push_adb_playlist(effective_playlist_path, p_path, expected_remote)

                        if remote_playlist and remote_thumbnails and should_download:
                            job_manager.update_job(jid, len(chgs or []), len(chgs or []), "正在推送缩略图到实机...")
                            push_adb_directory(effective_thumbnails_dir, t_dir)

                        summary = annotate_download_summary_paths(
                            summary,
                            local_root=effective_thumbnails_dir,
                            final_root=t_dir,
                        )

                        job_manager.complete_job(jid, build_apply_job_result(
                            summary,
                            apply_summary=apply_summary,
                            changes=chgs,
                            transport="adb" if remote_playlist else "local",
                            remote_backup=remote_backup,
                        ))
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
                rom_name_cn_path = data.get('rom_name_cn_path') or load_server_config().get('rom_name_cn_path') or str(app_paths.default_source())
                options = data.get('options') or {}
                backup = options.get('backup', True)
                continue_on_error = options.get('continue_on_error', True)
                download_thumbnails = options.get('download_thumbnails', True)
                write_names = options.get('write_names', True)
                
                # Handle PyInstaller path for rom_name_cn_path
                if getattr(sys, 'frozen', False) and not os.path.isabs(rom_name_cn_path):
                     rom_name_cn_path = os.path.join(sys._MEIPASS, rom_name_cn_path)

                # Create Job
                job_id = job_manager.create_job()
                job_manager.contexts[job_id] = {'thumbnails_dir': thumbnails_dir}
                
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
                            if job_manager.cancelled(jid):
                                break
                            filename = os.path.basename(playlist_path)
                            job_manager.update_job(jid, i, total_files, f"Processing {filename}...")
                            
                            system_name = os.path.splitext(filename)[0]
                            
                            try:
                                # 1. Analyze
                                changes = plcn.analyze_playlist(playlist_path, system_name, r_path, t_dir, manual_overrides_path=configured_overrides_path())
                                
                                # 2. Apply (with backup)
                                # We pass a dummy progress callback or None, as we track file-level progress here.
                                # Or we could aggregate progress? For simplicity, just file-level.
                                apply_result = plcn.apply_changes(
                                    playlist_path,
                                    changes,
                                    t_dir,
                                    backup=use_backup,
                                    download_thumbnails=should_download, cancel_check=lambda: job_manager.cancelled(jid),
                                    write_names=write_names
                                )
                                summary, _apply_summary = split_plcn_apply_result(apply_result)
                                summary = annotate_download_summary_paths(
                                    summary,
                                    local_root=t_dir,
                                    final_root=t_dir,
                                )
                                summaries.append(summary)
                                
                            except TaskCancelled:
                                break
                            except Exception as e:
                                print(f"Error processing {filename}: {e}")
                                errors.append(f"{filename}: {e}")
                                if not keep_going:
                                    raise
                                
                        merged_summary = ThumbnailDownloader.merge_summaries(summaries)
                        job_manager.complete_job(jid, {
                            "processed_count": len(summaries),
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
                self.send_header('Set-Cookie', f'plcn_session={SESSION_TOKEN}; HttpOnly; SameSite=Strict; Path=/')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Frame-Options', 'DENY')
                self.end_headers()
                self.wfile.write(content)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Template not found")

def run_server(open_browser=False):
    from app_runtime import InstanceLock
    instance = InstanceLock(app_paths.user_data_dir())
    if not instance.acquire():
        url = instance.existing_url()
        if open_browser:
            import webbrowser
            webbrowser.open(url)
        return url
    try:
        app_paths.initialize()
        return _serve_instance(instance, open_browser)
    finally:
        instance.close()


def _serve_instance(instance, open_browser):
    try:
        httpd = LocalHTTPServer(('127.0.0.1', PORT), ConfigHandler)
    except OSError:
        httpd = LocalHTTPServer(('127.0.0.1', 0), ConfigHandler)
    with httpd:
        url = f'http://127.0.0.1:{httpd.server_address[1]}'
        httpd.instance_id = secrets.token_urlsafe(24)
        instance.publish(url, httpd.instance_id)
        print(f'Starting server at {url}')
        if open_browser:
            import webbrowser
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")

if __name__ == "__main__":
    run_server()
