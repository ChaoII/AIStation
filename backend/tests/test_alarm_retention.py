"""告警记录：SQL 分页 + TTL 清理回归测试。"""
import asyncio


def test_record_list_uses_sql_pagination(test_client, auth_headers):
    """列表接口返回 CRUDBase.page 结构（total/items 由 SQL 侧计算）。"""
    resp = test_client.get(
        "/api/v1/video/alarm/record/list?page_no=1&page_size=5", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert {"page_no", "page_size", "total", "has_next", "items"} <= set(data)
    assert data["page_no"] == 1
    assert data["page_size"] == 5
    assert isinstance(data["items"], list)
    assert len(data["items"]) <= 5


def test_realtime_alarms_is_bounded(test_client, auth_headers):
    """实时告警返回列表且长度不超过 100（SQL LIMIT）。"""
    resp = test_client.get("/api/v1/video/alarm/record/realtime", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["data"]) <= 100


def test_purge_guard_and_execution():
    """retention_days<=0 不删除；正常配置可执行且返回非负行数。"""
    from app.api.v1.module_video.alarm.retention import purge_old_alarm_records

    assert asyncio.run(purge_old_alarm_records(0)) == 0
    assert asyncio.run(purge_old_alarm_records(-1)) == 0
    assert asyncio.run(purge_old_alarm_records(90)) >= 0
