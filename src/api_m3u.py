"""Server-owned M3U previews and guarded application."""
import json
from api_common import reply, background
import m3u_plan
import m3u_transaction as transaction


def preview(handler,context,payload):
    def work(jid):
        plan=m3u_plan.prepare(payload)
        context.job_manager.contexts[jid]={'m3u_plan':plan}
        return m3u_plan.public(plan)
    reply(handler,{'job_id':background(context.job_manager,'预览多盘变更（不写入）',work)})


def apply(handler,context,payload):
    ident=payload.get('preview_job_id')
    job=context.job_manager.get_job(ident)
    with context.job_manager.lock:
        stored=context.job_manager.contexts.get(ident,{})
        plan=stored.get('m3u_plan')
        if not job or job['status']!='completed' or not plan or not plan['can_apply']:
            raise ValueError('请重新生成有效的 M3U 预览')
        stored.pop('m3u_plan')
    def work(jid):
        return transaction.apply(plan)
    reply(handler,{'job_id':background(context.job_manager,'应用已确认的多盘方案',work)})
