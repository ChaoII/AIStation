"""数据落地（抽帧/清洗）后台任务注册表（进程内，与 import_jobs 同模式）。

任务生命周期短（抽帧+清洗通常几十秒内完成），用进程内字典即可，
与 x-anylabeling 导入任务保持一致，避免引入额外表与迁移。
"""
import time
import uuid
from dataclasses import asdict, dataclass, field


@dataclass
class PreprocessJob:
    job_id: str
    dataset_id: int
    user_id: int
    source: str = "video"  # video | images
    source_name: str = ""
    status: str = "pending"  # pending | running | done | failed
    phase: str = ""  # extract | clean | done
    processed: int = 0
    total: int = 0
    ingested: int = 0
    # 各剔除原因计数
    dropped_blur: int = 0
    dropped_dark: int = 0
    dropped_bright: int = 0
    dropped_small: int = 0
    dropped_duplicate: int = 0
    dropped_unreadable: int = 0
    error: str | None = None
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.updated_at = time.time()


_JOBS: dict[str, PreprocessJob] = {}
_MAX_JOBS = 200


def create_job(
    dataset_id: int,
    user_id: int,
    source: str,
    source_name: str = "",
) -> PreprocessJob:
    job = PreprocessJob(
        job_id=uuid.uuid4().hex,
        dataset_id=dataset_id,
        user_id=user_id,
        source=source,
        source_name=source_name,
    )
    _JOBS[job.job_id] = job
    if len(_JOBS) > _MAX_JOBS:
        for key in list(_JOBS)[: len(_JOBS) - _MAX_JOBS]:
            _JOBS.pop(key, None)
    return job


def get_job(job_id: str) -> PreprocessJob | None:
    return _JOBS.get(job_id)


def job_snapshot(job: PreprocessJob | None) -> dict | None:
    if job is None:
        return None
    data = asdict(job)
    data["elapsed_sec"] = round(max(0.0, time.time() - job.started_at), 1)
    return data
