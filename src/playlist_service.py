"""Public playlist API shared by CLI and HTTP callers.

Implementation lives in analysis, proposals, artwork, writeback and batch modules.
Import their dependencies there; do not store a second copy of service state here.
"""
from playlist_proposals import (
    MatchResult,
    ChangeProposal,
    has_chinese,
    normalize_value,
    build_proposal_id,
    classify_match,
    build_change_proposal,
    proposal_matches_item,
)
from playlist_artwork import (
    sanitize_thumbnail_filename,
    local_thumbnail_path,
    boxart_dir_path,
    adb_thumbnail_exists,
    build_existing_boxart_lookup,
    find_existing_boxart,
    cover_preview_url,
)
from playlist_analysis import (
    is_generic_collection_label,
    add_unique_candidate,
    get_rom_path_candidates,
    disc_sibling_key,
    has_disc_descriptor_siblings,
    analyze_playlist,
)
from playlist_writeback import (
    find_playlist_item_by_path,
    skipped_apply_detail,
    wrap_apply_result,
    writeback_record,
    apply_summary_applied_record,
    apply_summary_skipped_record,
    attach_writeback_summary,
    applied_record_verified,
    apply_changes,
)
from playlist_batch import (
    detect_system,
    process_playlist,
    process_directory,
)

__all__ = [
    'MatchResult',
    'ChangeProposal',
    'detect_system',
    'has_chinese',
    'is_generic_collection_label',
    'normalize_value',
    'add_unique_candidate',
    'get_rom_path_candidates',
    'build_proposal_id',
    'disc_sibling_key',
    'has_disc_descriptor_siblings',
    'sanitize_thumbnail_filename',
    'local_thumbnail_path',
    'boxart_dir_path',
    'adb_thumbnail_exists',
    'build_existing_boxart_lookup',
    'find_existing_boxart',
    'cover_preview_url',
    'classify_match',
    'build_change_proposal',
    'proposal_matches_item',
    'find_playlist_item_by_path',
    'skipped_apply_detail',
    'wrap_apply_result',
    'analyze_playlist',
    'writeback_record',
    'apply_summary_applied_record',
    'apply_summary_skipped_record',
    'attach_writeback_summary',
    'applied_record_verified',
    'apply_changes',
    'process_playlist',
    'process_directory',
]
