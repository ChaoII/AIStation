"""AI 报告增强：关联应用/会话（app_id/session_id）落库与列表/详情返回。"""
import asyncio

from app.plugin.module_ai.report.service import AiReportService


def _cleanup(test_client, auth_headers, report_id: int) -> None:
    test_client.request(
        "DELETE",
        "/api/v1/ai/report/delete",
        json=[report_id],
        headers=auth_headers,
    )


def test_report_with_app_id_visible_in_list_and_detail(test_client, auth_headers):
    """带 app_id/session_id 创建报告后，列表与详情均应回显关联 ID。"""
    created = asyncio.run(
        AiReportService.create(
            "关联报告",
            "# 关联报告",
            {"topic": "t"},
            1,
            app_id=7,
            session_id=9,
        )
    )
    rid = created["id"]

    try:
        lst = test_client.get("/api/v1/ai/report/list", headers=auth_headers).json()["data"]
        row = next(x for x in lst if x["id"] == rid)
        assert row["app_id"] == 7
        assert row["session_id"] == 9

        detail = test_client.get(
            f"/api/v1/ai/report/detail/{rid}", headers=auth_headers
        ).json()["data"]
        assert detail["app_id"] == 7
        assert detail["session_id"] == 9
        assert "# 关联报告" in detail["content"]
    finally:
        _cleanup(test_client, auth_headers, rid)


def test_existing_create_without_linked_ids_still_works(test_client, auth_headers):
    """不传 app_id/session_id 的既有调用保持可用，字段为 None。"""
    created = asyncio.run(
        AiReportService.create("普通报告", "# 普通报告", {"topic": "t"}, 1)
    )
    rid = created["id"]

    try:
        lst = test_client.get("/api/v1/ai/report/list", headers=auth_headers).json()["data"]
        row = next(x for x in lst if x["id"] == rid)
        assert row["title"] == "普通报告"
        assert row["app_id"] is None
        assert row["session_id"] is None
    finally:
        _cleanup(test_client, auth_headers, rid)
