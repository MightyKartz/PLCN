"""Desktop HTTP handlers; request transport is owned by server.py."""
import threading
import app_paths
import repair_history
from api_common import reply


def instance(handler, context, payload):
    reply(handler, {'instance_id': getattr(handler.server, 'instance_id', None)})


def desktop(handler, context, payload):
    jobs = context.job_manager
    config_path = context.CONFIG_FILE
    reply(handler, {'data_dir': str(app_paths.user_data_dir()), 'cache_dir': str(app_paths.cache_dir()),
                    'config_path': str(config_path), 'resource_dir': str(app_paths.resource_root()),
                    'active_jobs': jobs.active(), 'history': repair_history.list_history(), 'jobs': jobs.snapshot()})


def pick(handler, context, payload):
    from native_dialog import pick
    selected = pick(payload.get('kind', 'directory'), payload.get('initial', ''))
    reply(handler, {'path': selected})


def shutdown(handler, context, payload):
    jobs = context.job_manager
    with jobs.lock:
        if any(job['status'] in ('pending', 'running') for job in jobs.jobs.values()):
            reply(handler, {'error': '仍有任务运行，请取消或等待完成后再退出'}, 409)
            return
        jobs.stopping = True
    reply(handler, {'stopped': True})
    threading.Thread(target=handler.server.shutdown, daemon=True).start()
