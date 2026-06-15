from unittest.mock import AsyncMock, patch

import pytest

from models.ct_monitor_log import CtMonitorLogIngestRequest, CtMonitorLogSearchRequest
from models.user_postgres import UserResponse
from routes.ct_monitor_internal import ingest_ct_monitor_logs_internal
from routes.ct_monitor_logs import get_ct_monitor_log_filters, search_ct_monitor_logs


def _user(**overrides):
    data = {
        "id": "user-1",
        "username": "user",
        "email": "user@example.com",
        "is_active": True,
        "is_superuser": False,
        "roles": [],
        "program_permissions": {"prog1": "analyst", "prog2": "manager"},
    }
    data.update(overrides)
    return UserResponse(**data)


@pytest.mark.asyncio
async def test_internal_ingest_delegates_to_repository():
    request = CtMonitorLogIngestRequest(
        logs=[
            {
                "program_id": "11111111-1111-1111-1111-111111111111",
                "event_type": "typosquat_alert",
                "outcome": "published",
                "domain": "examp1e.com",
                "details": {"source": "test"},
            }
        ]
    )
    with patch(
        "routes.ct_monitor_internal.CtMonitorLogsRepository.insert_logs",
        new_callable=AsyncMock,
    ) as insert_logs:
        insert_logs.return_value = {"inserted_count": 1, "error_count": 0, "errors": []}
        response = await ingest_ct_monitor_logs_internal(request, _user(is_superuser=True))

    assert response["status"] == "success"
    assert response["data"]["inserted_count"] == 1
    insert_logs.assert_awaited_once_with(request.logs)


@pytest.mark.asyncio
async def test_search_intersects_requested_programs_with_user_access():
    request = CtMonitorLogSearchRequest(program=["prog1", "nope"], page=2, page_size=10)
    with patch(
        "routes.ct_monitor_logs.CtMonitorLogsRepository.search_logs_typed",
        new_callable=AsyncMock,
    ) as search:
        search.return_value = {"items": [{"id": "log-1"}], "total_count": 11}
        response = await search_ct_monitor_logs(request, _user())

    assert response["pagination"]["current_page"] == 2
    assert response["pagination"]["total_pages"] == 2
    search.assert_awaited_once()
    assert search.await_args.kwargs["programs"] == ["prog1"]
    assert search.await_args.kwargs["limit"] == 10
    assert search.await_args.kwargs["skip"] == 10


@pytest.mark.asyncio
async def test_search_user_without_access_returns_empty_without_query():
    request = CtMonitorLogSearchRequest(page=1, page_size=25)
    with patch(
        "routes.ct_monitor_logs.CtMonitorLogsRepository.search_logs_typed",
        new_callable=AsyncMock,
    ) as search:
        response = await search_ct_monitor_logs(request, _user(program_permissions={}))

    assert response["items"] == []
    assert response["pagination"]["total_items"] == 0
    search.assert_not_awaited()


@pytest.mark.asyncio
async def test_filter_values_are_scoped_to_user_access():
    with patch(
        "routes.ct_monitor_logs.CtMonitorLogsRepository.get_filter_values",
        new_callable=AsyncMock,
    ) as get_filter_values:
        get_filter_values.return_value = {
            "programs": ["prog1"],
            "match_types": ["similarity"],
            "priorities": ["high"],
        }
        response = await get_ct_monitor_log_filters(_user())

    assert response["programs"] == ["prog1"]
    get_filter_values.assert_awaited_once_with(programs=["prog1", "prog2"])


@pytest.mark.asyncio
async def test_filter_values_user_without_access_returns_empty_without_query():
    with patch(
        "routes.ct_monitor_logs.CtMonitorLogsRepository.get_filter_values",
        new_callable=AsyncMock,
    ) as get_filter_values:
        response = await get_ct_monitor_log_filters(_user(program_permissions={}))

    assert response == {"programs": [], "match_types": [], "priorities": []}
    get_filter_values.assert_not_awaited()
