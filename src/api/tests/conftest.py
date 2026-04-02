"""Pytest configuration and fixtures for API tests."""

import os
import sys
import warnings

warnings.filterwarnings("ignore")

# Disable auth middleware so unit tests can override dependencies
os.environ["DISABLE_AUTH_MIDDLEWARE"] = "true"

# Maintenance middleware would block most routes if enabled from DB/env in tests
os.environ.setdefault("DISABLE_MAINTENANCE_MIDDLEWARE", "true")

# Add src/api and src/api/app so both "app" and "routes" (used in app.main) resolve
_api_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_app_dir = os.path.join(_api_root, "app")
for _path in (_api_root, _app_dir):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import pytest
import httpx
from httpx import ASGITransport
from fastapi import FastAPI

# Import app after path and env are set
from app.main import app

# User fixture names that tests use for auth override
_USER_FIXTURES = (
    "mock_user_superuser",
    "mock_user_admin",
    "mock_user_manager",
    "mock_user_restricted",
    "mock_user_no_programs",
)


def _make_override_user(user):
    """Create a dependency override that returns the given user (accepts Request for FastAPI compatibility)."""

    def _override(request=None):
        return user

    return _override


@pytest.fixture(autouse=True)
def auth_override(request):
    """Set auth dependency override from the user fixture requested by the test."""
    from auth.dependencies import get_current_user_from_middleware, require_admin_or_manager

    for name in _USER_FIXTURES:
        if name in request.fixturenames:
            user = request.getfixturevalue(name)
            app.dependency_overrides[get_current_user_from_middleware] = _make_override_user(user)
            app.dependency_overrides[require_admin_or_manager] = _make_override_user(user)
            break
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client(auth_override):
    """FastAPI test client - depends on auth_override so override is set before client creation."""
    transport = ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")
