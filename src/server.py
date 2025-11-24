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

class ConfigHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.path = "/plcn.html"
            return self.serve_template()
        elif self.path == "/api/config":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    self.wfile.write(f.read().encode())
            else:
                self.wfile.write(b"{}")
            return
        elif self.path.startswith("/api/fs/list"):
            # Simple file system browser API
            # Query param: path (default to current dir)
            from urllib.parse import urlparse, parse_qs
            query = parse_qs(urlparse(self.path).query)
            path = query.get('path', ['.'])[0]
            
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
            return
        elif self.path == "/api/systems":
            # List available systems from rom-name-cn directory
            try:
                config = {}
                if os.path.exists(CONFIG_FILE):
                    with open(CONFIG_FILE, 'r') as f:
                        config = json.load(f)
                
                rom_db_path = config.get("rom_name_cn_path", "data/rom-name-cn")
                if not os.path.exists(rom_db_path):
                    # Try relative to base path
                    rom_db_path = os.path.join(get_base_path(), rom_db_path)
                
                systems = []
                if os.path.exists(rom_db_path):
                    # Look for CSV files
                    files = glob.glob(os.path.join(rom_db_path, "*.csv"))
                    for f in files:
                        # Filename without extension is the system name
                        name = os.path.splitext(os.path.basename(f))[0]
                        systems.append(name)
                    systems.sort()
                
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"systems": systems}).encode())
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
            return
        elif self.path.startswith("/api/playlist/detect"):
            # Detect system from playlist file content
            from urllib.parse import urlparse, parse_qs
            query = parse_qs(urlparse(self.path).query)
            path = query.get('path', [''])[0]
            
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
            return
        elif self.path == '/api/execute':
            # SSE endpoint to run command and stream output
            self.send_response(200)
            self.send_header('Content-type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.end_headers()

            try:
                # Determine mode based on config
                if os.path.exists(CONFIG_FILE):
                    with open(CONFIG_FILE, 'r') as f:
                        config = json.load(f)
                else:
                    config = {}
                
                # Construct command
                if getattr(sys, 'frozen', False):
                    # Running as compiled executable
                    cmd = [sys.executable]
                else:
                    # Running as script
                    cmd = [sys.executable, '-u', 'src/plcn.py'] # -u for unbuffered
                
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )
                
                for line in process.stdout:
                    # Send data to client
                    data = json.dumps({'message': line.strip()})
                    self.wfile.write(f"data: {data}\n\n".encode())
                    self.wfile.flush()
                
                exit_code = process.wait()
                
                # Send completion or error message based on exit code
                if exit_code == 0:
                    self.wfile.write(f"data: {json.dumps({'done': True})}\n\n".encode())
                else:
                    self.wfile.write(f"data: {json.dumps({'error': f'Process exited with code {exit_code}'})}\n\n".encode())
                self.wfile.flush()
                
            except Exception as e:
                err_msg = json.dumps({'error': str(e)})
                self.wfile.write(f"data: {err_msg}\n\n".encode())
                self.wfile.flush()
            return

        # Default behavior for other files
        return super().do_GET()

    def do_POST(self):
        if self.path == "/api/config":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                config_data = json.loads(post_data)
                # Save to config.json
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
