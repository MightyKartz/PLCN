"""Game-management plans are server-owned and can be consumed only once."""
import game_management as games
from api_common import background, reply
from task_control import checkpoint


def preview(handler, context, payload):
    mode = payload.get('mode')
    if not isinstance(mode, str) or mode not in {'import', 'remove', 'edit'}:
        raise ValueError('游戏管理操作无效')
    config = games.validate_import(payload) if mode == 'import' else None
    def work(jid):
        if config:
            plan = games.import_preview(config, lambda a, b, text: context.job_manager.update_job(jid, a, b, text),
                lambda: checkpoint(lambda: context.job_manager.cancelled(jid)))
        else:
            plan = games.edit_preview(payload) if mode == 'edit' else games.remove_preview(payload)
        with context.job_manager.lock:
            context.job_manager.contexts[jid] = {'game_plan': plan}
        return games.public_preview(plan)
    reply(handler, {'job_id': background(context.job_manager, '预览游戏管理操作', work)})


def details(handler, context, payload):
    reply(handler, games.details(payload))


def apply(handler, context, payload):
    ident = payload.get('preview_job_id')
    if not isinstance(ident, str): raise ValueError('请先完成预览')
    job = context.job_manager.get_job(ident)
    if not job or job['status'] != 'completed': raise ValueError('请先完成预览')
    with context.job_manager.lock:
        plan = context.job_manager.contexts.get(ident, {}).pop('game_plan', None)
    if not plan or not plan['can_apply']: raise ValueError('预览无效或已应用，请重新预览')
    reply(handler, {'job_id': background(context.job_manager, '更新游戏库', lambda jid: games.apply(plan,
        lambda a, b, text: context.job_manager.update_job(jid, a, b, text),
        lambda: checkpoint(lambda: context.job_manager.cancelled(jid))))})


def save_mapping(handler, context, payload):
    reply(handler, {'job_id':background(context.job_manager, '保存手动启动位置', lambda jid: games.save_import_mapping(payload))})
