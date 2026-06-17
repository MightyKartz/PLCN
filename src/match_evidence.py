import os
import re


ACCEPTED_SOURCES = {
    "rom_filename",
    "zip_short_name",
    "playlist_crc32",
    "local_zip_crc",
    "libretro_dat",
    "exact_alias",
    "manual_override",
    "fuzzy_candidate",
    "fallback",
}

STRONG_SOURCES = {
    "rom_filename",
    "zip_short_name",
    "playlist_crc32",
    "local_zip_crc",
    "libretro_dat",
}

WEAK_SOURCES = {
    "fuzzy_candidate",
    "fallback",
}

CONFLICT_REASON = "强 ROM/DAT/CRC 证据与弱中文/模糊证据冲突，需要人工确认"

_SOURCE_ALIASES = {
    "rom_filename": "rom_filename",
    "zip_short_name": "zip_short_name",
    "playlist_crc32": "playlist_crc32",
    "local_zip_crc": "local_zip_crc",
    "libretro_dat": "libretro_dat",
    "manual_override": "manual_override",
    "rom-stem": "rom_filename",
    "rom-file": "rom_filename",
    "rom": "rom_filename",
    "filename": "rom_filename",
    "display": "rom_filename",
    "playlist-crc": "playlist_crc32",
    "zip-crc": "local_zip_crc",
    "file-crc": "local_zip_crc",
    "libretro-dat": "libretro_dat",
    "libretro-dat-rom": "libretro_dat",
    "dat": "libretro_dat",
    "exact-alias": "exact_alias",
    "exact_alias": "exact_alias",
    "alias": "exact_alias",
    "rom-name-cn": "exact_alias",
    "manual": "manual_override",
    "manual-override": "manual_override",
    "playlist": "fuzzy_candidate",
    "fuzzy": "fuzzy_candidate",
    "fuzzy-candidate": "fuzzy_candidate",
    "fuzzy_candidate": "fuzzy_candidate",
    "arcade-fallback": "fallback",
    "fallback": "fallback",
    "heuristic": "fallback",
}

_SOURCE_LABELS = {
    "rom_filename": "rom-filename",
    "zip_short_name": "zip-short-name",
    "playlist_crc32": "playlist-crc32",
    "local_zip_crc": "local-zip-crc",
    "libretro_dat": "Libretro DAT",
    "exact_alias": "exact-alias",
    "manual_override": "manual-override",
    "fuzzy_candidate": "fuzzy-candidate",
    "fallback": "fallback",
}


def normalize_source(source, value=None, all_candidates=None):
    mapped = _SOURCE_ALIASES.get(str(source or "").strip(), "fallback")
    if mapped == "rom_filename" and source == "rom-stem" and _looks_like_zip_short_name(value, all_candidates):
        return "zip_short_name"
    return mapped if mapped in ACCEPTED_SOURCES else "fallback"


def build_match_diagnostics(
    match_diagnostics=None,
    *,
    match_source=None,
    item=None,
    display_label=None,
    new_label=None,
    thumbnail_source=None,
):
    diagnostics = dict(match_diagnostics or {})
    chain = []

    for evidence in diagnostics.get("evidence_chain") or []:
        normalized = normalize_evidence(evidence)
        if normalized:
            chain.append(normalized)

    raw_candidates = diagnostics.get("candidates") or []
    for candidate in raw_candidates:
        if isinstance(candidate, dict):
            value = candidate.get("value")
            source = candidate.get("source")
        else:
            try:
                value, source = candidate
            except (TypeError, ValueError):
                continue
        chain.append(make_evidence(source, value=value, all_candidates=raw_candidates))

    matched_candidate = diagnostics.get("matched_candidate")
    matched_source = diagnostics.get("matched_candidate_source")
    if matched_candidate or matched_source:
        chain.append(make_evidence(
            matched_source or match_source,
            value=matched_candidate,
            resolved_name=thumbnail_source,
            all_candidates=raw_candidates,
        ))

    if not chain and item:
        path = item.get("path") or ""
        basename = os.path.basename(path.split("#", 1)[0]) if path else ""
        if basename:
            chain.append(make_evidence("rom-file", value=basename, resolved_name=thumbnail_source))

    chain.append(make_evidence(
        match_source,
        value=display_label,
        resolved_name=thumbnail_source or new_label,
    ))

    diagnostics["evidence_chain"] = dedupe_evidence(chain)
    diagnostics["conflicts"] = find_conflicts(diagnostics["evidence_chain"])
    return diagnostics


def make_evidence(source, *, value=None, resolved_name=None, all_candidates=None):
    normalized_source = normalize_source(source, value=value, all_candidates=all_candidates)
    evidence = {
        "source": normalized_source,
        "source_label": _SOURCE_LABELS[normalized_source],
    }
    if source and str(source) != normalized_source:
        evidence["raw_source"] = str(source)
    if value:
        evidence["value"] = str(value)
    if resolved_name:
        evidence["resolved_name"] = str(resolved_name)
    return evidence


def normalize_evidence(evidence):
    if not isinstance(evidence, dict):
        return None
    normalized = make_evidence(
        evidence.get("source"),
        value=evidence.get("value"),
        resolved_name=evidence.get("resolved_name"),
    )
    for key in ("note", "score", "raw_source", "source_label"):
        if key in evidence:
            normalized[key] = evidence[key]
    return normalized


def find_conflicts(evidence_chain):
    conflicts = []
    strong = [entry for entry in evidence_chain if entry.get("source") in STRONG_SOURCES and _identity(entry)]
    weak = [entry for entry in evidence_chain if entry.get("source") in WEAK_SOURCES and _identity(entry)]

    for strong_entry in strong:
        for weak_entry in weak:
            if _normalized_identity(strong_entry) != _normalized_identity(weak_entry):
                conflicts.append({
                    "type": "strong_weak_evidence",
                    "reason": CONFLICT_REASON,
                    "strong_source": strong_entry.get("source"),
                    "strong_value": strong_entry.get("value"),
                    "strong_resolved_name": strong_entry.get("resolved_name"),
                    "weak_source": weak_entry.get("source"),
                    "weak_value": weak_entry.get("value"),
                    "weak_resolved_name": weak_entry.get("resolved_name"),
                })
    return conflicts


def _looks_like_zip_short_name(value, all_candidates):
    if not value:
        return False
    short_name = str(value).casefold()
    for candidate in all_candidates or []:
        candidate_value = candidate.get("value") if isinstance(candidate, dict) else candidate[0] if isinstance(candidate, (tuple, list)) and candidate else None
        candidate_source = candidate.get("source") if isinstance(candidate, dict) else candidate[1] if isinstance(candidate, (tuple, list)) and len(candidate) > 1 else None
        if candidate_source == "rom-file" and str(candidate_value or "").casefold() == f"{short_name}.zip":
            return True
    return False


def _identity(evidence):
    return evidence.get("resolved_name") or evidence.get("value")


def _normalized_identity(evidence):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", _identity(evidence).casefold())


def dedupe_evidence(chain):
    seen = set()
    result = []
    for entry in chain:
        if not entry:
            continue
        key = (
            entry.get("source"),
            entry.get("value"),
            entry.get("resolved_name"),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(entry)
    return result
