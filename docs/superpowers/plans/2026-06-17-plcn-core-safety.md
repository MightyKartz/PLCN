# PLCN Core Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve PLCN matching correctness, playlist write-back safety, and test reliability without changing the release version or publishing a new release.

**Architecture:** Keep the current API response shape compatible while introducing typed internal boundaries around match/proposal results. Strengthen write-back with explicit verification and structured skip details. Convert fragile print-driven tests into pytest assertions and document the current tag-triggered release flow.

**Tech Stack:** Python, pytest, RetroArch `.lpl` JSON, local `rom-name-cn`, Libretro DAT, GitHub Actions, GitHub draft PR.

---

## Scope Guardrails

- Do not edit or stage `plcn.db`, `output/`, `.DS_Store`, `.pytest_cache`, or unrelated older `docs/superpowers/plans/*.md` files.
- Do not tag, release, or merge.
- Preserve existing `/api/playlist/preview` change fields: `new_label`, `thumbnail_source`, `match_source`, `match_reason`, `match_score`, `needs_review`.
- Keep PLCN local-first; do not add ScreenScraper, Skraper, or remote scraping APIs.

## Task 1: Matching Result Boundary

**Files:**
- Modify: `src/plcn.py`
- Test: `test_change_proposals.py`

- [ ] **Step 1: Write failing tests**

Add tests asserting every generated proposal includes the required explanation fields and that weak Chinese directory/fuzzy hints cannot override ROM filename/DAT evidence.

- [ ] **Step 2: Verify red**

Run focused pytest against the new tests and confirm they fail before implementation.

- [ ] **Step 3: Implement minimal typed boundary**

Introduce a small internal result/proposal helper boundary, preferably dataclasses, while preserving dict output compatibility for the UI.

- [ ] **Step 4: Verify green**

Run `python3 -m pytest -q test_change_proposals.py test_search_precision.py test_fbneo_preview_matching.py test_rom_fingerprint.py`.

## Task 2: Write-Back Safety

**Files:**
- Modify: `src/plcn.py`
- Test: `test_change_proposals.py` or new focused pytest file

- [ ] **Step 1: Write failing tests**

Cover timestamped backups, stale proposal skips, and read-back verification after apply.

- [ ] **Step 2: Verify red**

Run the new focused tests and confirm they fail.

- [ ] **Step 3: Implement structured apply results**

Keep existing download summary compatibility, but include structured skipped/apply verification details. Stale proposals must not write or enqueue downloads.

- [ ] **Step 4: Verify green**

Run the focused apply/write-back tests.

## Task 3: Test Reliability And Fixtures

**Files:**
- Modify: `test_batch.py`
- Modify: `test_optimizations.py`
- Create: `tests/fixtures/playlists/` as needed

- [ ] **Step 1: Convert print-driven tests**

Replace `[PASS]` / `[FAIL]` prints in priority test files with pytest assertions.

- [ ] **Step 2: Add fixtures**

Add small `.lpl` fixtures for GBA Chinese parent folder, polluted label, FBNeo zip short name, PS1 bin/cue, Unicode NFC/NFD, duplicate entries, and missing thumbnail source.

- [ ] **Step 3: Verify**

Run `python3 -m pytest -q test_batch.py test_optimizations.py`.

## Task 4: Documentation And Release Flow

**Files:**
- Modify: `RELEASE_GUIDE.md`
- Modify: `README.md`
- Modify: `README_EN.md`

- [ ] **Step 1: Update release guide**

Remove stale v3.0.0 instructions. Document the current tag-triggered GitHub Actions release workflow, validation commands, and release-note expectations.

- [ ] **Step 2: Update development verification docs**

Ensure README validation commands mention pytest, py_compile, diff check, and UI JS syntax check when touching the template.

- [ ] **Step 3: Verify docs**

Search for stale `v3.0.0` release flow text and ensure docs remain Chinese-first with English README linked.

## Task 5: Integration, Review, PR

**Files:**
- All changed files

- [ ] **Step 1: Final verification**

Run:

```bash
python3 -m pytest -q
python3 -m py_compile src/*.py
git diff --check
```

If UI template changes, also run JS syntax check over `src/templates/plcn.html` and browser verification.

- [ ] **Step 2: Scope audit**

Run `git status --short` and stage only this plan, code, tests, fixtures, and docs for this work.

- [ ] **Step 3: Commit and push**

Commit on `codex/plcn-core-safety`, push to origin, and create a GitHub draft PR to `main`.

- [ ] **Step 4: PR body**

PR body must include background, changes, user impact, tests, and unfinished items. Do not merge, tag, or release.
