import pytest
from rom_paths import rom_filename, rom_title


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
