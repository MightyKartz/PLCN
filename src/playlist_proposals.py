"""Immutable change proposals, match metadata and playlist snapshot validation."""
from dataclasses import asdict, dataclass
import hashlib
import json
import re
import unicodedata
from typing import Any, Dict, Optional
from match_evidence import CONFLICT_REASON, build_match_diagnostics
from playlist_artwork import (
    cover_preview_url,
)


@dataclass(frozen=True)
class MatchResult:
    match_status: str
    match_score: int
    needs_review: bool
    default_reason: str

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class ChangeProposal:
    proposal_id: str
    index: int
    original_label: str
    original_item_label: str
    original_db_name: str
    original_item_snapshot: Dict[str, Any]
    path: str
    crc32: Optional[str]
    new_label: str
    thumbnail_source: Optional[str]
    system: str
    match_score: int
    match_status: str
    match_source: str
    match_reason: str
    match_diagnostics: Dict[str, Any]
    needs_review: bool
    thumbnail_exists: bool
    local_thumbnail_exists: bool
    cover_exists: bool
    cover_path: Optional[str]
    cover_preview_url: Optional[str]

    def to_dict(self):
        return asdict(self)


def has_chinese(text):
    return any('\u4e00' <= char <= '\u9fff' for char in (text or ''))


def normalize_value(value):
    return unicodedata.normalize('NFC', value or '')


def build_proposal_id(system_name, index, path, original_item_label, original_db_name):
    raw = "\n".join([
        normalize_value(system_name),
        str(index),
        normalize_value(path),
        normalize_value(original_item_label),
        normalize_value(original_db_name),
    ])
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]


def classify_match(display_label, new_label, thumbnail_source, current_label=None, cover_exists=False):
    duplicate = bool(re.search(r'\(\d+\)$', (display_label or '').strip()) or re.search(r'\(\d+\)$', (new_label or '').strip()))
    missing_thumb = not thumbnail_source
    label_has_chinese = has_chinese(new_label)
    current_matches_new = bool(current_label and new_label and normalize_value(current_label) == normalize_value(new_label))

    if duplicate:
        return MatchResult("duplicate", 99, True, "检测到重复项标记，需要确认是否保留或重命名")
    if current_matches_new and thumbnail_source and cover_exists and label_has_chinese:
        return MatchResult("ready", 100, False, "中文名、封面源和本地封面已就绪，无需修复")
    if current_matches_new and thumbnail_source and label_has_chinese:
        return MatchResult("download", 94, False, "中文名和封面源已就绪，仅需下载封面")
    if missing_thumb or not label_has_chinese:
        return MatchResult("review", 72 if label_has_chinese else 64, True, "缺少中文名或封面标准名，需要人工确认")
    if cover_exists:
        return MatchResult("rename", 96, False, "封面已存在，仅需写入中文名")
    return MatchResult(
        "matched",
        96 if thumbnail_source != display_label or new_label != display_label else 90,
        False,
        "已匹配中文名和缩略图标准名",
    )


def build_change_proposal(index, item, display_label, new_label, thumbnail_source, system_name, match_source="heuristic", match_reason=None, match_diagnostics=None, cover_exists=False, cover_path=None):
    original_item_label = item.get('label') or ''
    original_db_name = item.get('db_name') or ''
    path = item.get('path') or ''
    match_info = classify_match(display_label, new_label, thumbnail_source, current_label=original_item_label, cover_exists=cover_exists)
    diagnostics = build_match_diagnostics(
        match_diagnostics,
        match_source=match_source,
        item=item,
        display_label=display_label,
        new_label=new_label,
        thumbnail_source=thumbnail_source,
    )
    if diagnostics["conflicts"]:
        match_info = MatchResult(
            "review",
            min(match_info.match_score, 72),
            True,
            match_info.default_reason,
        )
        if not match_reason or CONFLICT_REASON not in match_reason:
            match_reason = f"{CONFLICT_REASON}：{match_reason or match_info.default_reason}"

    return ChangeProposal(
        proposal_id=build_proposal_id(system_name, index, path, original_item_label, original_db_name),
        index=index,
        original_label=display_label,
        original_item_label=original_item_label,
        original_db_name=original_db_name,
        original_item_snapshot=dict(item),
        path=path,
        crc32=item.get('crc32'),
        new_label=new_label,
        thumbnail_source=thumbnail_source,
        system=system_name,
        match_score=match_info.match_score,
        match_status=match_info.match_status,
        match_source=match_source,
        match_reason=match_reason or match_info.default_reason,
        match_diagnostics=diagnostics,
        needs_review=match_info.needs_review,
        thumbnail_exists=cover_exists,
        local_thumbnail_exists=cover_exists,
        cover_exists=cover_exists,
        cover_path=cover_path,
        cover_preview_url=cover_preview_url(cover_path),
    ).to_dict()


def proposal_matches_item(change, item):
    snapshot = change.get('original_item_snapshot')
    if snapshot is not None and normalize_value(json.dumps(snapshot, sort_keys=True, ensure_ascii=False)) != normalize_value(json.dumps(item, sort_keys=True, ensure_ascii=False)):
        return False
    expected_label = change.get('original_item_label')
    expected_db_name = change.get('original_db_name')
    expected_path = change.get('path')

    if expected_path and normalize_value(item.get('path')) != normalize_value(expected_path):
        return False
    if expected_label is not None and normalize_value(item.get('label')) != normalize_value(expected_label):
        return False
    if expected_db_name and normalize_value(item.get('db_name')) != normalize_value(expected_db_name):
        return False
    if 'crc32' in change and normalize_value(item.get('crc32')) != normalize_value(change.get('crc32')):
        return False
    return True
