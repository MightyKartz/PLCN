import pytest
from rom_paths import rom_filename, rom_title, artwork_titles, disc_group, preferred_disc_entry


@pytest.mark.parametrize('path,filename,title', [
    ('/游戏/仙魔大战 (日版).zip#Bikkuriman World (Japan).pce', 'Bikkuriman World (Japan).pce', 'Bikkuriman World (Japan)'),
    (r'C:\ROMs\中文.7z#folder\Game (USA).gba', 'Game (USA).gba', 'Game (USA)'),
    ('/roms/Game#1.gba', 'Game#1.gba', 'Game#1'),
    ('adb://device/sdcard/普通游戏.gba', '普通游戏.gba', '普通游戏'),
    ('/roms/中文.ZIP#subdir/Dr. Game.pce', 'Dr. Game.pce', 'Dr. Game'),
])
def test_archive_member_names_and_plain_names(path, filename, title):
    assert rom_filename(path) == filename
    assert rom_title(path) == title


def test_dos_title_candidates_use_archive_or_game_directory_without_changing_rom_display():
    path = r'C:\Roms\DOS\中文.ZIP#BIN\CDX.EXE'
    assert artwork_titles('DOS', path, '游戏') == ['游戏', '中文']
    assert rom_filename(path) == 'CDX.EXE'
    assert artwork_titles('DOS', '/DOS/Uncharted Waters/START.BAT', 'START') == ['Uncharted Waters']
    assert artwork_titles('DOS', '/DOS/CDX.EXE', 'CDX') == []
    assert artwork_titles('PCE', '/游戏.zip#Bikkuriman World.pce', '仙魔大战') == ['Bikkuriman World', '仙魔大战']


def test_multi_disc_titles_keep_separate_groups_without_m3u():
    items = [{'path': '/SS/Grandia CN (Disc 1).chd'},
             {'path': '/SS/Grandia CN (Disc 2).chd'}]
    assert disc_group(items[0]['path']) != disc_group(items[1]['path'])
    assert preferred_disc_entry(items) == {}


def test_cue_and_its_tracks_collapse_to_the_descriptor():
    items = [{'path': '/PS/Game (Disc 1).cue'},
             {'path': '/PS/Game (Disc 1) (Track 1).bin'},
             {'path': '/PS/Game (Disc 1) (Track 2).bin'}]
    assert preferred_disc_entry(items) == {'/PS/game (disc 1)': 0}


def test_m3u_row_owns_the_discs_it_stands_for():
    items = [{'path': '/SS/Grandia CN.m3u'},
             {'path': '/SS/Grandia CN (Disc 1).chd'},
             {'path': '/SS/Grandia CN (Disc 2).chd'}]
    preferred = preferred_disc_entry(items)
    assert preferred[disc_group(items[1]['path'])] == 0
    assert preferred[disc_group(items[2]['path'])] == 0
