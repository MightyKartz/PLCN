import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path


EMPTY_CRC_VALUES = {"", "detect", "none", "null", "unknown", "00000000"}


def utc_now_string():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_crc(value):
    if value is None:
        return ""

    raw = str(value).strip()
    if "|" in raw:
        raw = raw.split("|", 1)[0].strip()
    if raw.lower().startswith("0x"):
        raw = raw[2:]

    compact = re.sub(r"[^0-9a-fA-F]", "", raw)
    if raw.casefold() in EMPTY_CRC_VALUES or compact.casefold() in EMPTY_CRC_VALUES:
        return ""
    return compact.upper()


def rom_filename_from_path(path):
    if not path:
        return ""
    filename = os.path.basename(str(path))
    if "#" in filename:
        filename = filename.split("#", 1)[0]
    return filename


def load_overrides(path):
    path = Path(path)
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        entries = data.get("entries", [])
        return entries if isinstance(entries, list) else []
    return []


def save_overrides(path, entries):
    path = Path(path)
    if path.parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(entries or [], f, ensure_ascii=False, indent=2)
        f.write("\n")


def override_system_key(value):
    return (value or "").strip().casefold()


def override_filename_key(value):
    return rom_filename_from_path(value).casefold()


def override_entry_key(entry):
    system_key = override_system_key(entry.get("system"))
    crc = normalize_crc(entry.get("crc32"))
    if crc:
        return "crc", system_key, crc
    filename = entry.get("rom_filename") or rom_filename_from_path(entry.get("rom_path"))
    return "filename", system_key, override_filename_key(filename)


def find_override(entries, system, item):
    system_key = override_system_key(system)
    item_crc = normalize_crc((item or {}).get("crc32"))
    item_filename = override_filename_key((item or {}).get("path"))

    if item_crc:
        for entry in entries or []:
            if override_system_key(entry.get("system")) != system_key:
                continue
            if normalize_crc(entry.get("crc32")) == item_crc:
                return entry

    if item_filename:
        for entry in entries or []:
            if override_system_key(entry.get("system")) != system_key:
                continue
            entry_filename = entry.get("rom_filename") or rom_filename_from_path(entry.get("rom_path"))
            if override_filename_key(entry_filename) == item_filename:
                return entry

    return None


def upsert_override(entries, entry, now=None):
    updated = dict(entry or {})
    updated["crc32"] = normalize_crc(updated.get("crc32"))
    if not updated.get("rom_filename"):
        updated["rom_filename"] = rom_filename_from_path(updated.get("rom_path"))
    updated["updated_at"] = now or utc_now_string()

    key = override_entry_key(updated)
    result = []
    replaced = False
    for existing in entries or []:
        if override_entry_key(existing) == key:
            result.append(updated)
            replaced = True
        else:
            result.append(existing)

    if not replaced:
        result.append(updated)
    return result


def default_overrides_path(config_dir=None):
    base_dir = config_dir or os.getcwd()
    return os.path.join(base_dir, "manual_overrides.json")


def build_override_entry(payload, now=None):
    payload = payload or {}
    source = payload.get("entry") or payload.get("change") or payload

    system = source.get("system") or payload.get("system") or ""
    rom_path = source.get("rom_path") or source.get("path") or payload.get("rom_path") or payload.get("path") or ""
    rom_filename = source.get("rom_filename") or rom_filename_from_path(rom_path)

    return {
        "system": system,
        "rom_path": rom_path,
        "rom_filename": rom_filename,
        "crc32": normalize_crc(source.get("crc32") or payload.get("crc32")),
        "new_label": source.get("new_label") or payload.get("new_label") or "",
        "thumbnail_source": source.get("thumbnail_source") or payload.get("thumbnail_source") or "",
        "updated_at": now or utc_now_string(),
    }
