"""Host the existing workbench in a system WebView."""
from contextlib import ExitStack
import sys
from threading import Event, Thread

import app_paths
from app_brand import NAME
import server


def run_window():
    if sys.platform not in ('darwin', 'win32'):
        raise RuntimeError('独立窗口预览仅支持 macOS 和 Windows。')

    import webview

    with ExitStack() as launch:
        httpd, url = launch.enter_context(server.local_service(activate_window=True))
        if httpd is None:
            return

        window = webview.create_window(NAME, url, width=1280, height=820, min_size=(720, 540))
        service = Thread(target=httpd.serve_forever, name='retroarch-assistant-http')
        closing = Event()

        def stop_service():
            httpd.shutdown()
            service.join()
            launch.close()

        def activate_window():
            if window.events.minimized.is_set():
                window.restore()
            window.show()

        def pick_items_darwin(initial):
            """NSOpenPanel that accepts files AND folders in one multi-select panel."""
            import AppKit
            from Foundation import NSURL
            from PyObjCTools import AppHelper
            selected, finished = [], Event()
            def run():
                panel = AppKit.NSOpenPanel.openPanel()
                panel.setTitle_(NAME + ' — 选择游戏文件或文件夹')
                panel.setCanChooseFiles_(True)
                panel.setCanChooseDirectories_(True)
                panel.setAllowsMultipleSelection_(True)
                if initial:
                    panel.setDirectoryURL_(NSURL.fileURLWithPath_(initial))
                if panel.runModal() == AppKit.NSFileHandlingPanelOKButton:
                    selected.extend(panel.filenames())
                finished.set()
            AppHelper.callAfter(run)
            finished.wait()
            return selected

        def pick_file(kind, initial):
            if kind == 'items' and sys.platform == 'darwin':
                return pick_items_darwin(initial)
            dialog_type = webview.FileDialog.FOLDER if kind == 'directory' else webview.FileDialog.OPEN
            file_types = ('RetroArch playlist (*.lpl)',) if kind == 'file' else ()
            paths = window.create_file_dialog(
                dialog_type, directory=initial, allow_multiple=kind in ('files', 'items'), file_types=file_types,
            )
            if kind in ('files', 'items'):
                return list(paths or ())
            return paths[0] if paths else ''

        def allow_close():
            if server.job_manager.prepare_shutdown():
                closing.set()
                # AppKit can terminate the process directly after accepting Cmd+Q.
                stop_service()
                return True
            Thread(target=window.run_js, args=(
                "showStatus(desktopText('仍有任务运行，请取消或等待完成后再退出', "
                "'Active tasks must finish or be cancelled before quitting.'), 'error')",
            ), daemon=True).start()
            return False

        def close_when_service_stops():
            service.join()
            if not closing.is_set() and not window.events.closed.is_set():
                window.destroy()

        window.events.restored += window.events.minimized.clear
        window.events.maximized += window.events.minimized.clear
        window.events.closing += allow_close
        httpd.activate_window = activate_window
        httpd.pick_file = pick_file
        service.start()
        try:
            webview.start(
                close_when_service_stops, gui='edgechromium' if sys.platform == 'win32' else None,
                private_mode=False, storage_path=str(app_paths.cache_dir() / 'webview'),
            )
        finally:
            if not closing.is_set():
                stop_service()
