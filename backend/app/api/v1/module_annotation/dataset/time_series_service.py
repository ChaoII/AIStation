"""时间序列上传 service：CSV 探测 + RustFS 存储 + 入库计数。

时间序列用 ``AnnotationTimeSeriesModel`` 记录，文件按扩展名白名单（.csv/.tsv）
与大小（≤200MB）校验；探测表头识别时间列（默认首列或含 time/timestamp/date/时间
关键字），数值列（其余可解析为 float 的列），统计行数、推断时间单位（首条时间值
绝对值 > 1e12 判 ms 否则 s）与时间范围；写入对象存储并入库，同时递增
``dataset.time_series_count``。异常时删除已上传对象并重新抛出。
"""
import asyncio
import csv
import io
import uuid
from pathlib import Path

from sqlalchemy import select

from app.api.v1.module_annotation.dataset.model import (
    AnnotationTimeSeriesModel,
    DatasetModel,
    ImageStatus,
)
from app.core.audit import set_create_audit
from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import log
from app.utils.s3_client import s3_client

ALLOWED_TIME_SERIES_EXTENSIONS: set[str] = {".csv", ".tsv"}

MAX_TIME_SERIES_BYTES = 200 * 1024 * 1024  # 200MB
MAX_CSV_ROWS = 500_000  # 数据行数上限

# 表头中识别时间列的关键字（命中任一即视为时间列）
_TIME_KEYWORDS = ("time", "timestamp", "date", "时间")

_EXT_CONTENT_TYPE: dict[str, str] = {
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
}


def content_type_for(ext: str) -> str:
    """按扩展名返回 Content-Type，未知类型回退 octet-stream。"""
    return _EXT_CONTENT_TYPE.get(ext.lower(), "application/octet-stream")


