"""HTTP response and background job helpers."""
import json
import threading


def reply(handler, data, status=200):
    body = json.dumps(data, ensure_ascii=False).encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Content-Length', str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def background(jobs, title, work):
    job_id = jobs.create_job()
    with jobs.lock:
        jobs.jobs[job_id]['title'] = title
    def run():
        try:
            jobs.update_job(job_id, 0, 1, title)
            result = work(job_id)
            jobs.complete_job(job_id, result)
        except Exception as error:
            jobs.fail_job(job_id, error)
    threading.Thread(target=run, name='plcn-' + job_id, daemon=False).start()
    return job_id
