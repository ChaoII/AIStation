"""时间序列上传 service 单测：CSV 探测（时间/数值列、行数、时间单位、范围）、
扩展名/大小/行数上限校验、RustFS 上传、计数递增与失败清理。

仅 mock s3_client 与 db 会话，验证 TimeSeriesService.upload_time_series 与
_service 内 `_probe_csv` 的核心行为。
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1.module_annotation.dataset import time_series_service
from app.api.v1.module_annotation.dataset.time_series_service import TimeSeriesService
from app.core.exceptions import CustomException


def _make_file(name, content, size=None):
    """构造一个模拟 UploadFile。"""
    f = AsyncMock()
    f.filename = name
    f.size = size if size is not None else len(content)
    f.read = AsyncMock(return_value=content)
    return f


def _make_db(dataset=None):
    """构造一个模拟 async db 会话。"""
    db = AsyncMock()
    db.get = AsyncMock(return_value=dataset)
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


def _dataset():
    ds = MagicMock()
    ds.id = 7
    ds.is_deleted = False
    ds.time_series_count = 0
    return ds


def _csv(header, rows, delim=","):
    """构造 CSV 字节内容（首行为表头）。"""
    lines = [delim.join(str(c) for c in header)]
    for r in rows:
        lines.append(delim.join(str(c) for c in r))
    return ("\n".join(lines) + "\n").encode("utf-8")


def _run(coro):
    return asyncio.run(coro)


def test_probe_csv_detects_columns_and_stats():
    # 正常探测：时间列（含关键字首列）、数值列、行数、时间单位 s、范围。
    content = _csv(
        ["timestamp", "value", "temperature"],
        [[1.0, 10.0, 5.0], [2.0, 20.0, 6.0], [3.5, 30.0, 7.5]],
    )
    info = time_series_service._probe_csv(content)
    assert info["time_column"] == "timestamp"
    assert info["value_columns"] == ["value", "temperature"]
    assert info["row_count"] == 3
    assert info["time_unit"] == "s"
    assert info["start_time"] == 1.0
    assert info["end_time"] == 3.5


def test_probe_csv_time_unit_ms_for_large_timestamps():
    # 时间值绝对值 > 1e12 时，时间单位判为 ms。
    content = _csv(
        ["timestamp", "value"],
        [[1700000000000.0, 1.0], [1700000001000.0, 2.0]],
    )
    info = time_series_service._probe_csv(content)
    assert info["time_unit"] == "ms"
    assert info["start_time"] == 1700000000000.0
    assert info["end_time"] == 1700000001000.0


def test_probe_csv_default_first_column_when_no_keyword():
    # 无时间关键字时，默认首列作为时间列。
    content = _csv(["col1", "col2", "col3"], [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    info = time_series_service._probe_csv(content)
    assert info["time_column"] == "col1"
    assert info["value_columns"] == ["col2", "col3"]


def test_probe_csv_keyword_column_wins_over_first():
    # 含时间关键字的第二列应为时间列（优先级高于默认首列）；非数值列不入选数值列。
    content = _csv(["no", "timestamp", "value"], [["a", 1.0, 10.0], ["b", 2.0, 20.0]])
    info = time_series_service._probe_csv(content)
    assert info["time_column"] == "timestamp"
    assert info["value_columns"] == ["value"]


def test_probe_csv_raises_when_no_time_column():
    # 无法解析出有效时间值时，应抛出明确业务错误。
    content = _csv(["label", "value"], [["a", 1.0], ["b", 2.0]])
    with pytest.raises(CustomException) as e:
        time_series_service._probe_csv(content)
    assert "时间" in e.value.msg


def test_probe_csv_raises_when_no_value_columns():
    # 除时间列外无非数值列可解析为 float 时，应抛出明确业务错误。
    content = _csv(["timestamp", "note"], [[1.0, "x"], [2.0, "y"]])
    with pytest.raises(CustomException) as e:
        time_series_service._probe_csv(content)
    assert "数值" in e.value.msg


def test_probe_csv_raises_over_row_limit():
    # 数据行数超过上限（50 万）时应中止并抛出业务错误。
    n = time_series_service.MAX_CSV_ROWS + 1
    content = _csv(["t", "v"], [[i, i * 2] for i in range(n)])
    with pytest.raises(CustomException) as e:
        time_series_service._probe_csv(content)
    assert "行数" in e.value.msg


def test_upload_rejects_non_csv_extension():
    # 白名单外的扩展名应直接拒绝，不写对象也不入库。
    db = _make_db(dataset=_dataset())
    file = _make_file("data.txt", b"t,v\n1,2\n")
    with patch("app.api.v1.module_annotation.dataset.time_series_service.s3_client") as s3:
        with pytest.raises(CustomException) as e:
            _run(TimeSeriesService.upload_time_series(db, 7, file, auth=None))
        assert "扩展名" in e.value.msg or "格式" in e.value.msg
    s3.upload_fileobj.assert_not_called()
    db.add.assert_not_called()


def test_upload_rejects_oversize():
    # 超过 200MB 应拒绝。
    db = _make_db(dataset=_dataset())
    file = _make_file("big.csv", b"x", size=200 * 1024 * 1024 + 1)
    with patch("app.api.v1.module_annotation.dataset.time_series_service.s3_client") as s3:
        with pytest.raises(CustomException):
            _run(TimeSeriesService.upload_time_series(db, 7, file, auth=None))
    s3.upload_fileobj.assert_not_called()


def test_upload_populates_model_and_increments_count():
    # 合法 CSV：应上传对象、写入模型（含元数据）并递增 time_series_count。
    db = _make_db(dataset=_dataset())
    content = _csv(["timestamp", "value"], [[1.0, 10.0], [2.0, 20.0], [3.0, 30.0]])
    file = _make_file("data.csv", content)
    ds = db.get.return_value
    with patch("app.api.v1.module_annotation.dataset.time_series_service.s3_client") as s3:
        ts = _run(TimeSeriesService.upload_time_series(db, 7, file, auth=None))
    assert ts.object_key.startswith("datasets/7/time_series/")
    assert ts.object_key.endswith(".csv")
    assert ts.size_bytes == len(content)
    assert ts.time_column == "timestamp"
    assert ts.value_columns == ["value"]
    assert ts.row_count == 3
    assert ts.time_unit == "s"
    assert ts.start_time == 1.0
    assert ts.end_time == 3.0
    assert ts.name == "data.csv"
    s3.upload_fileobj.assert_called_once()
    uploaded = s3.upload_fileobj.call_args[0][0]
    assert uploaded.getvalue() == content
    db.add.assert_called()
    assert ds.time_series_count == 1


def test_upload_failure_cleans_up_uploaded_object():
    # 入库失败（flush 抛错）时，应删除已上传对象并重新抛错。
    db = _make_db(dataset=_dataset())
    db.flush = AsyncMock(side_effect=RuntimeError("db boom"))
    content = _csv(["timestamp", "value"], [[1.0, 2.0], [3.0, 4.0]])
    file = _make_file("data.csv", content)
    with patch("app.api.v1.module_annotation.dataset.time_series_service.s3_client") as s3:
        with pytest.raises(RuntimeError):
            _run(TimeSeriesService.upload_time_series(db, 7, file, auth=None))
    s3.delete_object.assert_called()
