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


def relocation_preview(handler, context, payload):
    import chd_deploy
    import rom_relocation
    jobs=context.job_manager;analysis=None
    if payload.get('analysis_job_id'):
        ident=payload['analysis_job_id']
        if not isinstance(ident,str): raise ValueError('请重新分析目录')
        with jobs.lock:
            job=jobs.jobs.get(ident);analysis=jobs.contexts.get(ident,{}).get('rom_storage_plan')
            if not job or job['status']!='completed' or not analysis: raise ValueError('请重新分析目录')
    def work(jid):
        def cancelled():
            if jobs.cancelled(jid): raise TaskCancelled('目录整理预览已取消')
        plan=rom_relocation.prepare(payload,analysis,cancelled,lambda message:jobs.update_job(jid,0,1,message))
        with jobs.lock: jobs.contexts[jid]={'rom_relocation_plan':plan}
        return chd_deploy.public(plan)
    reply(handler,{'job_id':background(jobs,'预览目录整理／ZIP 回传与引用（只读）',work)})


def relocation_apply(handler, context, payload):
    import chd_deploy
    jobs=context.job_manager;ident=payload.get('preview_job_id')
    if not isinstance(ident,str): raise ValueError('请重新生成整理预览')
    with jobs.lock:
        job=jobs.jobs.get(ident);stored=jobs.contexts.get(ident,{})
        plan=stored.get('rom_relocation_plan')
        if not job or job['status']!='completed' or not plan or not plan['can_apply']: raise ValueError('请重新生成有效的整理预览')
        stored.pop('rom_relocation_plan')
    def work(jid):
        def cancelled():
            if jobs.cancelled(jid): raise TaskCancelled('操作已停止，请从任务记录继续或恢复')
        record=chd_deploy.start(plan,cancelled,lambda message:jobs.update_job(jid,0,1,message))
        if record['status']!='completed': raise RuntimeError('整理操作部分完成：'+record['id']+' · '+str(record['error']))
        return record
    reply(handler,{'job_id':background(jobs,'执行已确认的目录／ZIP 方案',work)})


def relocation_recover(handler, context, payload):
    import json
    import chd_deploy
    ident=payload.get('id');action=payload.get('action');jobs=context.job_manager
    record=json.loads(chd_deploy.receipt(ident).read_text(encoding='utf-8'))
    if record.get('kind')!='rom_relocation' or action not in {'resume','restore'}: raise ValueError('请选择有效的整理操作与恢复方式')
    def work(jid):
        def cancelled():
            if jobs.cancelled(jid): raise TaskCancelled('整理操作已停止，可继续恢复')
        result=chd_deploy.run(ident,action=='restore',cancelled,lambda message:jobs.update_job(jid,0,1,message))
        if result['status'] not in {'completed','restored'}: raise RuntimeError('整理操作待处理：'+ident+' · '+str(result['error']))
        return result
    reply(handler,{'job_id':background(jobs,'恢复原目录与引用' if action=='restore' else '核对后继续整理',work)})
