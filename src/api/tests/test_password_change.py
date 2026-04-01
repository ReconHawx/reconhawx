"""Tests for forced password change and POST /auth/me/password."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.main import app
from app.models.user_postgres import UserResponse
from auth.dependencies import require_authentication


def _user(**kwargs) -> UserResponse:
    data = {
        "id": "00000000-0000-0000-0000-000000000099",
        "username": "pwuser",
        "email": "pwuser@example.com",
        "is_active": True,
        "is_superuser": False,
        "roles": ["user"],
        "program_permissions": {},
    }
    data.update(kwargs)
    return UserResponse(**data)


@pytest.fixture
def override_auth():
    """Override require_authentication for auth route tests."""
    yield
    app.dependency_overrides.pop(require_authentication, None)


@pytest.mark.asyncio
async def test_change_own_password_success(client: httpx.AsyncClient, override_auth):
    u = _user(must_change_password=True)
    app.dependency_overrides[require_authentication] = lambda: u
    updated = {
        "id": "00000000-0000-0000-0000-000000000099",
        "username": "pwuser",
        "email": "pwuser@example.com",
        "is_active": True,
        "is_superuser": False,
        "roles": ["user"],
        "program_permissions": {},
        "must_change_password": False,
        "created_at": None,
        "last_login": None,
        "updated_at": None,
        "first_name": None,
        "last_name": None,
        "rf_uhash": None,
        "hackerone_api_token": None,
        "hackerone_api_user": None,
        "intigriti_api_token": None,
    }
    with patch(
        "routes.auth.AuthRepository",
    ) as mock_cls:
        mock_cls.return_value.change_own_password = AsyncMock(return_value=updated)
        with patch(
            "middleware.auth.get_current_user",
            new_callable=AsyncMock,
            return_value=u,
        ):
            response = await client.post(
                "/auth/me/password",
                json={"current_password": "oldsecret", "new_password": "newsecret"},
                headers={"Authorization": "Bearer test-token"},
            )
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "pwuser"
    assert body["must_change_password"] is False


@pytest.mark.asyncio
async def test_change_own_password_wrong_current(client: httpx.AsyncClient, override_auth):
    u = _user()
    app.dependency_overrides[require_authentication] = lambda: u
    with patch(
        "routes.auth.AuthRepository",
    ) as mock_cls:
        mock_cls.return_value.change_own_password = AsyncMock(
            side_effect=ValueError("Invalid current password")
        )
        with patch(
            "middleware.auth.get_current_user",
            new_callable=AsyncMock,
            return_value=u,
        ):
            response = await client.post(
                "/auth/me/password",
                json={"current_password": "wrong", "new_password": "newsecret"},
                headers={"Authorization": "Bearer test-token"},
            )
    assert response.status_code == 400
    assert "Invalid current password" in response.text


@pytest.mark.asyncio
async def test_middleware_blocks_when_must_change_password():
    """AuthMiddleware returns 403 for protected paths when flag is set."""
    import middleware.auth as middleware_auth
    from unittest.mock import MagicMock, AsyncMock
    from starlette.requests import Request

    from middleware.auth import AuthMiddleware

    app_inner = MagicMock()

    async def call_next(req):
        return MagicMock(status_code=200)

    mw = AuthMiddleware(app_inner)

    user = _user(must_change_password=True)
    with patch.object(middleware_auth, "get_current_user", new_callable=AsyncMock, return_value=user):
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "path": "/programs",
            "raw_path": b"/programs",
            "root_path": "",
            "scheme": "http",
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "headers": [(b"authorization", b"Bearer faketoken")],
            "query_string": b"",
        }
        req = Request(scope)
        resp = await mw.dispatch(req, call_next)
        assert resp.status_code == 403
        payload = resp.body.decode()
        assert "password_change_required" in payload


@pytest.mark.asyncio
async def test_middleware_allows_change_password_path():
    """AuthMiddleware allows POST /auth/me/password when flag is set."""
    import middleware.auth as middleware_auth
    from unittest.mock import MagicMock, AsyncMock
    from starlette.requests import Request

    from middleware.auth import AuthMiddleware

    app_inner = MagicMock()

    async def call_next(req):
        return MagicMock(status_code=200)

    mw = AuthMiddleware(app_inner)
    user = _user(must_change_password=True)
    with patch.object(middleware_auth, "get_current_user", new_callable=AsyncMock, return_value=user):
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "path": "/auth/me/password",
            "raw_path": b"/auth/me/password",
            "root_path": "",
            "scheme": "http",
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "headers": [(b"authorization", b"Bearer faketoken")],
            "query_string": b"",
        }
        req = Request(scope)
        resp = await mw.dispatch(req, call_next)
        assert resp.status_code == 200
