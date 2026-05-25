"""Tests for internal runner last-execution routes."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def internal_user():
    from datetime import datetime

    from models.user_postgres import UserResponse

    return UserResponse(
        id="internal-service-test",
        username="internal-service-test",
        email="internal@recon.local",
        is_active=True,
        is_superuser=True,
        is_admin=True,
        program_permissions={},
        roles=["admin"],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def internal_auth_override(internal_user):
    from app.main import app
    from auth.dependencies import require_internal_service_identity

    app.dependency_overrides[require_internal_service_identity] = lambda: internal_user
    yield
    app.dependency_overrides.pop(require_internal_service_identity, None)


@pytest.mark.asyncio
@patch("routes.runner_internal.TaskLastExecutionsRepository.search_eligible_assets", new_callable=AsyncMock)
async def test_eligible_for_task_returns_pagination(
    mock_search, client, internal_auth_override
):
    mock_search.return_value = {
        "items": [{"id": "1", "name": "sub.example.com", "ip": []}],
        "total_count": 1,
    }
    program_id = str(uuid.uuid4())
    response = await client.post(
        "/internal/runner/assets/subdomain/eligible-for-task",
        json={
            "program_id": program_id,
            "task_type": "port_scan",
            "params": {"timeout": 900},
            "threshold_hours": 24,
            "limit": 100,
            "page": 1,
        },
        headers={"Authorization": "Bearer recon_internal_test"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["items"]) == 1
    assert data["pagination"]["total_items"] == 1
    mock_search.assert_awaited_once()


@pytest.mark.asyncio
@patch("routes.runner_internal.TaskLastExecutionsRepository.filter_recent_targets", new_callable=AsyncMock)
async def test_recent_targets(mock_filter, client, internal_auth_override):
    mock_filter.return_value = ["1.2.3.4"]
    program_id = str(uuid.uuid4())
    response = await client.post(
        "/internal/runner/task-executions/recent-targets",
        json={
            "program_id": program_id,
            "task_type": "port_scan",
            "params": {},
            "threshold_hours": 24,
            "targets": ["1.2.3.4", "8.8.8.8"],
        },
        headers={"Authorization": "Bearer recon_internal_test"},
    )
    assert response.status_code == 200
    assert response.json()["recent_targets"] == ["1.2.3.4"]
