"""Local HTTP transport, session security and service startup."""
import hmac
import http.server
from http.cookies import SimpleCookie
import json
import os
import secrets
import socket
import sys
import urllib.parse

import app_paths
from api_common import reply
from api_routes import GET_ROUTES, POST_ROUTES
from app_version import VERSION
from job_manager import JobManager
from job_results import (
    thumbnail_preview_url, annotate_download_summary_paths, split_plcn_apply_result,
    build_apply_job_result,
)
from manual_overrides import default_overrides_path
from safe_io import atomic_write_json

PORT = 7777
CONFIG_FILE = str(app_paths.config_path())
SESSION_TOKEN = secrets.token_urlsafe(32)


class LocalHTTPServer(http.server.ThreadingHTTPServer):
    # Split UI assets arrive concurrently; the default backlog of five resets browser connections.
    request_queue_size = 32
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
UI_ASSETS = (
    'plcn.css', 'workflow.js', 'ui.js', 'config.js', 'library-navigation.js',
    'repair-model.js', 'preview.js', 'tasks.js',
    'library.js', 'discs.js', 'm3u.js', 'storage.js', 'artwork.js', 'welcome.js', 'content-scan.js', 'desktop.js',
)

# Retired single-game workbench keys; migrated to the plain library keys on load.
LEGACY_CONFIG_KEYS = {
    'single_playlist_path': 'playlist_path',
    'single_system_name': 'system_name',
    'single_thumbnails_dir': 'thumbnails_dir',
    'single_rom_name_cn_path': 'rom_name_cn_path',
}


def load_server_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {}
    legacy = {old: new for old, new in LEGACY_CONFIG_KEYS.items() if old in data}
    if not legacy:
        return data
    for old, new in legacy.items():
        value = data.pop(old)
        if value and not data.get(new):
            data[new] = value
    try:
        atomic_write_json(CONFIG_FILE, data)
    except (OSError, RuntimeError):
        pass
    return data


def configured_overrides_path(config=None):
    config = config if config is not None else load_server_config()
    return config.get("manual_overrides_path") or default_overrides_path()


def merge_server_config(config_data):
    merged_config = load_server_config()
    merged_config.update(config_data)
    return merged_config


ASSET_ROUTES = {"/assets/" + name: name for name in UI_ASSETS}
job_manager = JobManager()


class ConfigHandler(http.server.SimpleHTTPRequestHandler):
    # Domain handlers receive the live runtime module explicitly so workers,
    # launchers and requests all use the same config path and task manager.
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

    def serve_template(self):
        try:
            with open(os.path.join(TEMPLATE_DIR, "plcn.html"), 'rb') as f:
                content = f.read()
                content = content.replace(b'{{PLCN_VERSION}}', VERSION.encode('utf-8'))
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

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if not self.authorize(bootstrap=path == '/'):
            return
        if path == '/':
            self.serve_template()
        elif path in ASSET_ROUTES:
            filename = ASSET_ROUTES[path]
            content = (app_paths.resource_root() / 'src' / 'templates' / filename).read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/javascript; charset=utf-8' if filename.endswith('.js') else 'text/css; charset=utf-8')
            self.end_headers()
            self.wfile.write(content)
        elif path in GET_ROUTES:
            try:
                GET_ROUTES[path](self, sys.modules[__name__], urllib.parse.parse_qs(parsed.query))
            except Exception as error:
                reply(self, {'error': str(error)}, 400)
        else:
            self.send_error(404)

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
        route = POST_ROUTES.get(self.path)
        if route is None:
            self.send_error(404, 'Unknown endpoint')
            return
        try:
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError('请求必须是 JSON 对象')
            route(self, sys.modules[__name__], payload)
        except Exception as error:
            reply(self, {'error': str(error)}, 400)


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
        finally:
            # Release USB before run_server removes the instance lock/record.
            # A replacement process must not open a session while this one closes it.
            from mtp_runtime import close
            close()

if __name__ == "__main__":
    run_server()
