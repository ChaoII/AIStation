"""x-anylabeling 导入后台任务注册表（进程内，uvicorn 单 worker 安全）。"""
import time
import uuid
from dataclasses import asdict, dataclass, field


@dataclass
class ImportJob:
    job_id: str
    dataset_id: int
    user_id: int
    kind: str = "import"  # import|purge
    status: str = "pending"  # pending|running|done|failed
    phase: str = ""  # scan|import|done
    processed: int = 0
    total: int = 0
    imported: int = 0
    skipped_duplicate: int = 0
    total_annotations: int = 0
    task_id: int | None = None
    task_name: str = ""
    error: str | None = None
    file_name: str = ""
    file_size: int = 0
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.updated_at = time.time()


_JOBS: dict[str, ImportJob] = {}
_LATEST: dict[int, str] = {}  # dataset_id -> 最新 job_id

# 只保留最近 N 个任务，避免长时间运行内存无界增长
_MAX_JOBS = 200


def create_job(
    dataset_id: int,
    user_id: int,
    file_name: str = "",
    file_size: int = 0,
    kind: str = "import",
) -> ImportJob:
    job = ImportJob(
        job_id=uuid.uuid4().hex,
        dataset_id=dataset_id,
        user_id=user_id,
        kind=kind,
        file_name=file_name,
        file_size=file_size,
    )
    _JOBS[job.job_id] = job
    _LATEST[dataset_id] = job.job_id
    if len(_JOBS) > _MAX_JOBS:
        for key in list(_JOBS)[: len(_JOBS) - _MAX_JOBS]:
            dropped = _JOBS.pop(key, None)
            if dropped and _LATEST.get(dropped.dataset_id) == key:
                _LATEST.pop(dropped.dataset_id, None)
    return job


def get_job(job_id: str) -> ImportJob | None:
    return _JOBS.get(job_id)


def get_latest_job(dataset_id: int) -> ImportJob | None:
    job_id = _LATEST.get(dataset_id)
    return _JOBS.get(job_id) if job_id else None


def job_snapshot(job: ImportJob | None) -> dict | None:
    """任务快照（含派生 elapsed_sec），供 API 与列表使用。"""
    if job is None:
        return None
    data = asdict(job)
    data["elapsed_sec"] = round(max(0.0, time.time() - job.started_at), 1)
    return data
