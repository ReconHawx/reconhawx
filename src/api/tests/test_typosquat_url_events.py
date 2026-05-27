"""Tests for typosquat URL create route event publishing."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

PROGRAM_ID = "00000000-0000-0000-0000-000000000099"

CREATE_PAYLOAD = {
    "url": "https://examp1e.com/login",
    "hostname": "examp1e.com",
    "path": "/login",
    "scheme": "https",
    "program_id": PROGRAM_ID,
    "typosquat_domain": "examp1e.com",
}

EVENT_DATA = {
    "event": "finding.created",
    "finding_type": "typosquat_url",
    "record_id": "url-id-1",
    "name": "https://examp1e.com/login",
    "url": "https://examp1e.com/login",
    "program_name": "test-program",
    "program_id": PROGRAM_ID,
}


class TestCreateTyposquatUrlEvents:
    @patch("app.routes.typosquat_findings.publisher.publish_immediate", new_callable=AsyncMock)
    @patch(
        "app.routes.typosquat_findings.TyposquatFindingsRepository.create_or_update_typosquat_url",
        new_callable=AsyncMock,
    )
    @pytest.mark.asyncio
    async def test_publishes_event_on_create(
        self,
        mock_create_or_update,
        mock_publish_immediate,
        client: httpx.AsyncClient,
        mock_user_superuser,
    ):
        mock_create_or_update.return_value = ("url-id-1", True, "domain-id-1", EVENT_DATA)

        with patch(
            "app.routes.typosquat_findings.TyposquatFindingsRepository.calculate_single_typosquat_risk_score",
            new_callable=AsyncMock,
            return_value={"status": "success", "risk_score": 10},
        ):
            response = await client.post("/findings/typosquat-url", json=CREATE_PAYLOAD)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["was_created"] is True

        mock_publish_immediate.assert_awaited_once_with(
            "events.findings.typosquat_url.created",
            EVENT_DATA,
        )

    @patch("app.routes.typosquat_findings.publisher.publish_immediate", new_callable=AsyncMock)
    @patch(
        "app.routes.typosquat_findings.TyposquatFindingsRepository.create_or_update_typosquat_url",
        new_callable=AsyncMock,
    )
    @pytest.mark.asyncio
    async def test_does_not_publish_on_update(
        self,
        mock_create_or_update,
        mock_publish_immediate,
        client: httpx.AsyncClient,
        mock_user_superuser,
    ):
        mock_create_or_update.return_value = ("url-id-1", False, "domain-id-1", None)

        with patch(
            "app.routes.typosquat_findings.TyposquatFindingsRepository.calculate_single_typosquat_risk_score",
            new_callable=AsyncMock,
            return_value={"status": "success", "risk_score": 10},
        ):
            response = await client.post("/findings/typosquat-url", json=CREATE_PAYLOAD)

        assert response.status_code == 200
        assert response.json()["was_created"] is False
        mock_publish_immediate.assert_not_awaited()

    @patch("app.routes.typosquat_findings.publisher.publish_immediate", new_callable=AsyncMock)
    @patch(
        "app.routes.typosquat_findings.TyposquatFindingsRepository.create_or_update_typosquat_url",
        new_callable=AsyncMock,
    )
    @pytest.mark.asyncio
    async def test_does_not_publish_when_filtered(
        self,
        mock_create_or_update,
        mock_publish_immediate,
        client: httpx.AsyncClient,
        mock_user_superuser,
    ):
        mock_create_or_update.return_value = (None, False, None, None)

        response = await client.post("/findings/typosquat-url", json=CREATE_PAYLOAD)

        assert response.status_code == 200
        assert response.json()["status"] == "filtered"
        mock_publish_immediate.assert_not_awaited()
