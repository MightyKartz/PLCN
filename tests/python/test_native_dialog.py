from types import SimpleNamespace

import pytest

import native_dialog


@pytest.mark.parametrize('kind', ['rom', 'file'])
def test_rom_picker_does_not_inherit_playlist_filter(monkeypatch, kind):
    import tkinter
    from tkinter import filedialog
    calls=[]
    root=SimpleNamespace(withdraw=lambda:None,attributes=lambda *args:None,destroy=lambda:None)
    monkeypatch.setattr(tkinter,'Tk',lambda:root)
    def choose(**options):
        calls.append(options)
        return '/games/Bahamut_Senki_MD_CN_v1.0.1.md'
    monkeypatch.setattr(filedialog,'askopenfilename',choose)
    assert native_dialog.helper_pick(kind).endswith('.md')
    if kind == 'rom':
        assert 'filetypes' not in calls[0]
        assert 'ROM' in calls[0]['title']
    else:
        assert calls[0]['filetypes']==[('RetroArch playlist','*.lpl')]
