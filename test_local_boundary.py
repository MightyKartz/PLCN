from pathlib import Path


def test_translator_has_no_llm_or_online_matching_path():
    source = Path("src/translator.py").read_text(encoding="utf-8")

    assert "llm_client" not in source
    assert "translate_with_llm" not in source
    assert "Fallback to LLM" not in source


def test_docs_do_not_present_llm_as_matching_direction():
    doc = Path("DOC/DOC1.md").read_text(encoding="utf-8")

    assert "LLM API" not in doc
    assert "LLM 辅助匹配" not in doc
    assert "若接入" not in doc
