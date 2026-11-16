"""Content scan plans remain on the server until explicitly confirmed."""
import content_scan as scan
import core_catalog
import automatic_scan
from api_common import reply, background


def auto_preview(handler, context, payload):
    root, sources = automatic_scan.validate(payload)
    def work(jid):
        result = automatic_scan.preview(root, sources, lambda a, b, text: context.job_manager.update_job(jid, a, b, text), lambda: context.job_manager.cancelled(jid))
        context.job_manager.contexts[jid] = {'automatic_plan': result}
        return automatic_scan.public_result(result)
    reply(handler, {'job_id': background(context.job_manager, '扫描新增游戏', work)})


def auto_apply(handler, context, payload):
    ident, systems = payload.get('preview_job_id'), payload.get('systems')
    job = context.job_manager.get_job(ident)
    if not job or job['status'] != 'completed' or not isinstance(systems, list) or not systems or any(not isinstance(s, str) for s in systems):
        raise ValueError('请先完成扫描并选择要导入的主机')
    with context.job_manager.lock:
        result = context.job_manager.contexts.get(ident, {}).get('automatic_plan')
        if not result or any(s not in result['plans'] for s in systems) or len(set(systems)) != len(systems):
            raise ValueError('扫描结果无效，请重新分析')
        context.job_manager.contexts[ident].pop('automatic_plan')
    reply(handler, {'job_id': background(context.job_manager, '导入新增游戏', lambda jid: automatic_scan.apply(result, systems,
        lambda a, b, text: context.job_manager.update_job(jid, a, b, text), lambda: context.job_manager.cancelled(jid)))})


def setup(handler, context, query):
    reply(handler, scan.setup(query.get('root', [''])[0]))


def directories(handler, context, query):
    reply(handler, scan.browse(query.get('path', [''])[0]))


def preview(handler, context, payload):
    config = scan.validate(payload)
    def work(jid):
        plan = scan.preview(config, lambda a, b, text: context.job_manager.update_job(jid, a, b, text),
                            lambda: context.job_manager.cancelled(jid))
        context.job_manager.contexts[jid] = {'content_plan': plan}
        return {key: plan[key] for key in ('target', 'added', 'retained', 'skipped', 'can_apply', 'core_status', 'note')}
    reply(handler, {'job_id': background(context.job_manager, '扫描游戏目录（不会写入列表）', work)})


def apply(handler, context, payload):
    ident = payload.get('preview_job_id')
    job = context.job_manager.get_job(ident)
    if not job or job['status'] != 'completed':
        raise ValueError('请先完成扫描预览')
    with context.job_manager.lock:
        plan = context.job_manager.contexts.get(ident, {}).pop('content_plan', None)
    if not plan or not plan['can_apply']:
        raise ValueError('预览无效或已经应用，请重新扫描')
    reply(handler, {'job_id': background(context.job_manager, '更新游戏列表', lambda jid: scan.apply(plan))})


def core_download(handler, context, payload):
    core, abi = payload.get('core_id'), payload.get('abi')
    core_catalog.validate(core, abi)
    reply(handler, {'job_id': background(context.job_manager, '从 Libretro 官方下载核心和信息文件',
                                       lambda jid: core_catalog.download(core, abi))})


def core_transfer(handler, context, payload):
    core, abi, root = payload.get('core_id'), payload.get('abi'), payload.get('root')
    core_catalog.validate(core, abi)
    reply(handler, {'job_id': background(context.job_manager, '传输核心（不会安装）',
                                       lambda jid: core_catalog.transfer(core, abi, root))})


def hints(handler, context, payload):
    reply(handler, scan.hints(payload.get('root'), payload.get('system'), payload.get('directory'), payload.get('playlist_name')))


def core_info(handler, context, query):
    reply(handler, core_catalog.info(query.get('core_id', [''])[0]))


def core_status(handler, context, payload):
    reply(handler, scan.core_status(payload.get('root'), payload.get('core_path')))
