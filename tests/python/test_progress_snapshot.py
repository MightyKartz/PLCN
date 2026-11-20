import io
import json
from types import SimpleNamespace

from job_manager import JobManager
import api_tasks


def test_progress_sends_terminal_snapshot_when_job_finishes_during_write(monkeypatch):
    jobs = JobManager()
    ident = jobs.create_job()
    jobs.update_job(ident, 0, 1, 'working')
    running = jobs.get_job(ident)

    class Output(io.BytesIO):
        def write(self, data):
            result = super().write(data)
            if jobs.active():
                jobs.complete_job(ident, {'done': True})
            return result

    output = Output()
    handler = SimpleNamespace(wfile=output, send_response=lambda *args: None,
                              send_header=lambda *args: None, end_headers=lambda: None)
    monkeypatch.setattr(api_tasks.time, 'sleep', lambda _: None)
    api_tasks.stream_progress(handler, SimpleNamespace(job_manager=jobs), {'job_id': [ident]})
    events = [json.loads(line[6:]) for line in output.getvalue().decode().splitlines() if line.startswith('data: ')]
    assert [event['status'] for event in events] == ['running', 'completed']
    assert events[-1]['result'] == {'done': True}
    assert running['status'] == 'running'


def test_find_by_request_survives_snapshot_cap():
    jobs = JobManager()
    target = jobs.create_job(); jobs.complete_job(target)
    with jobs.lock: jobs.jobs[target]['request_id'] = 'req-9'
    for _ in range(35):
        other = jobs.create_job(); jobs.complete_job(other)
    assert all(job['id'] != target for job in jobs.snapshot())
    found = jobs.find_by_request('req-9')
    assert found['id'] == target and found['request_id'] == 'req-9'
    assert jobs.find_by_request('missing') is None and jobs.find_by_request('') is None
