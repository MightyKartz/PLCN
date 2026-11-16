"""One-shot server-owned plans for layout inspection and ZIP copies."""
from api_common import background, reply
import rom_storage
from task_control import TaskCancelled


def analyze(handler, context, payload):
    jobs = context.job_manager
    def work(jid):
        def cancelled():
            if jobs.cancelled(jid): raise TaskCancelled('ROM 分析已取消')
        plan = rom_storage.analyze(payload,cancelled,lambda message:jobs.update_job(jid,0,1,message))
        with jobs.lock: jobs.contexts[jid] = {'rom_storage_plan':plan}
        return plan
    reply(handler,{'job_id':background(jobs,'分析主机目录与 ZIP 支持（只读）',work)})


def convert(handler, context, payload):
    jobs = context.job_manager
    ident, selected = payload.get('analysis_job_id'), payload.get('file_ids')
    if (not isinstance(ident,str) or not isinstance(selected,list) or not selected
            or any(not isinstance(value,str) for value in selected) or len(set(selected))!=len(selected)):
        raise ValueError('请选择已分析的 ROM')
    with jobs.lock:
        job = jobs.jobs.get(ident); stored = jobs.contexts.get(ident,{})
        plan = stored.get('rom_storage_plan')
        if not job or job['status']!='completed' or not plan: raise ValueError('请重新分析目录')
        if not set(selected)<={row['id'] for row in plan['rows'] if row['zip_eligible']}: raise ValueError('所选 ROM 不可转换')
        stored.pop('rom_storage_plan')
    def work(jid):
        def cancelled():
            if jobs.cancelled(jid): raise TaskCancelled('ZIP 任务已取消；已验证电脑副本见任务记录')
        return rom_storage.convert(plan,selected,cancelled,lambda message:jobs.update_job(jid,0,len(selected),message))
    reply(handler,{'job_id':background(jobs,'生成并校验 ZIP 电脑副本',work)})
