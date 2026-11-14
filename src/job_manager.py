"""Thread-safe task state shared by HTTP handlers and workers."""
import threading
import uuid
from task_control import TaskCancelled

class JobManager:
    def __init__(self):
        self.jobs = {}
        self.cancel_events = {}
        self.contexts = {}
        self.stopping = False
        self.lock = threading.Lock()

    def create_job(self):
        job_id = str(uuid.uuid4())
        with self.lock:
            if self.stopping:
                raise RuntimeError('PLCN 正在退出')
            self.cancel_events[job_id] = threading.Event()
            self.jobs[job_id] = {
                'status': 'pending',
                'progress': 0,
                'total': 0,
                'message': '',
                'messages': [],
                'result': None,
                'error': None
            }
        return job_id

    def update_job(self, job_id, progress, total, message):
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id]['progress'] = progress
                self.jobs[job_id]['total'] = total
                messages = self.jobs[job_id]['messages']
                if message and (not messages or messages[-1] != message):
                    self.jobs[job_id]['messages'] = (messages + [message])[-200:]
                self.jobs[job_id]['message'] = message
                self.jobs[job_id]['status'] = 'running'

    def complete_job(self, job_id, result=None):
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id]['status'] = 'cancelled' if self.cancel_events[job_id].is_set() else 'completed'
                self.jobs[job_id]['result'] = result
                self.jobs[job_id]['progress'] = self.jobs[job_id]['total']

    def fail_job(self, job_id, error):
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id]['status'] = 'cancelled' if isinstance(error, TaskCancelled) else 'failed'
                self.jobs[job_id]['error'] = str(error)

    def cancelled(self, job_id):
        return self.cancel_events[job_id].is_set()

    def cancel(self, job_id):
        with self.lock:
            if job_id not in self.jobs:
                raise ValueError('任务不存在')
            if self.jobs[job_id]['status'] in ('pending', 'running'):
                self.cancel_events[job_id].set()
                self.jobs[job_id]['message'] = '正在取消，将在安全步骤边界停止'

    def active(self):
        with self.lock:
            return any(job['status'] in ('pending', 'running') for job in self.jobs.values())

    def snapshot(self):
        with self.lock:
            return [dict(job, id=key) for key, job in reversed(list(self.jobs.items()))][:30]

    def get_job(self, job_id):
        with self.lock:
            return self.jobs.get(job_id)
