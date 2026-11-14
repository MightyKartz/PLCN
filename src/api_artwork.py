"""Artwork HTTP handlers; request transport is owned by server.py."""
import mimetypes
import os
import shlex
import subprocess
import urllib.parse
from adb_runtime import adb_executable, subprocess_options
from task_control import checkpoint
from api_common import reply, background


def context(handler, context, payload):
    from single_artwork import entry_context
    reply(handler, entry_context(payload))


def resolve(handler, context, payload):
    config_path = context.CONFIG_FILE
    from artwork_identity import resolve
    reply(handler, resolve(payload, config_path))


def status(handler, context, payload):
    from single_artwork import image_status
    reply(handler, image_status(str(payload.get('path') or '')))


def search(handler, context, payload):
    import single_artwork
    reply(handler, single_artwork.search(payload))


def preview(handler, context, payload):
    import single_artwork
    reply(handler, single_artwork.preview(payload))


def apply(handler, context, payload):
    jobs = context.job_manager
    from single_artwork import apply
    token = payload.get('token')
    def write_image(jid):
        checkpoint(lambda: jobs.cancelled(jid))
        return apply(token)
    reply(handler, {'job_id': background(jobs, '更新单个游戏图片', write_image)})


def serve_thumbnail_preview(handler, context, payload):
    target_path = payload.get('path', [''])[0]
    allowed_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    if not target_path:
        handler.send_response(404)
        handler.end_headers()
        return

    ext = os.path.splitext(urllib.parse.urlparse(target_path).path)[1].lower()
    if ext not in allowed_exts:
        handler.send_response(415)
        handler.end_headers()
        return

    try:
        from retroarch_scanner import is_adb_uri, parse_adb_uri

        if is_adb_uri(target_path):
            serial, remote_path = parse_adb_uri(target_path)
            if not serial or not remote_path:
                raise FileNotFoundError(target_path)
            result = subprocess.run(
                [adb_executable(), "-s", serial, "exec-out", "sh", "-c", f"cat {shlex.quote(remote_path)}"], **subprocess_options(),
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
        handler.send_response(200)
        handler.send_header("Content-type", content_type)
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", str(len(content)))
        handler.end_headers()
        handler.wfile.write(content)
    except Exception:
        handler.send_response(404)
        handler.end_headers()


def thumbnail(handler, context, payload):
    from single_artwork import catalog_image
    try:
        if payload.get('candidate'):
            from secondary_artwork import thumbnail
            content = thumbnail(payload['candidate'][0])
        else:
            content = catalog_image(payload.get('system', [''])[0], payload.get('kind', [''])[0], payload.get('name', [''])[0])
        handler.send_response(200)
        handler.send_header('Content-Type', 'image/png')
        handler.send_header('Content-Length', str(len(content)))
        handler.end_headers()
        handler.wfile.write(content)
    except (OSError, ValueError, RuntimeError) as error:
        reply(handler, {'error': str(error)}, 400)
