import os
import re
import zipfile
import zlib
from dataclasses import dataclass


@dataclass
class RomMatchCandidates:
    candidates: list
    fingerprint_status: str
    fingerprint_error: str = ""
    local_path: str = ""


def add_candidate(candidates, value, source):
    value = (value or "").strip()
    if not value:
        return
    key = (value.casefold(), source)
    if key in {(candidate.casefold(), candidate_source) for candidate, candidate_source in candidates}:
        return
    candidates.append((value, source))


def strip_archive_member(path):
    if not path:
        return ""
    return str(path).split("#", 1)[0]


def portable_basename(path):
    path = strip_archive_member(path).replace("\\", "/")
    return path.rsplit("/", 1)[-1] if "/" in path else path


def parse_retroarch_crc32(value):
    value = (value or "").strip()
    if not value or value.upper() == "DETECT":
        return None
    crc = value.split("|", 1)[0].strip().upper()
    if not re.fullmatch(r"[0-9A-F]{8}", crc):
        return None
    if crc == "00000000":
        return None
    return crc


def file_crc32(path):
    checksum = 0
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            checksum = zlib.crc32(chunk, checksum)
    return f"{checksum & 0xFFFFFFFF:08X}"


def add_local_file_fingerprints(candidates, local_path):
    if zipfile.is_zipfile(local_path):
        with zipfile.ZipFile(local_path) as archive:
            for entry in archive.infolist():
                if entry.is_dir():
                    continue
                add_candidate(candidates, f"{entry.CRC & 0xFFFFFFFF:08X}", "zip-crc")
        return

    add_candidate(candidates, file_crc32(local_path), "file-crc")


def build_rom_match_candidates(path, item_crc32=None):
    candidates = []
    outer_path = strip_archive_member(path)
    basename = portable_basename(path)
    stem = os.path.splitext(basename)[0]

    add_candidate(candidates, stem, "rom-stem")
    add_candidate(candidates, basename, "rom-file")

    parsed_crc = parse_retroarch_crc32(item_crc32)
    if parsed_crc:
        add_candidate(candidates, parsed_crc, "playlist-crc")

    if not outer_path or not os.path.exists(outer_path):
        return RomMatchCandidates(candidates, "not-local", local_path=outer_path)

    try:
        add_local_file_fingerprints(candidates, outer_path)
    except (OSError, zipfile.BadZipFile) as exc:
        return RomMatchCandidates(candidates, "unreadable", str(exc), outer_path)

    return RomMatchCandidates(candidates, "readable", local_path=outer_path)
