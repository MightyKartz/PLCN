import pytest
from gallery_names import matching_gallery_name

PCE = 'NEC - PC Engine - TurboGrafx 16'


@pytest.mark.parametrize('source,official', [
    ('Daisenpuu (Japan) (En)', 'Daisenpuu (Japan)'),
    ('Darius Plus (Japan) (En) (SG Enhanced)', 'Darius Plus (Japan) (SG Enhanced)'),
    ('Kiki Kaikai (Japan) (En)', 'Kiki Kaikai (Japan)'),
    ('Break In (Japan) (En)', 'Break In (Japan)'),
    ('Kyuukyoku Tiger (Japan) (En)', 'Kyuukyoku Tiger (Japan)'),
    ('Ninja Ryuuken Den (Japan) (En,Ja,Zh)', 'Ninja Ryuukenden (Japan) (En,Ja,Zh)'),
    ('OutRun (Japan) (En)', 'Out Run (Japan)'),
    ('R-Type Part-2 (Japan)', 'R-Type II (Japan)'),
    ('Xevious - Fardraut Densetsu (Japan)', 'Xevious - Fardraut Saga (Japan)'),
])
def test_pce_failed_task_names_match_actual_gallery_names(source, official):
    assert matching_gallery_name(PCE, source, [official]) == official


def test_matching_does_not_switch_regions_revisions_parts_or_platforms():
    assert matching_gallery_name(PCE, 'R-Type Part-2 (Japan)', ['R-Type I (Japan)', 'R-Type II (USA)', 'R-Type II (Japan) (v1.1)']) is None
    assert matching_gallery_name('NES', 'R-Type Part-2 (Japan)', ['R-Type II (Japan)']) is None
    assert matching_gallery_name(PCE, 'Game (Japan) (En)', ['Game 2 (Japan)', 'Game (Japan) (Fr)']) is None
    assert matching_gallery_name(PCE, 'Game (Japan)', ['Game (Japan) (Beta)']) is None
    assert matching_gallery_name(PCE, 'OutRun (Japan)', ['Out Run (Japan)', 'OUT RUN (Japan)']) is None


def test_explicit_language_variant_wins_over_unannotated_image():
    names = ['Ninja Ryuukenden (Japan)', 'Ninja Ryuukenden (Japan) (En,Ja,Zh)']
    assert matching_gallery_name(PCE, 'Ninja Ryuuken Den (Japan) (En,Ja,Zh)', names) == names[1]


def test_dos_missing_year_matches_only_a_unique_release_and_preserves_editions():
    title = 'Uncharted Waters 2 - New Horizons'
    assert matching_gallery_name('DOS', title, [title + ' (1995)']) == title + ' (1995)'
    assert matching_gallery_name('DOS', title, [title + ' (1995)', title + ' (1996)']) is None
    assert matching_gallery_name('DOS', title + ' (1994)', [title + ' (1995)']) is None
    assert matching_gallery_name('DOS', title, [title + ' (1995) (Demo)']) is None
    assert matching_gallery_name('DOS', title, [title + ' (1995) (Japan)']) is None
    assert matching_gallery_name('DOS', title, ['Uncharted Waters (1990)']) is None
    assert matching_gallery_name('NES', title, [title + ' (1995)']) is None
