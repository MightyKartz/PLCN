# PLCN Writeback Override UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make PLCN safer after applying playlist changes, persist local user corrections, and make the UI display backend-authoritative state instead of inferred accuracy.

**Architecture:** Keep the existing local Python CLI/Web UI shape. Add structured writeback verification around `apply_changes()`, add a small local `manual_overrides` module plus server endpoints, and narrow frontend status inference to backend/manual-edit states only. No external matching, scraping, cloud, or LLM service is introduced.

**Tech Stack:** Python, pytest, local JSON, RetroArch `.lpl`, vanilla JS in `src/templates/plcn.html`, GitHub draft PR.

---

## Guardrails

- Work from `/Users/kartz/Development/Playlistcn` on `codex/plcn-writeback-override-ui`.
- Do not commit `plcn.db`, `output/`, `.DS_Store`, `.pytest_cache`, or unrelated old plan files.
- Preserve local-only boundaries: no ScreenScraper, Skraper, online DB, cloud sync, LLM matching, or external scraping.
- Keep UI states aligned with PLCN terms: `matched`, `download`, `rename`, `ready`, `review`, `duplicate`, `applied`.
- Use TDD: every production behavior change gets a failing test first, then minimal implementation.

## Task 1: Writeback Safety And Read-Back Verification

**Files:**
- Modify: `src/plcn.py`
- Modify: `test_change_proposals.py`

- [x] **Step 1: Add failing tests for writeback results**

Add tests proving:

```python
def test_apply_changes_returns_writeback_summary_and_timestamped_backup(tmp_path):
    # create one .lpl item, apply one valid proposal with backup=True/download=False
    # assert a .bak-YYYYmmdd-HHMMSS file exists
    # assert summary["writeback"]["applied"] contains the proposal id/path/new_label
    # assert summary["writeback"]["failed"] == []
```

```python
def test_apply_changes_reports_readback_failure_without_silent_success(tmp_path, monkeypatch):
    # monkeypatch PlaylistManager.save to not persist the changed label
    # assert writeback failed entry has reason "readback_mismatch"
    # assert no download task is counted as success
```

```python
def test_apply_changes_preserves_ps1_cue_bin_siblings_during_apply(tmp_path):
    # create .cue and .bin siblings with same label
    # apply both proposals
    # assert both rows remain and both labels are updated
```

- [x] **Step 2: Run red tests**

Run:

```bash
python3 -m pytest -q test_change_proposals.py
```

Expected: new writeback summary / readback / cue-bin tests fail.

- [x] **Step 3: Implement structured writeback**

In `src/plcn.py`:

- Add `timestamped_backup_path(playlist_path)`.
- Add `has_disc_descriptor_siblings(items)` and use it in both analyze/apply to avoid collapsing `.cue/.bin` siblings.
- Track `applied_changes`, `skipped_changes`, and `failed_changes` during `apply_changes()`.
- Save, then reload `PlaylistManager(playlist_path)` and verify every applied path has `new_label`.
- Return a merged summary:

```python
summary["writeback"] = {
    "backup_path": backup_path,
    "applied": applied_changes,
    "skipped": skipped_changes,
    "failed": failed_changes,
}
```

- Only schedule thumbnail downloads for changes that pass read-back verification.

- [x] **Step 4: Verify green**

Run:

```bash
python3 -m pytest -q test_change_proposals.py
```

## Task 2: Local Manual Override Persistence

**Files:**
- Create: `src/manual_overrides.py`
- Modify: `src/plcn.py`
- Modify: `src/server.py`
- Create: `test_manual_overrides.py`

- [x] **Step 1: Add failing tests**

Test `load_overrides`, `save_overrides`, `upsert_override`, `find_override`, and `analyze_playlist(..., manual_overrides_path=...)`.

Required behavior:

```python
entry = {
    "system": "Sony - PlayStation",
    "rom_filename": "Snatcher.bin",
    "rom_path": "/roms/ps/Snatcher.bin",
    "crc32": "00000000|crc",
    "new_label": "掠夺者",
    "thumbnail_source": "Snatcher (Japan)",
}
saved = upsert_override([], entry, now="2026-06-17T00:00:00Z")
assert saved[0]["updated_at"] == "2026-06-17T00:00:00Z"
```

