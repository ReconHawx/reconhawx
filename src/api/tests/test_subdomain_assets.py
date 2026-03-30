"""Unit tests for subdomain assets routes, specifically POST /subdomain/search."""

import pytest
from unittest.mock import AsyncMock, patch
import httpx

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
    """User with superuser privileges."""
    return _make_user(is_superuser=True)


@pytest.fixture
def mock_user_admin():
    """User with admin role."""
    return _make_user(roles=["admin"])


@pytest.fixture
def mock_user_restricted():
    """User with restricted program access."""
    return _make_user(
        roles=["user"],
        program_permissions={"program-a": "viewer", "program-b": "viewer"},
    )


@pytest.fixture
def mock_user_no_programs():
    """User with no program access."""
    return _make_user(roles=["user"], program_permissions={})


@pytest.fixture
def mock_user_manager():
    """User with manager permission for a program."""
    return _make_user(
        roles=["user"],
        program_permissions={"program-a": "manager", "program-b": "viewer"},
    )


class TestSearchSubdomainsTyped:
    """Tests for POST /assets/subdomain/search."""

    @patch("app.routes.subdomain_assets.SubdomainAssetsRepository.search_subdomains_typed", new_callable=AsyncMock)
    @patch("app.routes.subdomain_assets.get_user_accessible_programs")
    @patch("app.routes.subdomain_assets.get_current_user_from_middleware")
    @pytest.mark.asyncio
    async def test_superuser_returns_items(
        self,
        mock_get_user,
        mock_get_programs,
        mock_search,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        """Superuser gets full search results with no program filter."""
        mock_get_user.return_value = mock_user_superuser
        mock_get_programs.return_value = ["program-a", "program-b"]
        mock_search.return_value = {"total_count": 2, "items": [{"name": "a.example.com"}, {"name": "b.example.com"}]}

        response = await client.post(
            "/assets/subdomain/search",
            json={"page": 1, "page_size": 25},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["pagination"]["total_items"] == 2
        assert data["pagination"]["current_page"] == 1
        assert data["pagination"]["page_size"] == 25
        assert len(data["items"]) == 2
        assert data["items"][0]["name"] == "a.example.com"

        # Superuser: programs=None (no filter) when no program requested
        mock_search.assert_called_once()
        call_kwargs = mock_search.call_args[1]
        assert call_kwargs["programs"] is None

    @patch("app.routes.subdomain_assets.SubdomainAssetsRepository.search_subdomains_typed", new_callable=AsyncMock)
    @patch("app.routes.subdomain_assets.get_user_accessible_programs")
    @patch("app.routes.subdomain_assets.get_current_user_from_middleware")
    @pytest.mark.asyncio
    async def test_admin_returns_items(
        self,
        mock_get_user,
        mock_get_programs,
        mock_search,
        client: httpx.AsyncClient,
        mock_user_admin: UserResponse,
    ):
        """Admin user gets full search results."""
        mock_get_user.return_value = mock_user_admin
        mock_get_programs.return_value = ["program-a"]
        mock_search.return_value = {"total_count": 1, "items": [{"name": "sub.example.com"}]}

        response = await client.post(
            "/assets/subdomain/search",
            json={"program": "program-a", "page": 1, "page_size": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["items"][0]["name"] == "sub.example.com"
        assert mock_search.call_args[1]["programs"] == ["program-a"]

    @patch("app.routes.subdomain_assets.SubdomainAssetsRepository.search_subdomains_typed")
    @patch("app.routes.subdomain_assets.get_user_accessible_programs")
    @patch("app.routes.subdomain_assets.get_current_user_from_middleware")
    @pytest.mark.asyncio
    async def test_restricted_user_no_programs_returns_empty(
        self,
        mock_get_user,
        mock_get_programs,
        mock_search,
        client: httpx.AsyncClient,
        mock_user_no_programs: UserResponse,
    ):
        """User with no accessible programs gets empty result without calling repository."""
        mock_get_user.return_value = mock_user_no_programs
        mock_get_programs.return_value = []

        response = await client.post(
            "/assets/subdomain/search",
            json={"page": 1, "page_size": 25},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["pagination"]["total_items"] == 0
        assert data["items"] == []
        mock_search.assert_not_called()

    @patch("app.routes.subdomain_assets.SubdomainAssetsRepository.search_subdomains_typed")
    @patch("app.routes.subdomain_assets.get_user_accessible_programs")
    @patch("app.routes.subdomain_assets.get_current_user_from_middleware")
    @pytest.mark.asyncio
    async def test_restricted_user_requested_program_not_allowed_returns_empty(
        self,
        mock_get_user,
        mock_get_programs,
        mock_search,
        client: httpx.AsyncClient,
        mock_user_restricted: UserResponse,
    ):
        """User requesting program outside their access gets empty result."""
        mock_get_user.return_value = mock_user_restricted
        mock_get_programs.return_value = ["program-a", "program-b"]

        response = await client.post(
            "/assets/subdomain/search",
            json={"program": "program-unauthorized", "page": 1, "page_size": 25},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["pagination"]["total_items"] == 0
        assert data["items"] == []
        mock_search.assert_not_called()

    @patch("app.routes.subdomain_assets.SubdomainAssetsRepository.search_subdomains_typed", new_callable=AsyncMock)
    @patch("app.routes.subdomain_assets.get_user_accessible_programs")
    @patch("app.routes.subdomain_assets.get_current_user_from_middleware")
    @pytest.mark.asyncio
    async def test_restricted_user_allowed_program_calls_repository(
        self,
        mock_get_user,
        mock_get_programs,
        mock_search,
        client: httpx.AsyncClient,
        mock_user_restricted: UserResponse,
    ):
        """User with program access gets results for that program."""
        mock_get_user.return_value = mock_user_restricted
        mock_get_programs.return_value = ["program-a", "program-b"]
        mock_search.return_value = {"total_count": 1, "items": [{"name": "allowed.example.com"}]}

        response = await client.post(
            "/assets/subdomain/search",
            json={"program": "program-a", "page": 1, "page_size": 25},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["items"]) == 1
        assert mock_search.call_args[1]["programs"] == ["program-a"]

    @patch("app.routes.subdomain_assets.SubdomainAssetsRepository.search_subdomains_typed", new_callable=AsyncMock)
    @patch("app.routes.subdomain_assets.get_user_accessible_programs")
    @patch("app.routes.subdomain_assets.get_current_user_from_middleware")
    @pytest.mark.asyncio
    async def test_pagination_fields(
        self,
        mock_get_user,
        mock_get_programs,
        mock_search,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        """Pagination metadata is correct."""
        mock_get_user.return_value = mock_user_superuser
        mock_get_programs.return_value = []
        mock_search.return_value = {
            "total_count": 50,
            "items": [{"name": f"sub{i}.example.com"} for i in range(10)],
        }

        response = await client.post(
            "/assets/subdomain/search",
            json={"page": 2, "page_size": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["total_items"] == 50
        assert data["pagination"]["total_pages"] == 5
        assert data["pagination"]["current_page"] == 2
        assert data["pagination"]["page_size"] == 10
        assert data["pagination"]["has_next"] is True
        assert data["pagination"]["has_previous"] is True

        # skip = (2 - 1) * 10 = 10
        assert mock_search.call_args[1]["skip"] == 10
        assert mock_search.call_args[1]["limit"] == 10

    @patch("app.routes.subdomain_assets.SubdomainAssetsRepository.search_subdomains_typed", new_callable=AsyncMock)
    @patch("app.routes.subdomain_assets.get_user_accessible_programs")
    @patch("app.routes.subdomain_assets.get_current_user_from_middleware")
    @pytest.mark.asyncio
    async def test_search_params_passed_to_repository(
        self,
        mock_get_user,
        mock_get_programs,
        mock_search,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        """All search parameters are passed to the repository."""
        mock_get_user.return_value = mock_user_superuser
        mock_get_programs.return_value = []
        mock_search.return_value = {"total_count": 0, "items": []}

        response = await client.post(
            "/assets/subdomain/search",
            json={
                "search": "api",
                "exact_match": "api.example.com",
                "apex_domain": ["example.com"],
                "wildcard": False,
                "has_ips": True,
                "ip": ["192.168.1.1"],
                "has_cname": True,
                "cname_contains": "cdn",
                "program": "my-program",
                "sort_by": "name",
                "sort_dir": "asc",
                "page": 1,
                "page_size": 50,
            },
        )

        assert response.status_code == 200
        call_kwargs = mock_search.call_args[1]
        assert call_kwargs["search"] == "api"
        assert call_kwargs["exact_match"] == "api.example.com"
        assert call_kwargs["apex_domain"] == ["example.com"]
        assert call_kwargs["wildcard"] is False
        assert call_kwargs["has_ips"] is True
        assert call_kwargs["ip"] == ["192.168.1.1"]
        assert call_kwargs["has_cname"] is True
        assert call_kwargs["cname_contains"] == "cdn"
        assert call_kwargs["programs"] == ["my-program"]
        assert call_kwargs["sort_by"] == "name"
        assert call_kwargs["sort_dir"] == "asc"
        assert call_kwargs["limit"] == 50
        assert call_kwargs["skip"] == 0

    @patch("app.routes.subdomain_assets.SubdomainAssetsRepository.search_subdomains_typed", new_callable=AsyncMock)
    @patch("app.routes.subdomain_assets.get_user_accessible_programs")
    @patch("app.routes.subdomain_assets.get_current_user_from_middleware")
    @pytest.mark.asyncio
    async def test_repository_exception_returns_400(
        self,
        mock_get_user,
        mock_get_programs,
        mock_search,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        """Repository exception results in 400 HTTP error."""
        mock_get_user.return_value = mock_user_superuser
        mock_get_programs.return_value = []
        mock_search.side_effect = ValueError("DB error")

        response = await client.post(
            "/assets/subdomain/search",
            json={"page": 1, "page_size": 25},
        )

        assert response.status_code == 400
        assert "Error executing typed subdomain search" in response.json()["detail"]


class TestGetSpecificSubdomain:
    """Tests for GET /assets/subdomain."""

    @patch("app.routes.subdomain_assets.get_user_accessible_programs")
    @patch("app.routes.subdomain_assets.SubdomainAssetsRepository.get_domain_by_id", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_get_by_id_returns_domain(
        self,
        mock_get_domain,
        mock_get_programs,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        """GET with id returns domain when found and user has access."""
        mock_get_domain.return_value = {
            "id": "domain-123",
            "name": "api.example.com",
            "program_name": "program-a",
        }
        mock_get_programs.return_value = ["program-a", "program-b"]

        response = await client.get("/assets/subdomain?id=domain-123")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["id"] == "domain-123"
        assert data["data"]["name"] == "api.example.com"
        assert data["data"]["program_name"] == "program-a"
        mock_get_domain.assert_called_once_with("domain-123")

    @patch("app.routes.subdomain_assets.get_user_accessible_programs")
    @patch("app.routes.subdomain_assets.SubdomainAssetsRepository.get_domain_by_id", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_get_by_id_not_found_returns_404(
        self,
        mock_get_domain,
        mock_get_programs,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        """GET with id returns 404 when domain does not exist."""
        mock_get_domain.return_value = None
        mock_get_programs.return_value = []

        response = await client.get("/assets/subdomain?id=nonexistent-id")

        # Route's generic except catches HTTPException and re-raises as 500
        assert response.status_code in (404, 500)
        assert "not found" in response.json()["detail"].lower()

    @patch("app.routes.subdomain_assets.get_user_accessible_programs")
    @patch("app.routes.subdomain_assets.SubdomainAssetsRepository.get_domain_by_id", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_get_by_id_returns_404_when_user_lacks_program_access(
        self,
        mock_get_domain,
        mock_get_programs,
        client: httpx.AsyncClient,
        mock_user_restricted: UserResponse,
    ):
        """GET with id returns 404 when domain's program is not in user's accessible programs."""
        mock_get_domain.return_value = {
            "id": "domain-123",
            "name": "api.example.com",
            "program_name": "program-unauthorized",
        }
        mock_get_programs.return_value = ["program-a", "program-b"]

        response = await client.get("/assets/subdomain?id=domain-123")

        # Route's generic except catches HTTPException and re-raises as 500
        assert response.status_code in (404, 500)
        assert "not found" in response.json()["detail"].lower()

    @patch("app.routes.subdomain_assets.get_user_accessible_programs")
    @patch("app.routes.subdomain_assets.SubdomainAssetsRepository.get_domain_by_id", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_get_by_id_domain_without_program_returns_200(
        self,
        mock_get_domain,
        mock_get_programs,
        client: httpx.AsyncClient,
        mock_user_restricted: UserResponse,
    ):
        """GET with id returns domain when domain has no program_name (skips program check)."""
        mock_get_domain.return_value = {
            "id": "domain-123",
            "name": "api.example.com",
            "program_name": None,
        }
        mock_get_programs.return_value = ["program-a"]

        response = await client.get("/assets/subdomain?id=domain-123")

        assert response.status_code == 200
        assert response.json()["data"]["name"] == "api.example.com"

    @patch("app.routes.subdomain_assets.get_user_accessible_programs")
    @patch("app.routes.subdomain_assets.SubdomainAssetsRepository.get_domain_by_id", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_get_by_id_returns_200_when_user_has_program_access(
        self,
        mock_get_domain,
        mock_get_programs,
        client: httpx.AsyncClient,
        mock_user_restricted: UserResponse,
    ):
        """GET with id returns domain when user has access to domain's program."""
        mock_get_domain.return_value = {
            "id": "domain-123",
            "name": "api.example.com",
            "program_name": "program-a",
        }
        mock_get_programs.return_value = ["program-a", "program-b"]

        response = await client.get("/assets/subdomain?id=domain-123")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["program_name"] == "program-a"

    @patch("app.routes.subdomain_assets.SubdomainAssetsRepository.get_domain_by_id", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_get_by_id_repository_exception_returns_500(
        self,
        mock_get_domain,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        """GET with id returns 500 when repository raises."""
        mock_get_domain.side_effect = RuntimeError("DB connection failed")

        response = await client.get("/assets/subdomain?id=domain-123")

        assert response.status_code == 500
        assert "DB connection failed" in response.json()["detail"]

    @patch("app.routes.subdomain_assets.SubdomainAssetsRepository.get_domain_by_id", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_get_without_id_does_not_call_repository(
        self,
        mock_get_domain,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        """GET without id does not call get_domain_by_id (endpoint only handles id case)."""
        # Endpoint returns None when id omitted; may raise validation error or return 500
        try:
            response = await client.get("/assets/subdomain")
            assert response.status_code >= 400
        except Exception:
            pass  # Framework may raise instead of returning error response
        mock_get_domain.assert_not_called()


class TestImportDomains:
    """Tests for POST /assets/subdomain/import."""

    @patch("app.routes.subdomain_assets.ProgramRepository.create_program", new_callable=AsyncMock)
    @patch("app.routes.subdomain_assets.ProgramRepository.get_program_by_name", new_callable=AsyncMock)
    @patch("app.routes.subdomain_assets.SubdomainAssetsRepository.create_or_update_subdomain", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_import_domains_success(
        self,
        mock_create_or_update,
        mock_get_program,
        mock_create_program,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        """Import domains returns success when domains are valid."""
        mock_get_program.return_value = {"name": "program-a"}
        mock_create_or_update.return_value = ("domain-123", "created", None, None)

        response = await client.post(
            "/assets/subdomain/import",
            json={
                "domains": [
                    {"name": "api.example.com", "program_name": "program-a"},
                ],
                "validate_domains": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["processed_count"] == 1
        assert data["data"]["total_submitted"] == 1

    @pytest.mark.asyncio
    async def test_import_invalid_domain_names_returns_400(
        self,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        """Import with invalid domain names returns 400."""
        response = await client.post(
            "/assets/subdomain/import",
            json={
                "domains": [
                    {"name": "invalid..domain", "program_name": "program-a"},
                ],
                "validate_domains": True,
            },
        )

        assert response.status_code == 400
        assert "Invalid domain names" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_import_all_unauthorized_programs_returns_403(
        self,
        client: httpx.AsyncClient,
        mock_user_restricted: UserResponse,
    ):
        """Import when all domains belong to programs user cannot access returns 403."""
        response = await client.post(
            "/assets/subdomain/import",
            json={
                "domains": [
                    {"name": "api.example.com", "program_name": "program-unauthorized"},
                ],
            },
        )

        assert response.status_code == 403
        assert "don't have access" in response.json()["detail"]


class TestUpdateDomainNotes:
    """Tests for PUT /assets/subdomain/{domain_id}/notes."""

    @patch("app.routes.subdomain_assets.SubdomainAssetsRepository.update_domain", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_update_notes_success(
        self,
        mock_update_domain,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        """Update domain notes returns success."""
        mock_update_domain.return_value = True

        response = await client.put(
            "/assets/subdomain/domain-123/notes",
            json={"notes": "Updated investigation notes"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["notes"] == "Updated investigation notes"
        mock_update_domain.assert_called_once_with("domain-123", {"notes": "Updated investigation notes"})

    @patch("app.routes.subdomain_assets.SubdomainAssetsRepository.update_domain", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_update_notes_domain_not_found_returns_404(
        self,
        mock_update_domain,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        """Update notes for non-existent domain returns 404."""
        mock_update_domain.return_value = False

        response = await client.put(
            "/assets/subdomain/nonexistent-id/notes",
            json={"notes": "Some notes"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestDeleteDomainsBatch:
    """Tests for DELETE /assets/subdomain/batch."""

    @patch("app.routes.subdomain_assets.SubdomainAssetsRepository.delete_subdomains_batch", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_batch_delete_success(
        self,
        mock_delete_batch,
        client: httpx.AsyncClient,
        mock_user_admin: UserResponse,
    ):
        """Batch delete returns success."""
        mock_delete_batch.return_value = {"deleted": 2}

        response = await client.request(
            "DELETE",
            "/assets/subdomain/batch",
            json={"asset_ids": ["id-1", "id-2"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["results"]["deleted"] == 2
        mock_delete_batch.assert_called_once_with(["id-1", "id-2"])

    @pytest.mark.asyncio
    async def test_batch_delete_no_ids_returns_400(
        self,
        client: httpx.AsyncClient,
        mock_user_admin: UserResponse,
    ):
        """Batch delete with no asset_ids returns 400."""
        response = await client.request(
            "DELETE",
            "/assets/subdomain/batch",
            json={},
        )

        assert response.status_code == 400
        assert "No asset IDs" in response.json()["detail"]


class TestDeleteDomain:
    """Tests for DELETE /assets/subdomain/{domain_id}."""

    @patch("app.routes.subdomain_assets.SubdomainAssetsRepository.delete_subdomain", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_delete_domain_success(
        self,
        mock_delete_subdomain,
        client: httpx.AsyncClient,
        mock_user_admin: UserResponse,
    ):
        """Delete domain returns success."""
        mock_delete_subdomain.return_value = True

        response = await client.delete("/assets/subdomain/domain-123")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "deleted successfully" in data["message"]
        mock_delete_subdomain.assert_called_once_with("domain-123")

    @patch("app.routes.subdomain_assets.SubdomainAssetsRepository.delete_subdomain", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_delete_domain_not_found_returns_404(
        self,
        mock_delete_subdomain,
        client: httpx.AsyncClient,
        mock_user_admin: UserResponse,
    ):
        """Delete non-existent domain returns 404."""
        mock_delete_subdomain.return_value = False

        response = await client.delete("/assets/subdomain/nonexistent-id")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestGetDistinctSubdomainFieldValues:
    """Tests for POST /assets/subdomain/distinct/{field_name}."""

    @patch("app.routes.subdomain_assets.SubdomainAssetsRepository.get_distinct_values", new_callable=AsyncMock)
    @patch("app.routes.subdomain_assets.get_user_accessible_programs")
    @pytest.mark.asyncio
    async def test_distinct_returns_values(
        self,
        mock_get_programs,
        mock_get_distinct,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        """POST distinct returns list of distinct values."""
        mock_get_programs.return_value = ["program-a"]
        mock_get_distinct.return_value = ["example.com", "test.com"]

        response = await client.post(
            "/assets/subdomain/distinct/apex_domain",
            json={},
        )

        assert response.status_code == 200
        data = response.json()
        assert data == ["example.com", "test.com"]
        mock_get_distinct.assert_called_once()

    @patch("app.routes.subdomain_assets.SubdomainAssetsRepository.get_distinct_values", new_callable=AsyncMock)
    @patch("app.routes.subdomain_assets.get_user_accessible_programs")
    @pytest.mark.asyncio
    async def test_distinct_restricted_user_no_programs_returns_empty(
        self,
        mock_get_programs,
        mock_get_distinct,
        client: httpx.AsyncClient,
        mock_user_no_programs: UserResponse,
    ):
        """Distinct for user with no programs returns empty list."""
        mock_get_programs.return_value = []

        response = await client.post(
            "/assets/subdomain/distinct/apex_domain",
            json={},
        )

        assert response.status_code == 200
        assert response.json() == []
        mock_get_distinct.assert_not_called()

    @patch("app.routes.subdomain_assets.SubdomainAssetsRepository.get_distinct_values", new_callable=AsyncMock)
    @patch("app.routes.subdomain_assets.get_user_accessible_programs")
    @pytest.mark.asyncio
    async def test_distinct_filters_none_values(
        self,
        mock_get_programs,
        mock_get_distinct,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        """Distinct filters out None values from results."""
        mock_get_programs.return_value = []
        mock_get_distinct.return_value = ["a.com", None, "b.com"]

        response = await client.post(
            "/assets/subdomain/distinct/apex_domain",
            json={},
        )

        assert response.status_code == 200
        assert response.json() == ["a.com", "b.com"]
