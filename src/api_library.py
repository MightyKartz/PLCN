"""Library HTTP handlers; request transport is owned by server.py."""
import json
import os
from api_common import reply
import subprocess
import sys


def sources(handler, context, payload):
    config_path = context.CONFIG_FILE
    from library_sources import discover
    reply(handler, discover(config_path))


def overview(handler, context, query):
    from workbench_library import overview as read_overview
    reply(handler, read_overview(query.get('root', [''])[0]))


def recent(handler, context, payload):
    config_path = context.CONFIG_FILE
    from library_sources import remember
    reply(handler, remember(payload, config_path))


def list_files(handler, context, payload):
    path = payload.get('path', ['.'])[0]
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

        handler.send_response(200)
        handler.send_header("Content-type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps(response).encode())
    except Exception as e:
        handler.send_response(500)
        handler.end_headers()
        handler.wfile.write(json.dumps({"error": str(e)}).encode())


def scan_device(handler, context, payload):
    target_path = payload.get('path', [''])[0]
    try:
        from retroarch_scanner import scan_retroarch_target
        scan = scan_retroarch_target(target_path or None)

        handler.send_response(200)
        handler.send_header("Content-type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps(scan, ensure_ascii=False).encode("utf-8"))
    except Exception as e:
        handler.send_response(500)
        handler.send_header("Content-type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps({"error": str(e)}, ensure_ascii=False).encode("utf-8"))


def open_folder(handler, context, payload):
    try:
        data = payload
        target_path = data.get("path")
        if not target_path:
            handler.send_response(400)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"error": "Path is required"}).encode())
            return

        target_path = os.path.abspath(target_path)
        if not os.path.exists(target_path):
            handler.send_response(404)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"error": "Path does not exist"}).encode())
            return
        if not os.path.isdir(target_path):
            target_path = os.path.dirname(target_path)

        if sys.platform == "darwin":
            subprocess.Popen(["open", target_path])
        elif os.name == "nt":
            os.startfile(target_path)
        else:
            subprocess.Popen(["xdg-open", target_path])

        handler.send_response(200)
        handler.send_header("Content-type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps({"status": "success", "path": target_path}).encode())
    except Exception as e:
        handler.send_response(500)
        handler.send_header("Content-type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps({"error": str(e)}).encode())
    return
