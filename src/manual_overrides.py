import json
import os


def load_overrides(path):
    if not path or not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("entries"), list):
        return data["entries"]
    return []


def save_overrides(path, entries):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def _normalize_text(value):
    return str(value or "").strip().casefold()


def _rom_filename(path):
    if not path:
        return ""
    filename = os.path.basename(str(path))
    if "#" in filename:
        filename = filename.split("#", 1)[0]
    return filename


def _normalize_crc(value):
    value = str(value or "").strip()
    if not value or value.upper() == "DETECT":
        return ""
    if "|" in value:
        value = value.split("|", 1)[0]
    return value.strip().lower()


def find_override(entries, system, item):
    item_filename = _normalize_text(_rom_filename((item or {}).get("path")))
    item_crc = _normalize_crc((item or {}).get("crc32"))
    normalized_system = _normalize_text(system)

    for entry in entries or []:
        if _normalize_text(entry.get("system")) != normalized_system:
            continue

        entry_crc = _normalize_crc(entry.get("crc32"))
        if entry_crc and item_crc and entry_crc == item_crc:
            return entry

        entry_filename = _normalize_text(entry.get("rom_filename") or entry.get("filename"))
        if entry_filename and item_filename and entry_filename == item_filename:
            return entry

    return None
