"""x-anylabeling 导入后台任务注册表（进程内，uvicorn 单 worker 安全）。"""
import uuid
from dataclasses import dataclass


@dataclass
class ImportJob:
    job_id: str
    dataset_id: int
    user_id: int
    status: str = "pending"  # pending|running|done|failed
    phase: str = ""
    processed: int = 0
    total: int = 0
    imported: int = 0
    total_annotations: int = 0
    task_id: int | None = None
    task_name: str = ""
    error: str | None = None


_JOBS: dict[str, ImportJob] = {}

# 只保留最近 N 个任务，避免长时间运行内存无界增长
_MAX_JOBS = 200


def create_job(dataset_id: int, user_id: int) -> ImportJob:
    job = ImportJob(job_id=uuid.uuid4().hex, dataset_id=dataset_id, user_id=user_id)
    _JOBS[job.job_id] = job
    if len(_JOBS) > _MAX_JOBS:
        for key in list(_JOBS)[: len(_JOBS) - _MAX_JOBS]:
            _JOBS.pop(key, None)
    return job


def get_job(job_id: str) -> ImportJob | None:
    return _JOBS.get(job_id)
