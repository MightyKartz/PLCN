import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from libretro_db import LibretroDB


EXPECTED_AOF3 = "Art of Fighting 3 - The Path of the Warrior / Art of Fighting - Ryuuko no Ken Gaiden"


def test_fbneo_dat_maps_rom_zip_stem_to_standard_title():
    db = LibretroDB("data")

    assert db.load_system_dat("FBNeo - Arcade Games")

    assert db.get_standard_name("aof3") == EXPECTED_AOF3


def test_fbneo_dat_maps_rom_zip_filename_to_standard_title():
    db = LibretroDB("data")

    assert db.load_system_dat("FBNeo - Arcade Games")

    assert db.get_standard_name("aof3.zip") == EXPECTED_AOF3


def test_fbneo_dat_maps_rom_crc_to_standard_title():
    db = LibretroDB("data")

    assert db.load_system_dat("FBNeo - Arcade Games")

    assert db.get_standard_name("0A015CAC") == EXPECTED_AOF3
