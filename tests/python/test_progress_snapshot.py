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
