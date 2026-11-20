"""Desktop HTTP handlers; request transport is owned by server.py."""
import threading
import app_paths
import chd_operations
import rom_storage
from api_common import reply


def instance(handler, context, payload):
    reply(handler, {'instance_id': getattr(handler.server, 'instance_id', None)})


def desktop(handler, context, payload):
    jobs = context.job_manager
    config_path = context.CONFIG_FILE
    reply(handler, {'data_dir': str(app_paths.user_data_dir()), 'cache_dir': str(app_paths.cache_dir()),
                    'config_path': str(config_path), 'resource_dir': str(app_paths.resource_root()),
                    'active_jobs': jobs.active(), 'rom_storage_operations': rom_storage.history(), 'chd_operations': chd_operations.history(), 'jobs': jobs.snapshot()})


def pick(handler, context, payload):
    from native_dialog import PICK_KINDS, pick as pick_native
    kind = payload.get('kind', 'directory')
    initial = payload.get('initial', '')
    if kind not in PICK_KINDS or not isinstance(initial, str):
        raise ValueError('无效的文件选择参数')
    picker = getattr(handler.server, 'pick_file', pick_native)
    selected = picker(kind, initial)
    reply(handler, {'paths': selected} if isinstance(selected, list) else {'path': selected})


def activate(handler, context, payload):
    activate_window = getattr(handler.server, 'activate_window', None)
    if activate_window is None:
        reply(handler, {'error': '当前实例使用浏览器界面'}, 409)
        return
    activate_window()
    reply(handler, {'activated': True})


def shutdown(handler, context, payload):
    if not context.job_manager.prepare_shutdown():
        reply(handler, {'error': '仍有任务运行，请取消或等待完成后再退出'}, 409)
        return
    reply(handler, {'stopped': True})
    threading.Thread(target=handler.server.shutdown, daemon=True).start()
