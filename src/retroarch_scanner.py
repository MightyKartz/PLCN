import json
import os
import hashlib
import shlex
import subprocess
import time
from pathlib import Path


PLAYLIST_DIR_NAMES = {"playlists", "playlist"}
THUMBNAIL_DIR_NAMES = {"thumbnails", "thumbnail"}
ADB_RETROARCH_ROOTS = [
    "/sdcard/RetroArch",
    "/storage/emulated/0/RetroArch",
    "/storage/emulated/0/retroarch",
    "/storage/emulated/0/Android/data/com.retroarch/files",
    "/storage/emulated/0/Android/data/com.retroarch.aarch64/files",
    "/storage/emulated/0/Android/data/com.retroarch.ra32/files",
    "/storage/emulated/0/Android/data/com.retroarch.ra64/files",
]


def _path_string(path):
    return str(path) if path else None


def _safe_resolve(path):
    return Path(path).expanduser().resolve(strict=False)


def is_adb_uri(path):
    return isinstance(path, str) and path.startswith("adb://")


def adb_uri(serial, remote_path=""):
    if not remote_path:
        return f"adb://{serial}"
    return f"adb://{serial}{remote_path if remote_path.startswith('/') else '/' + remote_path}"


def parse_adb_uri(uri):
    if not is_adb_uri(uri):
        raise ValueError(f"Not an ADB URI: {uri}")
    rest = uri[len("adb://"):]
    if "/" not in rest:
        return rest, ""
    serial, remote_path = rest.split("/", 1)
    return serial, "/" + remote_path


def _unique_paths(paths):
    seen = set()
    unique = []
    for path in paths:
        text = str(path)
        if text in seen:
            continue
        seen.add(text)
        unique.append(path)
    return unique


def default_scan_candidates():
    """Return shallow RetroArch root candidates without recursively walking drives."""
    home = Path.home()
    candidates = [
        home / "Library" / "Application Support" / "RetroArch",
        home / ".config" / "retroarch",
        home / "RetroArch",
        Path.cwd() / "RetroArch",
        Path.cwd() / "retroarch",
    ]

    mount_roots = [Path("/Volumes"), Path("/run/media") / os.environ.get("USER", ""), Path("/media") / os.environ.get("USER", ""), Path("/mnt")]
    for mount_root in mount_roots:
        if not mount_root.exists() or not mount_root.is_dir():
            continue
        try:
            for child in mount_root.iterdir():
                if not child.is_dir():
                    continue
                candidates.extend([
                    child / "RetroArch",
                    child / "retroarch",
                    child / "retroarch" / "playlists",
                    child / "RetroArch" / "playlists",
                ])
        except OSError:
            continue

    return [
        {
            "path": str(path),
            "exists": path.exists(),
            "label": path.name or str(path),
            "transport": "local",
        }
        for path in _unique_paths(candidates)
    ]


