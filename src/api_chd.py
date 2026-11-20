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


def deployment_preview(handler,context,payload):
    import chd_deploy
    jobs=context.job_manager
    def work(jid):
        def cancelled():
            if jobs.cancelled(jid): raise TaskCancelled('回传预览已取消')
        plan=chd_deploy.prepare(payload,cancelled,lambda message:jobs.update_job(jid,0,1,message))
        with jobs.lock: jobs.contexts[jid]={'chd_deployment':plan}
        return chd_deploy.public(plan)
    reply(handler,{'job_id':background(jobs,'预览 CHD 回传与引用变更（不写设备）',work)})


def deployment_apply(handler,context,payload):
    import chd_deploy
    jobs=context.job_manager;ident=payload.get('preview_job_id')
    if not isinstance(ident,str): raise ValueError('请重新生成回传预览')
    with jobs.lock:
        job=jobs.jobs.get(ident);stored=jobs.contexts.get(ident,{})
        plan=stored.get('chd_deployment')
        if not job or job['status']!='completed' or not plan or not plan['can_apply']: raise ValueError('请重新生成有效的回传预览')
        stored.pop('chd_deployment')
    def work(jid):
        def cancelled():
            if jobs.cancelled(jid): raise TaskCancelled('操作已在安全步骤停止')
        result=chd_deploy.start(plan,cancelled,lambda message:jobs.update_job(jid,0,1,message))
        if result['status']!='completed' and not result.get('cleanup'):
            raise RuntimeError('CHD 操作部分完成：'+str(result['error']))
        if result.get('cleanup'):
            # The verified remainder stays server-side; the client references it by job id.
            with jobs.lock:
                jobs.contexts[jid]={'chd_cleanup':result.pop('cleanup')}
            result['cleanup_id']=jid
        return result
    reply(handler,{'job_id':background(jobs,'执行已确认的 CHD 回传方案',work)})


def deployment_cleanup(handler,context,payload):
    import chd_deploy
    jobs=context.job_manager;ident=payload.get('cleanup_job_id')
    if not isinstance(ident,str): raise ValueError('缺少继续清理的任务标识')
    def invalid(message):
        error=ValueError(message);error.code='cleanup_invalid';return error
    with jobs.lock:
        if not jobs.contexts.get(ident,{}).get('chd_cleanup'): raise invalid('该清理任务已失效，请重新生成方案')
    def work(jid):
        def cancelled():
            if jobs.cancelled(jid): raise TaskCancelled('清理已在安全步骤停止')
        # Atomically claim the plan: only one task may execute a given id.
        with jobs.lock:
            cleanup=jobs.contexts.get(ident,{}).pop('chd_cleanup',None)
            if cleanup is None: raise invalid('该清理任务已被执行或已失效')
        try:
            result=chd_deploy.continue_cleanup(cleanup,cancelled,lambda message:jobs.update_job(jid,0,1,message))
        except Exception:
            # Nothing completed durably: return the plan so the same id can retry.
            with jobs.lock:
                jobs.contexts.setdefault(ident,{})['chd_cleanup']=cleanup
            raise
        if result.get('cleanup'):
            with jobs.lock:
                jobs.contexts[jid]={'chd_cleanup':result.pop('cleanup')}
            result['cleanup_id']=jid
        return result
    request_id=payload.get('request_id');job_id=background(jobs,'继续清理 CHD 原镜像',work)
    if isinstance(request_id,str) and request_id:
        with jobs.lock: jobs.jobs[job_id]['request_id']=request_id
    reply(handler,{'job_id':job_id})
