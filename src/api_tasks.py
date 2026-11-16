"""Tasks HTTP handlers; request transport is owned by server.py."""
import json
import time
import repair_history
from api_common import reply, background


def cancel(handler, context, payload):
    jobs = context.job_manager
    jobs.cancel(payload.get('job_id'))
    reply(handler, {'cancel_requested': True})


def retry(handler, context, payload):
    jobs = context.job_manager
    old_id = payload.get('job_id')
    job = jobs.get_job(old_id)
    if not job or job['status'] not in ('completed', 'cancelled', 'failed'):
        raise ValueError('请选择已结束的任务')
    target = jobs.contexts.get(old_id, {}).get('thumbnails_dir')
    details = (job.get('result') or {}).get('download_summary', {}).get('details', [])
    tasks = list(dict.fromkeys((r['system'], r['source'], r['game']) for r in details
                              if (r.get('status') == 'failed' or r.get('reason') == 'cancelled')
                              and r.get('reason') != 'filename_collision'))
    if not tasks:
        raise ValueError('没有可重试的图片任务；命名冲突请先修改名称')
    def retry(jid):
        from thumbnail_downloader import ThumbnailDownloader
        jobs.contexts[jid] = {'thumbnails_dir': target}
        downloader = ThumbnailDownloader(target)
        downloader.cancel_check = lambda: jobs.cancelled(jid)
        return {'download_summary': downloader.download_batch(tasks, lambda a, b, text: jobs.update_job(jid, a, b, text))}
    reply(handler, {'job_id': background(jobs, '重试未完成图片，不修改列表', retry)})


def restore(handler, context, payload):
    reply(handler, repair_history.restore(payload.get('id')))


def stream_progress(handler, context, payload):
    job_id = payload.get('job_id', [''])[0]
    handler.send_response(200)
    handler.send_header("Content-type", "text/event-stream")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "keep-alive")
    handler.end_headers()

    while True:
        job = context.job_manager.get_job(job_id)
        if not job:
            handler.wfile.write(b"data: " + json.dumps({"error": "Job not found"}).encode() + b"\n\n")
            break

        data = {
            "status": job['status'],
            "progress": job['progress'],
            "total": job['total'],
            "message": job['message'],
            "result": job['result'],
            "error": job['error']
        }

        try:
            handler.wfile.write(b"data: " + json.dumps(data).encode() + b"\n\n")
            handler.wfile.flush()
        except BrokenPipeError:
            break

        if job['status'] in ['completed', 'failed', 'cancelled']:
            break

        time.sleep(0.5)


def workbench_status(handler, context, query):
    """Small task projection; full receipts stay behind the details action."""
    from api_common import reply
    jobs = context.job_manager.snapshot()
    job = next((j for j in jobs if j['status'] in ('pending', 'running')), jobs[0] if jobs else None)
    if job:
        result = job.get('result') or {}
        job = {key: job[key] for key in ('id', 'status', 'progress', 'total', 'message', 'error')}
        job['partial'] = bool(result.get('errors') or result.get('download_summary', {}).get('total', {}).get('failed'))
    reply(handler, {'job': job, 'active_count': sum(j['status'] in ('pending', 'running') for j in jobs)})
