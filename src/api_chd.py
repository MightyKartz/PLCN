"""Server-owned local CHD plans, cancellable workers and durable results."""
from api_common import reply, background
import chd_operations
from task_control import TaskCancelled


def analyze(handler,context,payload):
    jobs=context.job_manager
    def work(jid):
        def cancelled():
            if jobs.cancelled(jid): raise TaskCancelled('空间分析已取消')
        result=chd_operations.analyze(payload,cancelled,lambda message:jobs.update_job(jid,0,1,message))
        with jobs.lock: jobs.contexts[jid]={'chd_plan':result}
        return chd_operations.public(result)
    reply(handler,{'job_id':background(jobs,'分析 CHD 空间与能力',work)})


def convert(handler,context,payload):
    jobs=context.job_manager;ident=payload.get('analysis_job_id');selected=payload.get('disc_ids')
    if not isinstance(ident,str) or not isinstance(selected,list) or not selected or any(not isinstance(value,str) for value in selected) or len(set(selected))!=len(selected):
        raise ValueError('请选择已分析的光盘')
    with jobs.lock:
        job=jobs.jobs.get(ident);stored=jobs.contexts.get(ident,{})
        plan=stored.get('chd_plan')
        if not job or job['status']!='completed' or not plan or not plan['can_convert']:
            raise ValueError('请重新分析空间与工具')
        if not set(selected)<={row['id'] for row in plan['rows'] if row['eligible']}: raise ValueError('所选光盘已失效')
        stored.pop('chd_plan')
    def work(jid):
        def cancelled():
            if jobs.cancelled(jid): raise TaskCancelled('CHD 任务已取消；已验证输出保留，未完成工作文件已清理')
        return chd_operations.convert(plan,selected,cancelled,lambda message:jobs.update_job(jid,0,len(selected),message))
    reply(handler,{'job_id':background(jobs,'电脑 CHD 转换（保留原文件）',work)})