def _run_adb(args, timeout=10, adb_runner=None):
    if adb_runner:
        return adb_runner(args, timeout=timeout)

    try:
        result = subprocess.run(
            ["adb"] + list(args),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return result.stdout or result.stderr or ""
    return result.stdout


def list_adb_devices(adb_runner=None):
    output = _run_adb(["devices", "-l"], timeout=8, adb_runner=adb_runner)
    devices = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices"):
            continue
        parts = line.split()
        if len(parts) < 2 or parts[1] != "device":
            continue
        meta = {}
        for token in parts[2:]:
            if ":" in token:
                key, value = token.split(":", 1)
                meta[key] = value
        devices.append({
            "serial": parts[0],
            "model": meta.get("model", ""),
            "device": meta.get("device", ""),
            "transport": "adb",
        })
    return devices


def adb_scan_candidates(adb_runner=None):
    candidates = []
    for device in list_adb_devices(adb_runner=adb_runner):
        label = device.get("model") or device.get("serial")
        candidates.append({
            "path": adb_uri(device["serial"]),
            "exists": True,
            "label": f"{label} (ADB)",
            "transport": "adb",
            "device": device,
        })
    return candidates


def _find_child_dir(root, names):
    for name in names:
        candidate = root / name
        if candidate.exists() and candidate.is_dir():
            return candidate
    if not root.exists() or not root.is_dir():
        return None
    try:
        for child in root.iterdir():
            if child.is_dir() and child.name.lower() in names:
                return child
    except OSError:
        return None
    return None


def _find_config(root):
    for candidate in (root / "retroarch.cfg", root / "config" / "retroarch.cfg"):
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _infer_layout(target):
    if target.is_file() and target.suffix.lower() == ".lpl":
        playlists_dir = target.parent
        root = playlists_dir.parent if playlists_dir.name.lower() in PLAYLIST_DIR_NAMES else playlists_dir
        return root, playlists_dir

    if target.name.lower() in PLAYLIST_DIR_NAMES:
        return target.parent, target

    playlists_dir = _find_child_dir(target, PLAYLIST_DIR_NAMES)
    if playlists_dir:
        return target, playlists_dir

    try:
        if target.is_dir() and any(child.suffix.lower() == ".lpl" for child in target.iterdir() if child.is_file()):
            return target, target
    except OSError:
        pass

    return target, None


def _system_from_db_name(db_name):
    if not db_name:
        return ""
    return os.path.splitext(os.path.basename(db_name))[0]


def _read_playlist_summary(path):
    base = {
        "name": path.name,
        "path": str(path),
        "system": os.path.splitext(path.name)[0],
        "db_name": "",
        "item_count": 0,
        "valid": False,
        "error": None,
        "sample_labels": [],
        "modified_at": int(path.stat().st_mtime),
    }

    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        items = data.get("items", [])
        if not isinstance(items, list):
            raise ValueError("Playlist items must be a list")

        db_name = ""
        for item in items:
            if isinstance(item, dict) and item.get("db_name"):
                db_name = item.get("db_name")
                break

        sample_labels = [
            item.get("label") or os.path.basename(item.get("path", ""))
            for item in items[:3]
            if isinstance(item, dict)
        ]

        base.update({
            "system": _system_from_db_name(db_name) or base["system"],
            "db_name": db_name,
            "item_count": len(items),
            "valid": True,
            "sample_labels": sample_labels,
        })
    except Exception as exc:
        base["error"] = str(exc)

    return base


def _list_playlists(playlists_dir):
    if not playlists_dir or not playlists_dir.exists() or not playlists_dir.is_dir():
        return []
    try:
        paths = sorted(
            [path for path in playlists_dir.iterdir() if path.is_file() and path.suffix.lower() == ".lpl"],
            key=lambda path: path.name.lower(),
        )
    except OSError:
        return []
    return [_read_playlist_summary(path) for path in paths]


def _adb_shell(serial, script, timeout=12, adb_runner=None):
    return _run_adb(["-s", serial, "shell", script], timeout=timeout, adb_runner=adb_runner)


def _adb_cat(serial, remote_path, timeout=20, adb_runner=None):
    return _run_adb(["-s", serial, "exec-out", "cat", remote_path], timeout=timeout, adb_runner=adb_runner)


def _adb_first_line(output):
    for line in (output or "").splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def _find_adb_root(serial, requested_path="", adb_runner=None):
    if requested_path and requested_path.endswith(".lpl"):
        playlists_dir = os.path.dirname(requested_path)
        root = os.path.dirname(playlists_dir) if os.path.basename(playlists_dir).lower() in PLAYLIST_DIR_NAMES else playlists_dir
        return root, playlists_dir

    if requested_path and os.path.basename(requested_path).lower() in PLAYLIST_DIR_NAMES:
        return os.path.dirname(requested_path), requested_path

    if requested_path:
        script = f'if [ -d {shlex.quote(requested_path + "/playlists")} ]; then echo {shlex.quote(requested_path)}; fi'
        found = _adb_first_line(_adb_shell(serial, script, adb_runner=adb_runner))
        if found:
            return found, f"{found}/playlists"

    quoted_roots = " ".join(shlex.quote(path) for path in ADB_RETROARCH_ROOTS)
    script = (
        f"for p in {quoted_roots}; do "
        "[ -d \"$p/playlists\" ] && echo \"$p\"; "
        "done; "
        "for p in /storage/*/RetroArch /storage/*/retroarch; do "
        "[ -d \"$p/playlists\" ] && echo \"$p\"; "
        "done"
    )
    found = _adb_first_line(_adb_shell(serial, script, adb_runner=adb_runner))
    if found:
        return found, f"{found}/playlists"
    return requested_path, None


def _find_adb_thumbnails(serial, root, adb_runner=None):
    if not root:
        return ""
    script = f'if [ -d {shlex.quote(root + "/thumbnails")} ]; then echo {shlex.quote(root + "/thumbnails")}; fi'
    return _adb_first_line(_adb_shell(serial, script, adb_runner=adb_runner))


def _find_adb_config(serial, root, adb_runner=None):
    candidates = [
        f"{root}/retroarch.cfg" if root else "",
        f"{root}/config/retroarch.cfg" if root else "",
        "/storage/emulated/0/Android/data/com.retroarch/files/retroarch.cfg",
        "/storage/emulated/0/Android/data/com.retroarch.aarch64/files/retroarch.cfg",
        "/storage/emulated/0/Android/data/com.retroarch.ra32/files/retroarch.cfg",
        "/storage/emulated/0/Android/data/com.retroarch.ra64/files/retroarch.cfg",
    ]
    quoted = " ".join(shlex.quote(path) for path in candidates if path)
    script = f"for c in {quoted}; do [ -f \"$c\" ] && echo \"$c\" && break; done"
    return _adb_first_line(_adb_shell(serial, script, adb_runner=adb_runner))


def _adb_stat_mtime(serial, remote_path, adb_runner=None):
    script = f"stat -c %Y {shlex.quote(remote_path)} 2>/dev/null || echo 0"
    output = _adb_first_line(_adb_shell(serial, script, adb_runner=adb_runner))
    try:
        return int(output)
    except (TypeError, ValueError):
        return 0


def _read_adb_playlist_summary(serial, remote_path, adb_runner=None):
    base = {
        "name": os.path.basename(remote_path),
        "path": adb_uri(serial, remote_path),
        "remote_path": remote_path,
        "system": os.path.splitext(os.path.basename(remote_path))[0],
        "db_name": "",
        "item_count": 0,
        "valid": False,
        "error": None,
        "sample_labels": [],
        "modified_at": _adb_stat_mtime(serial, remote_path, adb_runner=adb_runner),
        "transport": "adb",
    }

    try:
        content = _adb_cat(serial, remote_path, adb_runner=adb_runner)
        data = json.loads(content)
        items = data.get("items", [])
        if not isinstance(items, list):
            raise ValueError("Playlist items must be a list")

        db_name = ""
        for item in items:
            if isinstance(item, dict) and item.get("db_name"):
                db_name = item.get("db_name")
                break

        base.update({
            "system": _system_from_db_name(db_name) or base["system"],
            "db_name": db_name,
            "item_count": len(items),
            "valid": True,
            "sample_labels": [
                item.get("label") or os.path.basename(item.get("path", ""))
                for item in items[:3]
                if isinstance(item, dict)
            ],
        })
    except Exception as exc:
        base["error"] = str(exc)

    return base


def _list_adb_playlists(serial, playlists_dir, adb_runner=None):
    if not playlists_dir:
        return []
    script = f"find {shlex.quote(playlists_dir)} -maxdepth 1 -type f -name '*.lpl' 2>/dev/null | sort"
    output = _adb_shell(serial, script, adb_runner=adb_runner)
    return [
        _read_adb_playlist_summary(serial, line.strip(), adb_runner=adb_runner)
        for line in output.splitlines()
        if line.strip()
    ]


def _scan_adb_target(target_path, candidates, adb_runner=None):
    serial, requested_path = parse_adb_uri(target_path)
    devices = {device["serial"]: device for device in list_adb_devices(adb_runner=adb_runner)}
    device = devices.get(serial, {"serial": serial, "model": "", "device": "", "transport": "adb"})

    root, playlists_dir = _find_adb_root(serial, requested_path, adb_runner=adb_runner)
    thumbnails_dir = _find_adb_thumbnails(serial, root, adb_runner=adb_runner)
    config_file = _find_adb_config(serial, root, adb_runner=adb_runner)
    playlists = _list_adb_playlists(serial, playlists_dir, adb_runner=adb_runner)
    total_items = sum(item["item_count"] for item in playlists if item.get("valid"))
    status = "ready" if playlists else "no_playlists"
    label = device.get("model") or serial

    return {
        "connected": True,
        "transport": "adb",
        "device": device,
        "target_path": target_path,
        "root_path": adb_uri(serial, root) if root else adb_uri(serial),
        "status": status,
        "message": f"已通过 ADB 识别 {label} 的 RetroArch 游戏列表。" if playlists else f"已连接 {label}，但未找到 .lpl 游戏列表。",
        "directories": {
            "playlists": adb_uri(serial, playlists_dir) if playlists_dir else None,
            "thumbnails": adb_uri(serial, thumbnails_dir) if thumbnails_dir else None,
            "config": adb_uri(serial, config_file) if config_file else None,
        },
        "playlists": playlists,
        "totals": {
            "playlists": len(playlists),
            "items": total_items,
        },
        "candidates": candidates,
    }


def materialize_adb_file(uri, cache_dir=".plcn_runtime/adb", adb_runner=None):
    serial, remote_path = parse_adb_uri(uri)
    if not remote_path:
        raise ValueError("ADB URI must include a remote file path")

    digest = hashlib.sha1(f"{serial}\n{remote_path}".encode("utf-8")).hexdigest()[:12]
    target_dir = Path(cache_dir) / serial
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{digest}-{os.path.basename(remote_path)}"
    content = _adb_cat(serial, remote_path, adb_runner=adb_runner)
    target_path.write_text(content, encoding="utf-8")
    return str(target_path)


def backup_adb_file(uri, adb_runner=None):
    serial, remote_path = parse_adb_uri(uri)
    if not remote_path:
        raise ValueError("ADB URI must include a remote file path")
    backup_path = f"{remote_path}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
    script = f"cp {shlex.quote(remote_path)} {shlex.quote(backup_path)}"
    _adb_shell(serial, script, adb_runner=adb_runner)
    return adb_uri(serial, backup_path)


def push_adb_file(local_path, uri, adb_runner=None):
    serial, remote_path = parse_adb_uri(uri)
    if not remote_path:
        raise ValueError("ADB URI must include a remote file path")
    _run_adb(["-s", serial, "push", local_path, remote_path], timeout=30, adb_runner=adb_runner)
    return uri


def push_adb_directory(local_dir, uri, adb_runner=None):
    serial, remote_path = parse_adb_uri(uri)
    if not remote_path:
        raise ValueError("ADB URI must include a remote directory path")
    _adb_shell(serial, f"mkdir -p {shlex.quote(remote_path)}", adb_runner=adb_runner)
    _run_adb(["-s", serial, "push", f"{local_dir}/.", remote_path], timeout=120, adb_runner=adb_runner)
    return uri


def scan_retroarch_target(target_path=None, *, local_candidates=None, adb_runner=None):
    local_candidate_list = default_scan_candidates() if local_candidates is None else local_candidates
    adb_candidate_list = adb_scan_candidates(adb_runner=adb_runner)
    candidates = local_candidate_list + adb_candidate_list

    if target_path and is_adb_uri(target_path):
        return _scan_adb_target(target_path, candidates, adb_runner=adb_runner)

    if not target_path:
        for candidate in local_candidate_list:
            if not candidate["exists"]:
                continue
            scan = scan_retroarch_target(candidate["path"], local_candidates=local_candidate_list, adb_runner=adb_runner)
            if scan["connected"] and scan["playlists"]:
                scan["candidates"] = candidates
                return scan
        for candidate in adb_candidate_list:
            scan = _scan_adb_target(candidate["path"], candidates, adb_runner=adb_runner)
            if scan["connected"] and scan["playlists"]:
                return scan
        return {
            "connected": False,
            "target_path": "",
            "root_path": "",
            "status": "not_found",
            "message": "未找到默认 RetroArch 目录，请手动选择本地、挂载设备目录，或确认 ADB 设备已授权。",
            "directories": {"playlists": None, "thumbnails": None, "config": None},
            "playlists": [],
            "totals": {"playlists": 0, "items": 0},
            "candidates": candidates,
        }

    target = _safe_resolve(target_path)
    if not target.exists():
        return {
            "connected": False,
            "target_path": str(target),
            "root_path": "",
            "status": "not_found",
            "message": "目标目录不存在。",
            "directories": {"playlists": None, "thumbnails": None, "config": None},
            "playlists": [],
            "totals": {"playlists": 0, "items": 0},
            "candidates": candidates,
        }

    root, playlists_dir = _infer_layout(target)
    thumbnails_dir = _find_child_dir(root, THUMBNAIL_DIR_NAMES)
    config_file = _find_config(root)
    playlists = _list_playlists(playlists_dir)
    total_items = sum(item["item_count"] for item in playlists if item.get("valid"))
    status = "ready" if playlists else "no_playlists"

    return {
        "connected": True,
        "transport": "local",
        "target_path": str(target),
        "root_path": str(root),
        "status": status,
        "message": "已识别 RetroArch 游戏列表。" if playlists else "已连接目录，但未找到 .lpl 游戏列表。",
        "directories": {
            "playlists": _path_string(playlists_dir),
            "thumbnails": _path_string(thumbnails_dir),
            "config": _path_string(config_file),
        },
        "playlists": playlists,
        "totals": {
            "playlists": len(playlists),
            "items": total_items,
        },
        "candidates": candidates,
    }
