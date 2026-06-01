# PLCN Match Metadata And Apply Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make preview match state backend-owned and prevent stale preview proposals from writing over user-edited playlist items.

**Architecture:** `src/plcn.py` emits enriched change proposals with stable ids, original item snapshots, and match metadata. `apply_changes()` validates path, original label, and `db_name` before writing. `src/templates/plcn.html` consumes backend status first and falls back to the old heuristic only for legacy data.

**Tech Stack:** Python 3, pytest, vanilla HTML/CSS/JavaScript local Web UI.

---

### Task 1: Lock Proposal Metadata With Tests

**Files:**
- Create: `test_change_proposals.py`
- Modify: `src/plcn.py`

- [x] **Step 1: Add a failing test for backend proposal metadata**

Run: `python3 -m pytest test_change_proposals.py -q`

Expected before implementation: `AttributeError: module 'plcn' has no attribute 'build_change_proposal'`.

- [x] **Step 2: Implement `build_change_proposal()`**

Add `proposal_id`, `original_item_label`, `original_db_name`, `match_score`, `match_status`, `match_source`, `match_reason`, and `needs_review` to every preview change proposal.

- [x] **Step 3: Verify metadata test passes**

Run: `python3 -m pytest test_change_proposals.py -q`

Expected after implementation: metadata test passes.

### Task 2: Prevent Stale Preview Writes

**Files:**
- Modify: `test_change_proposals.py`
- Modify: `src/plcn.py`

- [x] **Step 1: Add a failing test for stale proposal snapshots**

The test creates a playlist whose label changed after preview, then applies a stale proposal. Before implementation, the label is overwritten.

- [x] **Step 2: Implement `proposal_matches_item()`**

Compare proposal `path`, `original_item_label`, and `original_db_name` against the current playlist item before writing.

- [x] **Step 3: Apply only validated changes**

Skip stale proposals and exclude them from thumbnail download tasks.

- [x] **Step 4: Verify stale write test passes**

Run: `python3 -m pytest test_change_proposals.py -q`

Expected after implementation: stale proposal does not modify the playlist.

### Task 3: Use Backend Status In The UI

**Files:**
- Modify: `src/templates/plcn.html`

- [x] **Step 1: Update `getMatchInfo()`**

Prefer backend `match_status` and `match_score`; use the old heuristic only when legacy preview data lacks metadata.

- [x] **Step 2: Show backend reason in the inspector**

Append `match_reason` to the confidence line so users can understand why the status was assigned.

- [x] **Step 3: Mark manual edits explicitly**

When users edit a proposed label or thumbnail source, set `match_source` to `manual` and recalculate matched/review state from the edited values.

### Task 4: Verify

**Files:**
- Modify: `DOC/OPTIMIZATION_PLAN.md`

- [x] **Step 1: Run Python and pytest validation**

Run:

```bash
python3 -m py_compile src/*.py
git diff --check
python3 -m pytest -q
```

Expected: all pass.

- [x] **Step 2: Browser QA**

Restart `python3 src/server.py`, open `http://localhost:7777/`, generate a preview, confirm table status uses backend metadata, and confirm the console has no errors.
