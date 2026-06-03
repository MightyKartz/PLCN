import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from rom_fingerprint import build_rom_match_candidates


def write_minimal_zip_with_crc(path, entry_name, crc_hex):
    entry_bytes = entry_name.encode("utf-8")
    data = b"placeholder"
    crc = int(crc_hex, 16)
    size = len(data)

    local_header = struct.pack(
        "<IHHHHHIIIHH",
        0x04034B50,
        20,
        0,
        0,
        0,
        0,
        crc,
        size,
        size,
        len(entry_bytes),
        0,
    )

    central_dir_offset = len(local_header) + len(entry_bytes) + len(data)
    central_header = struct.pack(
        "<IHHHHHHIIIHHHHHII",
        0x02014B50,
        20,
        20,
        0,
        0,
        0,
        0,
        crc,
        size,
        size,
        len(entry_bytes),
        0,
        0,
        0,
        0,
        0,
        0,
    )
    central_dir_size = len(central_header) + len(entry_bytes)
    end_record = struct.pack(
        "<IHHHHIIH",
        0x06054B50,
        0,
        0,
        1,
        1,
        central_dir_size,
        central_dir_offset,
        0,
    )

    path.write_bytes(
        local_header
        + entry_bytes
        + data
        + central_header
        + entry_bytes
        + end_record
    )


def test_local_zip_internal_crc_becomes_match_candidate(tmp_path):
    zip_path = tmp_path / "unknown.zip"
    write_minimal_zip_with_crc(zip_path, "rom.bin", "0A015CAC")

    result = build_rom_match_candidates(str(zip_path), "DETECT")

    assert ("unknown", "rom-stem") in result.candidates
    assert ("unknown.zip", "rom-file") in result.candidates
    assert ("0A015CAC", "zip-crc") in result.candidates
    assert result.fingerprint_status == "readable"


def test_retroarch_crc32_field_is_normalized_before_matching():
    result = build_rom_match_candidates("/storage/roms/fbneo/wrong-name.zip", "0A015CAC|crc")

    assert ("0A015CAC", "playlist-crc") in result.candidates
    assert result.fingerprint_status == "not-local"


def test_detect_and_zero_crc32_are_not_used_as_candidates():
    detect_result = build_rom_match_candidates("/storage/roms/fbneo/aof3.zip", "DETECT")
    zero_result = build_rom_match_candidates("/storage/roms/fbneo/aof3.zip", "00000000|crc")

    assert all(source != "playlist-crc" for _, source in detect_result.candidates)
    assert all(source != "playlist-crc" for _, source in zero_result.candidates)
