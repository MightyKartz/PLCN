class TaskCancelled(Exception):
    """Cancellation observed at a safe boundary, never mid-write."""


def checkpoint(cancel_check):
    if cancel_check and cancel_check():
        raise TaskCancelled('任务已取消；已完成的写回和下载会保留')
