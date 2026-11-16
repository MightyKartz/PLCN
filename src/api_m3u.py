"""Server-owned M3U previews and durable operation recovery."""
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
        result=transaction.start(plan)
        context.job_manager.contexts[jid]={'m3u_operation':result['operation_id']}
        if result['status']!='applied':
            raise RuntimeError('多盘操作部分完成，请在任务与恢复中检查：'+result['operation_id']+' · '+str(result['error']))
        return result
    reply(handler,{'job_id':background(context.job_manager,'应用已确认的多盘方案',work)})


def history(handler,context,query):
    reply(handler,{'operations':transaction.receipts()})


def recover(handler,context,payload):
    ident=payload.get('id');restore=payload.get('action')=='restore'
    if payload.get('action') not in {'restore','resume'}: raise ValueError('请选择恢复或继续操作')
    manifest=transaction.receipt_path(ident)
    if json.loads(manifest.read_text(encoding='utf-8'))['mode']=='chd_references':
        raise ValueError('请从 CHD 操作恢复；必须先还原原镜像，再还原引用')
    def work(jid):
        result=transaction.run(ident,restore=restore)
        if result['status'] not in {'applied','restored'}: raise RuntimeError(str(result['error'])+'；记录：'+ident)
        return result
    reply(handler,{'job_id':background(context.job_manager,'恢复多盘修改' if restore else '继续多盘操作',work)})
