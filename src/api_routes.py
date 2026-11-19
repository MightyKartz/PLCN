"""Explicit HTTP routes.

Handlers take (request, live service context, parsed query or JSON object).
Authentication and JSON transport validation stay in server.ConfigHandler.
"""
import api_m3u
import api_chd
import api_rom_storage
import api_content
import api_library
import api_playlists
import api_artwork
import api_tasks
import api_data
import api_desktop
import api_config
import api_games

GET_ROUTES = {
    '/api/game-files/storages': api_library.game_file_storages,
    '/api/game-files/directory': api_library.game_file_directory,
    '/api/jobs/status': api_tasks.workbench_status,
    '/api/library/playlist-summary': api_library.playlist_summary,
    '/api/library/overview': api_library.overview,
    '/api/m3u/history': api_m3u.history,
    '/api/cores/info': api_content.core_info,
    '/api/content/setup': api_content.setup,
    '/api/content/directories': api_content.directories,
    '/api/artwork/thumbnail': api_artwork.thumbnail,
    '/api/config': api_config.get_config,
    '/api/data': api_data.data,
    '/api/desktop': api_desktop.desktop,
    '/api/device/scan': api_library.scan_device,
    '/api/fs/list': api_library.list_files,
    '/api/instance': api_desktop.instance,
    '/api/library/sources': api_library.sources,
    '/api/overrides/list': api_config.list_overrides,
    '/api/completion/receipts': api_playlists.completion_receipts_list,
    '/api/playlist/detect': api_playlists.detect_system,
    '/api/playlist/items': api_playlists.items,
    '/api/playlist/discs': api_playlists.discs,
    '/api/progress': api_tasks.stream_progress,
    '/api/stats': api_data.get_stats,
    '/api/systems': api_data.list_systems,
    '/api/thumbnail/preview': api_artwork.serve_thumbnail_preview,
}

POST_ROUTES = {
    '/api/game-files/change': api_library.change_game_file,
    '/api/game-files/delete-preview': api_library.preview_game_file_deletion,
    '/api/game-files/delete-apply': api_library.apply_game_file_deletion,
    '/api/games/mapping': api_games.save_mapping,
    '/api/games/preview': api_games.preview,
    '/api/games/details': api_games.details,
    '/api/games/apply': api_games.apply,
    '/api/content/auto-preview': api_content.auto_preview,
    '/api/content/auto-apply': api_content.auto_apply,
    '/api/rom-storage/relocation/preview': api_rom_storage.relocation_preview,
    '/api/rom-storage/relocation/apply': api_rom_storage.relocation_apply,
    '/api/rom-storage/relocation/recover': api_rom_storage.relocation_recover,
    '/api/rom-storage/analyze': api_rom_storage.analyze,
    '/api/rom-storage/convert': api_rom_storage.convert,
    '/api/chd/deployment/preview': api_chd.deployment_preview,
    '/api/chd/deployment/apply': api_chd.deployment_apply,
    '/api/chd/deployment/recover': api_chd.deployment_recover,
    '/api/chd/analyze': api_chd.analyze,
    '/api/chd/convert': api_chd.convert,
    '/api/m3u/preview': api_m3u.preview,
    '/api/m3u/apply': api_m3u.apply,
    '/api/m3u/recover': api_m3u.recover,
    '/api/content/core-status': api_content.core_status,
    '/api/content/hints': api_content.hints,
    '/api/content/infer': api_content.infer,
    '/api/content/preview': api_content.preview,
    '/api/content/apply': api_content.apply,
    '/api/cores/download': api_content.core_download,
    '/api/cores/transfer': api_content.core_transfer,
    '/api/artwork/apply': api_artwork.apply,
    '/api/artwork/context': api_artwork.context,
    '/api/artwork/preview': api_artwork.preview,
    '/api/artwork/resolve': api_artwork.resolve,
    '/api/artwork/search': api_artwork.search,
    '/api/artwork/status': api_artwork.status,
    '/api/batch/discard': api_playlists.batch_discard,
    '/api/batch/preview': api_playlists.batch_preview,
    '/api/batch/apply': api_playlists.batch_apply,
    '/api/completion/undo': api_playlists.completion_undo,
    '/api/config': api_config.save_config,
    '/api/data/activate': api_data.activate,
    '/api/data/check': api_data.check,
    '/api/data/compare': api_data.compare,
    '/api/data/fetch': api_data.fetch,
    '/api/data/rollback': api_data.rollback,
    '/api/desktop/activate': api_desktop.activate,
    '/api/desktop/pick': api_desktop.pick,
    '/api/desktop/shutdown': api_desktop.shutdown,
    '/api/fs/open': api_library.open_folder,
    '/api/history/restore': api_tasks.restore,
    '/api/jobs/cancel': api_tasks.cancel,
    '/api/jobs/retry': api_tasks.retry,
    '/api/library/recent': api_library.recent,
    '/api/overrides/save': api_config.save_overrides_handler,
    '/api/playlist/apply': api_playlists.apply,
    '/api/playlist/preview': api_playlists.preview,
}
