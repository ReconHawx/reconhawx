"""Route-level tests for scope pattern sanitization on program writes.

These cover the bug where `PUT /programs/{name}` silently accepted malformed
structured scope patterns (e.g. `.*h3x.it`) that later caused every asset
POST to be marked out-of-scope. After the fix, invalid rows are dropped on
write and reported back to the client via `scope_warnings`.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.models.user_postgres import UserResponse


def _make_user(
    *,
    is_superuser: bool = False,
    roles: list[str] | None = None,
    program_permissions: dict | list | None = None,
) -> UserResponse:
    return UserResponse(
        id="test-user-id",
        username="testuser",
        email="test@example.com",
        is_active=True,
        is_superuser=is_superuser,
        roles=roles or ["user"],
        program_permissions=program_permissions or {},
    )


@pytest.fixture
def mock_user_superuser():
    return _make_user(is_superuser=True)


class TestUpdateProgramScopeSanitize:
    """Tests for PUT /programs/{name}."""

    @patch(
        "app.routes.programs.ProgramRepository.update_program",
        new_callable=AsyncMock,
    )
    @patch(
        "app.routes.programs.ProgramRepository.get_program_by_name",
        new_callable=AsyncMock,
    )
    @pytest.mark.asyncio
    async def test_put_drops_invalid_patterns_and_reports_warnings(
        self,
        mock_get_program,
        mock_update_program,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        """Invalid structured patterns are dropped; valid ones persist."""
        mock_get_program.return_value = {
            "id": "00000000-0000-0000-0000-000000000001",
            "name": "reconhawx",
            "scope_domains": [],
            "out_of_scope_domains": [],
        }
        mock_update_program.return_value = True

        response = await client.put(
            "/programs/reconhawx?overwrite=true",
            json={
                "scope_domains": [
                    {"pattern": "reconhawx.io", "wildcard": True},
                    {"pattern": "*.api.reconhawx.com", "wildcard": True},
                    {"pattern": ".*h3x.it", "wildcard": True},
                ],
                "out_of_scope_domains": [
                    {"pattern": "internal.reconhawx.io", "wildcard": False},
                    {"pattern": ".*admin.reconhawx.io", "wildcard": True},
                ],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

        assert "scope_warnings" in data
        warnings = data["scope_warnings"]
        assert warnings["ignored_in_scope"] == [
            {"pattern": ".*h3x.it", "reason": "invalid label in pattern: '*h3x'"}
        ]
        assert warnings["ignored_out_of_scope"] == [
            {
                "pattern": ".*admin.reconhawx.io",
                "reason": "invalid label in pattern: '*admin'",
            }
        ]

        mock_update_program.assert_awaited_once()
        _pid, update_payload = mock_update_program.await_args.args
        assert update_payload["scope_domains"] == [
            {"pattern": "reconhawx.io", "wildcard": True},
            {"pattern": "*.api.reconhawx.com", "wildcard": True},
        ]
        assert update_payload["out_of_scope_domains"] == [
            {"pattern": "internal.reconhawx.io", "wildcard": False},
        ]

    @patch(
        "app.routes.programs.ProgramRepository.update_program",
        new_callable=AsyncMock,
    )
    @patch(
        "app.routes.programs.ProgramRepository.get_program_by_name",
        new_callable=AsyncMock,
    )
    @pytest.mark.asyncio
    async def test_put_cleans_legacy_bad_rows_from_existing_program(
        self,
        mock_get_program,
        mock_update_program,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        """With overwrite=False the merge path sanitizes the merged result too,
        so pre-existing malformed rows from the DB are dropped on save."""
        mock_get_program.return_value = {
            "id": "00000000-0000-0000-0000-000000000002",
            "name": "reconhawx",
            "scope_domains": [
                {"pattern": ".*h3x.it", "wildcard": True},
                {"pattern": "reconhawx.io", "wildcard": True},
            ],
            "out_of_scope_domains": [],
        }
        mock_update_program.return_value = True

        response = await client.put(
            "/programs/reconhawx",
            json={
                "scope_domains": [
                    {"pattern": "*.api.reconhawx.com", "wildcard": True},
                ],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        warnings = data.get("scope_warnings", {})
        assert "ignored_in_scope" in warnings
        assert any(
            w["pattern"] == ".*h3x.it" for w in warnings["ignored_in_scope"]
        )

        mock_update_program.assert_awaited_once()
        _pid, update_payload = mock_update_program.await_args.args
        patterns = [row["pattern"] for row in update_payload["scope_domains"]]
        assert "reconhawx.io" in patterns
        assert "*.api.reconhawx.com" in patterns
        assert ".*h3x.it" not in patterns

    @patch(
        "app.routes.programs.ProgramRepository.update_program",
        new_callable=AsyncMock,
    )
    @patch(
        "app.routes.programs.ProgramRepository.get_program_by_name",
        new_callable=AsyncMock,
    )
    @pytest.mark.asyncio
    async def test_put_without_warnings_omits_field(
        self,
        mock_get_program,
        mock_update_program,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        """When all patterns are valid, the response has no scope_warnings key."""
        mock_get_program.return_value = {
            "id": "00000000-0000-0000-0000-000000000003",
            "name": "reconhawx",
            "scope_domains": [],
            "out_of_scope_domains": [],
        }
        mock_update_program.return_value = True

        response = await client.put(
            "/programs/reconhawx?overwrite=true",
            json={
                "scope_domains": [{"pattern": "reconhawx.io", "wildcard": True}],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "scope_warnings" not in data


class TestCreateProgramScopeSanitize:
    """Tests for POST /programs."""

    @patch(
        "app.routes.programs.ProgramRepository.create_program",
        new_callable=AsyncMock,
    )
    @pytest.mark.asyncio
    async def test_post_drops_invalid_patterns_and_reports_warnings(
        self,
        mock_create_program,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        """POST mirrors PUT behavior: bad rows dropped, returned as warnings."""
        mock_create_program.return_value = "00000000-0000-0000-0000-000000000099"

        response = await client.post(
            "/programs",
            json={
                "name": "reconhawx",
                "scope_domains": [
                    {"pattern": "reconhawx.io", "wildcard": True},
                    {"pattern": ".*h3x.it", "wildcard": True},
                ],
                "out_of_scope_domains": [],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["id"] == "00000000-0000-0000-0000-000000000099"
        assert "scope_warnings" in data
        assert data["scope_warnings"]["ignored_in_scope"][0]["pattern"] == ".*h3x.it"

        mock_create_program.assert_awaited_once()
        create_payload = mock_create_program.await_args.args[0]
        assert create_payload["scope_domains"] == [
            {"pattern": "reconhawx.io", "wildcard": True},
        ]
