"""Read-only local and ADB artwork lookup for playlist analysis and browsing."""
import os
import shlex
import urllib.parse
from artwork_resolver import sanitize_filename, valid_image_file


def sanitize_thumbnail_filename(name):
    return sanitize_filename(name)


def local_thumbnail_path(thumbnails_dir, system_name, label, type_name="Named_Boxarts"):
    if not thumbnails_dir or not label:
        return None
    filename = sanitize_thumbnail_filename(label) + ".png"
    return os.path.join(thumbnails_dir, system_name, type_name, filename)


def boxart_dir_path(thumbnails_dir, system_name, type_name="Named_Boxarts"):
    if not thumbnails_dir or not system_name:
        return None
    return os.path.join(thumbnails_dir, system_name, type_name)


def adb_thumbnail_exists(thumbnails_dir, system_name, label, type_name="Named_Boxarts"):
    if not thumbnails_dir or not label:
        return False, None
    try:
        from retroarch_scanner import is_adb_uri, parse_adb_uri, _adb_shell
        if not is_adb_uri(thumbnails_dir):
            return False, None
        serial, remote_dir = parse_adb_uri(thumbnails_dir)
        if not remote_dir:
            return False, None
        filename = sanitize_thumbnail_filename(label) + ".png"
        remote_path = "/".join(part.strip("/") for part in [remote_dir, system_name, type_name, filename] if part)
        remote_path = "/" + remote_path if not remote_path.startswith("/") else remote_path
        script = f"test -f {shlex.quote(remote_path)} && echo 1 || echo 0"
        exists = (_adb_shell(serial, script, timeout=8) or "").strip().splitlines()
        return (exists[0] == "1" if exists else False), remote_path
    except Exception:
        return False, None


def build_existing_boxart_lookup(thumbnails_dir, system_name, type_name="Named_Boxarts"):
    if not thumbnails_dir or not system_name:
        return {"type": "none", "base_path": None, "filenames": set()}

    try:
        from retroarch_scanner import is_adb_uri, parse_adb_uri, _adb_shell
        if is_adb_uri(thumbnails_dir):
            serial, remote_dir = parse_adb_uri(thumbnails_dir)
            if not remote_dir:
                return {"type": "adb", "base_path": None, "filenames": set()}
            remote_path = "/".join(part.strip("/") for part in [remote_dir, system_name, type_name] if part)
            remote_path = "/" + remote_path if not remote_path.startswith("/") else remote_path
            output = _adb_shell(serial, f"ls -1 {shlex.quote(remote_path)} 2>/dev/null", timeout=15)
            filenames = {os.path.basename(line.strip()) for line in (output or "").splitlines() if line.strip()}
            return {"type": "adb", "serial": serial, "base_path": remote_path, "filenames": filenames}
    except Exception:
        return {"type": "adb", "serial": None, "base_path": None, "filenames": set()}

    local_dir = boxart_dir_path(thumbnails_dir, system_name, type_name)
    if not local_dir or not os.path.isdir(local_dir):
        return {"type": "local", "base_path": local_dir, "filenames": set()}
    try:
        filenames = {name for name in os.listdir(local_dir) if os.path.isfile(os.path.join(local_dir, name))}
    except OSError:
        filenames = set()
    return {"type": "local", "base_path": local_dir, "filenames": filenames}


def find_existing_boxart(thumbnails_dir, system_name, *labels, lookup=None):
    if not thumbnails_dir:
        return False, None
    if lookup is not None:
        filenames = lookup.get("filenames") or set()
        base_path = lookup.get("base_path")
        for label in labels:
            if not label:
                continue
            filename = sanitize_thumbnail_filename(label) + ".png"
            if filename in filenames:
                if lookup.get("type") == "adb":
                    remote_path = f"{base_path.rstrip('/')}/{filename}" if base_path else filename
                    serial = lookup.get("serial")
                    if serial and remote_path.startswith("/"):
                        return True, f"adb://{serial}{remote_path}"
                    return True, remote_path
                local_path = os.path.join(base_path, filename) if base_path else filename
                if valid_image_file(local_path):
                    return True, local_path
        return False, None

    try:
        from retroarch_scanner import is_adb_uri, parse_adb_uri
        if is_adb_uri(thumbnails_dir):
            serial, _remote_dir = parse_adb_uri(thumbnails_dir)
            for label in labels:
                exists, path = adb_thumbnail_exists(thumbnails_dir, system_name, label)
                if exists:
                    return True, f"adb://{serial}{path}" if path and path.startswith("/") else path
            return False, None
    except Exception:
        pass

    for label in labels:
        path = local_thumbnail_path(thumbnails_dir, system_name, label)
        if path and valid_image_file(path):
            return True, path
    return False, None


def cover_preview_url(cover_path):
    if not cover_path:
        return None
    return "/api/thumbnail/preview?path=" + urllib.parse.quote(str(cover_path), safe="")
