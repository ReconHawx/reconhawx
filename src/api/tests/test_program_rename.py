"""Tests for renaming a program via PUT /programs/{program_name}."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy.exc import IntegrityError

from app.models.user_postgres import UserResponse

_MINIMAL_PROGRAM = {
    "id": "00000000-0000-0000-0000-000000000001",
    "name": "oldname",
    "scope_domains": [],
    "out_of_scope_domains": [],
    "typosquat_filtering_settings": None,
    "ct_monitoring_enabled": False,
}


class TestProgramRename:
    @patch(
        "app.routes.programs.ProgramRepository.update_program",
        new_callable=AsyncMock,
    )
    @patch(
        "app.routes.programs.ProgramRepository.get_program_by_name",
        new_callable=AsyncMock,
    )
    @pytest.mark.asyncio
    async def test_put_rename_success(
        self,
        mock_get_program,
        mock_update_program,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        """Superuser can rename; response includes data.name."""

        async def _get_by_name(name: str):
            if name == "oldname":
                return dict(_MINIMAL_PROGRAM)
            if name == "newname":
                return None
            return None

        mock_get_program.side_effect = _get_by_name
        mock_update_program.return_value = True

        response = await client.put(
            "/programs/oldname",
            json={"name": "newname"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data.get("data") == {"name": "newname"}
        assert "newname" in data["message"]

        mock_update_program.assert_awaited_once()
        _pid, payload = mock_update_program.await_args.args
        assert payload["name"] == "newname"

    @patch(
        "app.routes.programs.ProgramRepository.get_program_by_name",
        new_callable=AsyncMock,
    )
    @pytest.mark.asyncio
    async def test_put_rename_conflict_duplicate_name(
        self,
        mock_get_program,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        """409 when target name is already used by another program."""

        async def _get_by_name(name: str):
            if name == "oldname":
                return dict(_MINIMAL_PROGRAM)
            if name == "taken":
                return {
                    "id": "00000000-0000-0000-0000-000000000099",
                    "name": "taken",
                }
            return None

        mock_get_program.side_effect = _get_by_name

        response = await client.put(
            "/programs/oldname",
            json={"name": "taken"},
        )

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_put_rename_forbidden_non_manager(
        self,
        client: httpx.AsyncClient,
        mock_user_restricted: UserResponse,
    ):
        """403 when user lacks manager access to the program."""

        response = await client.put(
            "/programs/program-a",
            json={"name": "new-name"},
        )

        assert response.status_code == 403
        assert "Manager" in response.json()["detail"]

    @patch(
        "app.routes.programs.ProgramRepository.update_program",
        new_callable=AsyncMock,
    )
    @patch(
        "app.routes.programs.ProgramRepository.get_program_by_name",
        new_callable=AsyncMock,
    )
    @pytest.mark.asyncio
    async def test_put_rename_integrity_error_returns_409(
        self,
        mock_get_program,
        mock_update_program,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        """Race on unique constraint maps to 409."""

        async def _get_by_name(name: str):
            if name == "oldname":
                return dict(_MINIMAL_PROGRAM)
            if name == "newname":
                return None
            return None

        mock_get_program.side_effect = _get_by_name
        mock_update_program.side_effect = IntegrityError(
            "stmt", None, Exception("duplicate key")
        )

        response = await client.put(
            "/programs/oldname",
            json={"name": "newname"},
        )

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"].lower()
