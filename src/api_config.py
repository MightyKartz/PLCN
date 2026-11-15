"""Config HTTP handlers; request transport is owned by server.py."""
from safe_io import atomic_write_json, file_lock
from manual_overrides import build_override_entry, load_overrides, save_overrides, upsert_override
import app_paths
import json


def list_overrides(handler, context, payload):
    try:
        config = context.load_server_config()
        path = context.configured_overrides_path(config)
        entries = load_overrides(path)

        handler.send_response(200)
        handler.send_header("Content-type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps({
            "entries": entries,
            "path": path,
        }, ensure_ascii=False).encode("utf-8"))
    except Exception as e:
        handler.send_response(500)
        handler.send_header("Content-type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps({"error": str(e)}, ensure_ascii=False).encode("utf-8"))


def get_config(handler, context, payload):
    handler.send_response(200)
    handler.send_header("Content-type", "application/json")
    handler.end_headers()
    config = context.load_server_config()
    config.setdefault('rom_name_cn_path', str(app_paths.default_source()))
    handler.wfile.write(json.dumps(config, ensure_ascii=False).encode('utf-8'))
    return


def save_overrides_handler(handler, context, payload):
    try:
        data = payload
        config = context.load_server_config()
        path = context.configured_overrides_path(config)
        entry = build_override_entry(data)
        with file_lock(path):
            entries = upsert_override(load_overrides(path), entry, now=entry.get("updated_at"))
            save_overrides(path, entries)

        handler.send_response(200)
        handler.send_header("Content-type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps({
            "status": "success",
            "entry": entry,
            "entries": entries,
            "path": path,
        }, ensure_ascii=False).encode("utf-8"))
    except Exception as e:
        handler.send_response(500)
        handler.send_header("Content-type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps({"error": str(e)}, ensure_ascii=False).encode("utf-8"))
    return


def save_config(handler, context, payload):
    try:
        config_data = payload
        with file_lock(context.CONFIG_FILE):
            merged_config = context.merge_server_config(config_data)
            atomic_write_json(context.CONFIG_FILE, merged_config)
        handler.send_response(200)
        handler.send_header("Content-type", "application/json")
        handler.end_headers()
        handler.wfile.write(b'{"status": "success"}')
    except Exception as e:
        handler.send_response(500)
        handler.end_headers()
        handler.wfile.write(f'{{"status": "error", "message": "{str(e)}"}}'.encode())
    return
