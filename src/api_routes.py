"""Explicit HTTP routes.

Handlers take (request, live service context, parsed query or JSON object).
Authentication and JSON transport validation stay in server.ConfigHandler.
"""
import api_m3u
import api_content
import api_library
import api_playlists
import api_artwork
import api_tasks
import api_data
import api_desktop
import api_config

GET_ROUTES = {
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
    '/api/playlist/detect': api_playlists.detect_system,
    '/api/playlist/items': api_playlists.items,
    '/api/playlist/discs': api_playlists.discs,
    '/api/progress': api_tasks.stream_progress,
    '/api/stats': api_data.get_stats,
    '/api/systems': api_data.list_systems,
    '/api/thumbnail/preview': api_artwork.serve_thumbnail_preview,
}

POST_ROUTES = {
    '/api/m3u/preview': api_m3u.preview,
    '/api/m3u/apply': api_m3u.apply,
    '/api/m3u/recover': api_m3u.recover,
    '/api/content/core-status': api_content.core_status,
    '/api/content/hints': api_content.hints,
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
    '/api/config': api_config.save_config,
    '/api/data/activate': api_data.activate,
    '/api/data/check': api_data.check,
    '/api/data/compare': api_data.compare,
    '/api/data/fetch': api_data.fetch,
    '/api/data/rollback': api_data.rollback,
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
