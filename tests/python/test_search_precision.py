import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from database import DatabaseManager


def test_exact_english_search_prefers_matching_title_over_shared_region_noise(tmp_path):
    db = DatabaseManager(str(tmp_path / "search.db"))
    cursor = db.get_connection().cursor()
    cursor.execute(
        "INSERT INTO translations (english_name, chinese_name, system) VALUES (?, ?, ?)",
        ("DonPachi (USA, ver. 1.12, 95/05/2x)", "", "FBNeo - Arcade Games"),
    )
    cursor.execute(
        "INSERT INTO translations (english_name, chinese_name, system) VALUES (?, ?, ?)",
        (
            "Strider (USA, B-Board 90629B-3, buggy Street Fighter II conversion)",
            "出击飞龙（美版, 街霸II转换版）",
            "Arcade - CPS1",
        ),
    )
    db.get_connection().commit()

    results = db.search_by_keyword(
        "DonPachi (USA, ver. 1.12, 95/05/2x)",
        system="FBNeo - Arcade Games",
        limit=5,
    )

    assert results
    assert results[0]["english_name"] == "DonPachi (USA, ver. 1.12, 95/05/2x)"
    assert all("Strider" not in result["english_name"] for result in results)


def test_base_title_search_does_not_return_unrelated_long_title(tmp_path):
    db = DatabaseManager(str(tmp_path / "search.db"))
    cursor = db.get_connection().cursor()
    cursor.execute(
        "INSERT INTO translations (english_name, chinese_name, system) VALUES (?, ?, ?)",
        (
            "Strider (USA, B-Board 90629B-3, buggy Street Fighter II conversion)",
            "出击飞龙（美版, 街霸II转换版）",
            "Arcade - CPS1",
        ),
    )
    db.get_connection().commit()

    results = db.search_by_keyword("DonPachi", system="FBNeo - Arcade Games", limit=5)

    assert results == []
