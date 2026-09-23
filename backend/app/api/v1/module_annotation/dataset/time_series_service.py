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
from datetime import datetime, timedelta
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


def _delimiter_for(ext: str | None) -> str:
    """按扩展名返回 CSV 分隔符：``.tsv`` 用制表符，其余（含未知/None）用逗号。"""
    if ext and ext.lower() == ".tsv":
        return "\t"
    return ","


def _column_is_numeric(rows: list[list[str]], idx: int, max_probe: int = 100) -> bool:
    """探测某一列前若干行（非空）是否都能解析为 float，判断其是否为数值列。

    仅抽样最多 ``max_probe`` 行，避免对每个候选列做全量扫描；任一行解析失败即
    返回 False。全部为空（无可解析值）也返回 False。
    """
    probed = 0
    for row in rows:
        if idx >= len(row):
            continue
        cell = row[idx].strip()
        if not cell:
            continue
        try:
            float(cell)
        except ValueError:
            return False
        probed += 1
        if probed >= max_probe:
            break
    return probed > 0


def _find_time_column(headers: list[str], rows: list[list[str]]) -> tuple[str, int]:
    """识别时间列：在命中时间关键字的候选列集中，优先选择值可解析为 float 的那列；
    若关键字列均不可解析且首列可解析，则回退首列；否则沿用首个关键字列（供下游报错）。"""
    keyword_idx = [
        i for i, header in enumerate(headers)
        if any(k in header.lower() for k in _TIME_KEYWORDS)
    ]
    for idx in keyword_idx:
        if _column_is_numeric(rows, idx):
            return headers[idx], idx
    if headers and _column_is_numeric(rows, 0):
        return headers[0], 0
    if keyword_idx:
        return headers[keyword_idx[0]], keyword_idx[0]
    return headers[0], 0


def _probe_csv(content: bytes, ext: str | None = None) -> dict:
    """探测 CSV 结构，返回 ``{time_column, value_columns, row_count, time_unit,
    start_time, end_time}``。

    逐行（csv reader，按 ``ext`` 适配分隔符）解析：数据行数超上限即中止；
    无有效时间列、无数值列抛业务错误。
    """
    text = _decode_csv(content)
    delimiter = _delimiter_for(ext)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)

    headers: list[str] | None = None
    for row in reader:
        if row and any(cell.strip() for cell in row):
            headers = [c.strip() for c in row]
            break
    if not headers:
        raise CustomException(
            msg="无法识别时间列: 文件为空或缺少表头", code=400, status_code=400
        )

    rows: list[list[str]] = []
    for row in reader:
        if not row or not any(cell.strip() for cell in row):
            continue
        rows.append(row)
        if len(rows) > MAX_CSV_ROWS:
            raise CustomException(
                msg=f"数据行数超过上限（{MAX_CSV_ROWS} 行）: {len(rows)}",
                code=400,
                status_code=400,
            )

    time_column, time_idx = _find_time_column(headers, rows)

    # 数值列候选：除时间列外的其余列（仍保序）
    value_candidates: dict[int, str] = {
        i: headers[i] for i in range(len(headers)) if i != time_idx
    }
    numeric = set(value_candidates.keys())

    times: list[float] = []

    for row in rows:
        # 时间列：取本行时间值（非数值行不参与统计）
        if time_idx < len(row):
            cell = row[time_idx].strip()
            try:
                times.append(float(cell))
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

    start_time = min(times)
    time_unit = "ms" if abs(start_time) > 1e12 else "s"
    return {
        "time_column": time_column,
        "value_columns": value_columns,
        "row_count": len(rows),
        "time_unit": time_unit,
        "start_time": start_time,
        "end_time": max(times),
    }


class TimeSeriesService:

    LOCK_TIMEOUT_MINUTES = 5

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
        probe = _probe_csv(content, ext)

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
            if ts.locked_by and ts.locked_at:
                if datetime.utcnow() - ts.locked_at > timedelta(minutes=cls.LOCK_TIMEOUT_MINUTES):
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