Manual override must match by `system + crc32` first, then `system + rom_filename`, and must be used before fuzzy/name search.

- [x] **Step 2: Run red tests**

Run:

```bash
python3 -m pytest -q test_manual_overrides.py
```

Expected: import/function failures.

- [x] **Step 3: Implement local JSON overrides**

Create `src/manual_overrides.py` with:

- `load_overrides(path) -> list`
- `save_overrides(path, entries) -> None`
- `find_override(entries, system, item) -> dict | None`
- `upsert_override(entries, entry, now=None) -> list`
- `default_overrides_path(config_dir=None) -> str`

Wire `manual_overrides_path=None` into `plcn.analyze_playlist()`. When found, build a proposal with `match_source == "manual_override"`, `match_score == 100`, `needs_review is False`, and local diagnostics.

- [x] **Step 4: Add server endpoint tests or direct handler coverage**

If there is no existing server test harness, add focused pure tests for the helper that builds/saves an override payload. Add `/api/overrides/save` and `/api/overrides/list` in `src/server.py` using only local JSON.

- [x] **Step 5: Verify green**

Run:

```bash
python3 -m pytest -q test_manual_overrides.py test_change_proposals.py
```

## Task 3: Backend-Authoritative UI State And Override Save Entry

**Files:**
- Modify: `src/templates/plcn.html`
- Modify: `test_ui_information_architecture.py`

- [x] **Step 1: Add failing UI text/static tests**

Assert:

```python
assert "frontend-fallback" not in html
assert "source: 'manual-edit'" in html
assert "保存为本地修正规则" in html
assert "/api/overrides/save" in html
assert "待保存本地修正" in html
```

- [x] **Step 2: Run red UI tests**

Run:

```bash
python3 -m pytest -q test_ui_information_architecture.py
```

- [x] **Step 3: Update JS state model**

In `getMatchInfo(change)`, if backend fields are missing, return review/unknown with `source: 'backend-missing'` instead of computing confidence. In `reclassifyEditedChange`, mark edits as `match_source = 'manual-edit'`, `match_status = 'review'`, `needs_review = true`, and add `pending_override = true`.

Add a button in the inspector/details area labeled `保存为本地修正规则`. It posts system, path, crc32, new label, and thumbnail source to `/api/overrides/save`; after success set `match_source = 'manual_override'`, `match_score = 100`, `needs_review = false`, and rerender.

- [x] **Step 4: Syntax and focused tests**

Run:

```bash
python3 -m pytest -q test_ui_information_architecture.py
```

If script extraction tooling exists, run it. Otherwise add a small Node syntax check for extracted inline script before final verification.

## Task 4: Docs And Local Boundary

**Files:**
- Modify: `DOC/OPTIMIZATION_PLAN.md`
- Modify if needed: `README.md`, `README_EN.md`

- [x] **Step 1: Update docs**

Document:

- timestamped backups and read-back verification
- local override path and fields
- UI now displays backend status; manual edits are pending local corrections
- no external matching or scraping

- [x] **Step 2: Boundary scan**

Run:

```bash
rg -n "ScreenScraper|Skraper|LLM|cloud|云同步|在线匹配|外部刮削" README.md README_EN.md DOC src
```

Allowed hits must be explicit local-only boundary statements or historical notes.

## Task 5: Integration, Verification, And Draft PR

**Files:**
- All changed files

- [x] **Step 1: Full verification**

Run:

```bash
python3 -m pytest -q
python3 -m py_compile src/*.py
git diff --check
```

If UI changed, also run inline JS syntax/browser verification.

- [x] **Step 2: Scope audit**

Run:

```bash
git status --short
git diff --name-only
```

Stage only files for this goal.

- [x] **Step 3: Publish draft PR**

Commit, push `codex/plcn-writeback-override-ui`, and create a draft PR to `main`. Prefer GitHub connector; fall back to `gh pr create --draft` if connector returns permission errors.
