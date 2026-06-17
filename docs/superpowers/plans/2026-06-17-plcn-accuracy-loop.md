# PLCN Accuracy Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make PLCN's local matching loop more accurate by adding regression fixtures, explicit local evidence chains, and local manual overrides without adding any external scraping or online matching service.

**Architecture:** Keep `analyze_playlist()` response fields compatible while enriching `match_diagnostics` with a local evidence chain. Add a small `manual_overrides` module that reads and writes local JSON and is consulted before fuzzy matching. Treat weak evidence conflicts as review-only, not auto-repair.

**Tech Stack:** Python, pytest, RetroArch `.lpl` JSON, local `rom-name-cn`, Libretro DAT, local JSON overrides, GitHub draft PR.

---

## Guardrails

- Do not add ScreenScraper, Skraper, online game databases, cloud sync, or LLM online matching.
- Do not commit `plcn.db`, `output/`, `.DS_Store`, `.pytest_cache`, or unrelated old plan files.
- Preserve existing preview fields: `new_label`, `thumbnail_source`, `match_source`, `match_reason`, `match_score`, `needs_review`, `match_diagnostics`.
- Strong evidence wins over Chinese parent folders, polluted labels, and fuzzy candidates.
- Evidence conflict means `match_status == "review"` and `needs_review is True`.

## Task 1: Accuracy Fixtures And Red Tests

**Files:**
- Create: `tests/fixtures/playlists/*.lpl`
- Modify: `test_change_proposals.py`

- [x] **Step 1: Write fixture tests**

Add pytest cases that call `plcn.analyze_playlist()` for Snatcher, GBA parent-folder pollution, FBNeo zip short name, PS1 bin/cue, Unicode NFC/NFD, same-title cross-system, hack/collection, and missing thumbnail source.

Required assertion pattern:

```python
assert change["new_label"] == expected_cn
assert change["thumbnail_source"] == expected_source
assert change["match_source"]
assert isinstance(change["match_score"], int)
assert isinstance(change["needs_review"], bool)
assert change["match_diagnostics"]["evidence_chain"]
```

- [x] **Step 2: Add the Snatcher negative case**

Add a fixture where `path` ends in `Snatcher.bin`, the existing label is Chinese, and the incorrect source `Tiger & Bunny - On-Air Jack! (Japan)` would be a plausible bad result. Expected behavior:

```python
assert change["thumbnail_source"] != "Tiger & Bunny - On-Air Jack! (Japan)"
assert change["match_status"] == "review"
assert change["needs_review"] is True
```

- [x] **Step 3: Verify red**

Run:

```bash
python3 -m pytest -q test_change_proposals.py
```

Expected before implementation: failures for missing fixtures/evidence chain/manual override behavior.

## Task 2: Local Evidence Chain

**Files:**
- Create: `src/match_evidence.py`
- Modify: `src/plcn.py`
- Test: `test_change_proposals.py`

- [x] **Step 1: Add evidence model**

Create `MatchEvidence` and helpers:

```python
@dataclass(frozen=True)
class MatchEvidence:
    source: str
    value: str
    strength: int
    note: str = ""

def evidence_to_dict(evidence):
    return asdict(evidence)
```

Accepted `source` values include `rom_filename`, `zip_short_name`, `playlist_crc32`, `local_zip_crc`, `libretro_dat`, `exact_alias`, `manual_override`, `fuzzy_candidate`, and `fallback`.

- [x] **Step 2: Wire evidence into proposals**

Every proposal's `match_diagnostics` must include:

```python
{
    "evidence_chain": [
        {"source": "rom_filename", "value": "...", "strength": 90, "note": "..."}
    ],
    "conflicts": []
}
```

- [x] **Step 3: Conflict rule**

If strong ROM/DAT/CRC evidence conflicts with weak Chinese label or fuzzy source, return a review proposal:

```python
match_status = "review"
needs_review = True
match_reason = "本地强证据与弱证据冲突，需要确认"
```

- [x] **Step 4: Verify green**

Run:

```bash
python3 -m pytest -q test_change_proposals.py test_fbneo_preview_matching.py test_rom_fingerprint.py
```

## Task 3: Manual Overrides

**Files:**
- Create: `src/manual_overrides.py`
- Modify: `src/plcn.py`
- Test: `test_manual_overrides.py`

- [x] **Step 1: Write failing tests**

Test local JSON read/write and priority over fuzzy matching:

```python
override = {
    "system": "Sony - PlayStation",
    "rom_filename": "Snatcher.bin",
    "crc32": "00000000|crc",
    "new_label": "掠夺者",
    "thumbnail_source": "Snatcher (Japan)",
}
```

Expected proposal:

```python
assert change["new_label"] == "掠夺者"
assert change["thumbnail_source"] == "Snatcher (Japan)"
assert change["match_source"] == "manual_override"
assert change["needs_review"] is False
```

- [x] **Step 2: Implement minimal local JSON store**

Use project-local or explicit path only; no network. Provide `load_overrides(path)`, `save_overrides(path, entries)`, and `find_override(entries, system, item)`.

- [x] **Step 3: Wire into analyze**

Add optional `manual_overrides_path=None` to `analyze_playlist()`. If an override matches system + ROM filename or CRC, use it before fuzzy translation.

- [x] **Step 4: Verify green**

Run:

```bash
python3 -m pytest -q test_manual_overrides.py test_change_proposals.py
```

## Task 4: Documentation And Local Boundary

**Files:**
- Modify: `DOC/OPTIMIZATION_PLAN.md`
- Optional Modify: `README.md`, `README_EN.md`

- [x] **Step 1: Document accuracy-first local loop**

Ensure docs say PLCN is local-first and accuracy comes from local `.lpl`, ROM evidence, Libretro DAT, `rom-name-cn`, alias, and manual overrides.

- [x] **Step 2: Remove misleading external phrasing**

Search docs for external matching language:

```bash
rg -n "ScreenScraper|Skraper|LLM|cloud|云同步|在线匹配|外部刮削" README.md README_EN.md DOC
```

Only allowed mentions are explicit "not supported / not used" boundary statements.

## Task 5: Integration And Draft PR

**Files:**
- All changed files

- [x] **Step 1: Full verification**

Run:

```bash
python3 -m pytest -q
python3 -m py_compile src/*.py
git diff --check
```

- [x] **Step 2: Scope audit**

Run:

```bash
git status --short
git diff --name-only main...HEAD
```

Stage only plan, code, tests, fixtures, and docs for this accuracy loop.

- [x] **Step 3: Publish**

Commit on `codex/plcn-accuracy-loop`, push, and create a GitHub draft PR to `main`. Do not merge, tag, or release.
