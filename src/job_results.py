"""Serialize playlist writeback and image results for task clients."""
from pathlib import Path
import os
import urllib.parse

def thumbnail_preview_url(path):
    if not path:
        return None
    return "/api/thumbnail/preview?path=" + urllib.parse.quote(str(path), safe="")


def annotate_download_summary_paths(summary, local_root=None, final_root=None):
    if not summary:
        return summary

    try:
        from retroarch_scanner import is_adb_uri, parse_adb_uri
    except Exception:
        is_adb_uri = lambda value: False
        parse_adb_uri = None

    import mtp_runtime as mtp
    if mtp.is_mtp(final_root) and local_root:
        for detail in summary.get('details', []):
            if detail.get('path'):
                detail['path'] = mtp.join(final_root, *Path(detail['path']).relative_to(local_root).parts)
    adb_target = bool(final_root and is_adb_uri(final_root) and parse_adb_uri)
    local_base = os.path.abspath(local_root) if local_root else None

    for detail in summary.get("details", []):
        path = detail.get("path")
        if path and adb_target and local_base:
            try:
                path_abs = os.path.abspath(path)
                if path_abs == local_base or path_abs.startswith(local_base + os.sep):
                    serial, remote_root = parse_adb_uri(final_root)
                    rel_path = os.path.relpath(path_abs, local_base).replace(os.sep, "/")
                    remote_path = "/".join(part.strip("/") for part in [remote_root, rel_path] if part)
                    path = f"adb://{serial}/{remote_path}" if remote_path else f"adb://{serial}"
                    detail["path"] = path
            except Exception:
                pass

        if detail.get("type") == "Named_Boxarts" and detail.get("status") in {"success", "skipped"} and path:
            detail["cover_path"] = path
            detail["cover_preview_url"] = thumbnail_preview_url(path)

    return summary


def split_plcn_apply_result(result):
    if isinstance(result, dict) and "download_summary" in result and "apply" in result:
        return result.get("download_summary") or {}, result.get("apply")
    return result or {}, None


def build_apply_job_result(summary, apply_summary=None, changes=None, transport="local"):
    writeback = summary.get("writeback") if isinstance(summary, dict) else None
    if isinstance(writeback, dict):
        applied_count = len(writeback.get("applied") or [])
    elif isinstance(apply_summary, dict):
        applied_count = len(apply_summary.get("applied") or [])
    else:
        applied_count = len(changes or [])

    return {
        "applied_count": applied_count,
        "download_summary": summary,
        "apply": apply_summary,
        "transport": transport,
    }