def _decode_csv(content: bytes) -> str:
    """按 utf-8-sig → gbk → latin1 依次解码 CSV 原文。"""
    for enc in ("utf-8-sig", "gbk"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("latin1")


def _find_time_column(headers: list[str]) -> tuple[str | None, int | None]:
    """识别时间列：优先表头含时间关键字的列，否则默认首列；无列时返回 (None, None)。"""
    for rstrip_idx, header in enumerate(headers):
        lowered = header.lower()
        if any(k in lowered for k in _TIME_KEYWORDS):
            return header, rstrip_idx
    if headers:
        return headers[0], 0
    return None, None


def _probe_csv(content: bytes) -> dict:
    """探测 CSV 结构，返回 ``{time_column, value_columns, row_count, time_unit,
    start_time, end_time}``。

    逐行（csv reader）解析：数据行数超上限即中止；无有效时间列、无数值列抛业务错误。
    """
    text = _decode_csv(content)
    reader = csv.reader(io.StringIO(text))

    headers: list[str] | None = None
    for row in reader:
        if row and any(cell.strip() for cell in row):
            headers = [c.strip() for c in row]
            break
    if not headers:
        raise CustomException(
            msg="无法识别时间列: 文件为空或缺少表头", code=400, status_code=400
        )

    time_column, time_idx = _find_time_column(headers)
    if time_column is None:
        raise CustomException(
            msg="无法识别时间列: 缺少表头", code=400, status_code=400
        )

    # 数值列候选：除时间列外的其余列（仍保序）
    value_candidates: dict[int, str] = {
        i: headers[i] for i in range(len(headers)) if i != time_idx
    }
    numeric = set(value_candidates.keys())

    row_count = 0
    first_valid_time: float | None = None
    times: list[float] = []

    for row in reader:
        if not row or not any(cell.strip() for cell in row):
            continue
        row_count += 1
        if row_count > MAX_CSV_ROWS:
            raise CustomException(
                msg=f"数据行数超过上限（{MAX_CSV_ROWS} 行）: {row_count}",
                code=400,
                status_code=400,
            )
        # 时间列：取本行时间值（非数值行不参与统计）
        if time_idx < len(row):
            cell = row[time_idx].strip()
            try:
                t = float(cell)
                times.append(t)
                if first_valid_time is None:
                    first_valid_time = t
            except ValueError:
                pass
        # 数值列：只要出现非 float 值即从候选剔除
        for idx in list(numeric):
            if idx >= len(row):
                numeric.discard(idx)
                continue
            cell = row[idx].strip()
            try:
                float(cell)
            except ValueError:
                numeric.discard(idx)

    if not times:
        raise CustomException(
            msg=f"无法识别时间列: 列「{time_column}」无有效数值数据", code=400, status_code=400
        )
    value_columns = [value_candidates[i] for i in sorted(numeric)]
    if not value_columns:
        raise CustomException(
            msg="未识别到数值列: 除时间列外无数字型数据", code=400, status_code=400
        )

    time_unit = "ms" if abs(first_valid_time) > 1e12 else "s"
    return {
        "time_column": time_column,
        "value_columns": value_columns,
        "row_count": row_count,
        "time_unit": time_unit,
        "start_time": min(times),
        "end_time": max(times),
    }


class TimeSeriesService:

    @classmethod
    async def upload_time_series(cls, db, dataset_id: int, file, auth) -> AnnotationTimeSeriesModel:
        """上传单个时间序列 CSV：白名单/大小校验、探测、写入 RustFS、入库并更新计数。

        ``db`` 为调用方传入的 async 会话（便于复用事务）；异常时删除已上传
        对象并重新抛出。
        """
        filename = file.filename or "unnamed"
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_TIME_SERIES_EXTENSIONS:
            raise CustomException(
                msg=f"不支持的时间序列格式: {filename}", code=400, status_code=400
            )
        size = getattr(file, "size", None)
        if size is not None and size > MAX_TIME_SERIES_BYTES:
            raise CustomException(
                msg=f"文件过大（>200MB）: {filename}", code=400, status_code=400
            )

        content = await file.read()
        if not content:
            raise CustomException(msg="上传内容为空", code=400, status_code=400)

        # 探测（探测失败则不写对象存储，避免污染 RustFS）
        probe = _probe_csv(content)

        object_key = f"datasets/{dataset_id}/time_series/{uuid.uuid4().hex}{ext}"

        await asyncio.to_thread(
            s3_client.upload_fileobj,
            io.BytesIO(content),
            object_key,
            None,
            content_type_for(ext),
        )
        uploaded = True

        try:
            dataset = await db.get(DatasetModel, dataset_id)
            if not dataset or dataset.is_deleted:
                raise CustomException(
                    msg=f"数据集不存在: {dataset_id}", code=404, status_code=404
                )
            ts = AnnotationTimeSeriesModel(
                dataset_id=dataset_id,
                name=filename,
                object_key=object_key,
                time_column=probe["time_column"],
                value_columns=probe["value_columns"],
                row_count=probe["row_count"],
                time_unit=probe["time_unit"],
                start_time=probe["start_time"],
                end_time=probe["end_time"],
                size_bytes=len(content),
                status=ImageStatus.UNANNOTATED,
            )
            set_create_audit(ts, auth)
            db.add(ts)
            await db.flush()
            dataset.time_series_count += 1
        except Exception:
            # 入库失败：删除本次已上传对象，避免孤儿
            if uploaded:
                try:
                    await asyncio.to_thread(s3_client.delete_object, object_key)
                except Exception as e2:  # noqa: BLE001
                    log.warning(f"[时间序列上传] 补偿删除对象失败: {e2}")
            raise

        return ts

    @classmethod
    async def list_time_series(cls, dataset_id: int) -> list[dict]:
        """按数据集列出时间序列（不含已删除）。"""
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AnnotationTimeSeriesModel)
                    .where(
                        AnnotationTimeSeriesModel.dataset_id == dataset_id,
                        AnnotationTimeSeriesModel.is_deleted == False,  # noqa: E712
                    )
                    .order_by(AnnotationTimeSeriesModel.id.desc())
                )
            ).scalars().all()
            return [cls.series_out(v) for v in rows]

    @classmethod
    async def get_time_series(cls, series_id: int) -> dict:
        """查询单个时间序列详情，不存在抛 404。"""
        async with async_db_session() as db:
            ts = await db.get(AnnotationTimeSeriesModel, series_id)
            if not ts or ts.is_deleted:
                raise CustomException(
                    msg=f"时间序列不存在: {series_id}", code=404, status_code=404
                )
            return cls.series_out(ts)

    @classmethod
    async def get_content(cls, series_id: int) -> str:
        """返回时间序列的原始 CSV 原文（UTF-8 解码）。"""
        async with async_db_session() as db:
            ts = await db.get(AnnotationTimeSeriesModel, series_id)
            if not ts or ts.is_deleted:
                raise CustomException(
                    msg=f"时间序列不存在: {series_id}", code=404, status_code=404
                )
            object_key = ts.object_key
        buf = await asyncio.to_thread(s3_client.download_fileobj, object_key)
        return _decode_csv(buf.read())

    @classmethod
    async def lock_time_series(cls, series_id: int, user_id: int) -> dict:
        """按序列整体上锁，被他人持有且未超时则返回冲突信息。"""
        async with async_db_session.begin() as db:
            ts = await db.get(AnnotationTimeSeriesModel, series_id)
            if not ts or ts.is_deleted:
                raise CustomException(
                    msg=f"时间序列不存在: {series_id}", code=404, status_code=404
                )
            from datetime import datetime, timedelta

            if ts.locked_by and ts.locked_at:
                if datetime.utcnow() - ts.locked_at > timedelta(minutes=5):
                    ts.locked_by = None
                    ts.locked_at = None
            if ts.locked_by and ts.locked_by != user_id:
                return {"locked": True, "locked_by": ts.locked_by}
            ts.locked_by = user_id
            ts.locked_at = datetime.utcnow()
            return {"locked": False, "locked_by": user_id}

    @classmethod
    async def unlock_time_series(cls, series_id: int, user_id: int) -> None:
        """解锁序列，仅锁持有者可解除。"""
        async with async_db_session.begin() as db:
            ts = await db.get(AnnotationTimeSeriesModel, series_id)
            if ts and not ts.is_deleted and ts.locked_by == user_id:
                ts.locked_by = None
                ts.locked_at = None

    @classmethod
    def series_out(cls, ts: AnnotationTimeSeriesModel) -> dict:
        """时间序列行 → 输出 dict（status 序列化为字符串）。"""
        return {
            "id": ts.id,
            "dataset_id": ts.dataset_id,
            "name": ts.name,
            "object_key": ts.object_key,
            "time_column": ts.time_column,
            "value_columns": ts.value_columns,
            "row_count": ts.row_count,
            "time_unit": ts.time_unit,
            "start_time": ts.start_time,
            "end_time": ts.end_time,
            "size_bytes": ts.size_bytes,
            "status": ts.status.value if hasattr(ts.status, "value") else ts.status,
            "locked_by": ts.locked_by,
            "annotation_count": ts.annotation_count,
        }
