import pytest
from rom_paths import rom_filename, rom_title, artwork_titles


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
