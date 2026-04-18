"""Pure unit tests for auth program-scoping helpers (no HTTP, no DB)."""

import pytest

from auth.dependencies import (
    check_program_permission,
    filter_by_user_programs,
    get_user_accessible_programs,
    get_user_program_permission_level,
)
from models.user_postgres import UserResponse


def _user(
    *,
    is_superuser: bool = False,
    roles: list | None = None,
    program_permissions: dict | list | None = None,
) -> UserResponse:
    return UserResponse(
        id="u1",
        username="tester",
        email="t@example.com",
        is_active=True,
        is_superuser=is_superuser,
        roles=roles or ["user"],
        program_permissions=program_permissions if program_permissions is not None else {},
    )


class TestGetUserAccessiblePrograms:
    def test_superuser_empty_means_unrestricted(self):
        u = _user(is_superuser=True)
        assert get_user_accessible_programs(u) == []

    def test_admin_role_empty_means_unrestricted(self):
        u = _user(roles=["admin"])
        assert get_user_accessible_programs(u) == []

    def test_dict_permissions_returns_keys(self):
        u = _user(program_permissions={"p1": "analyst", "p2": "manager"})
        assert set(get_user_accessible_programs(u)) == {"p1", "p2"}

    def test_list_permissions_old_format(self):
        u = _user(program_permissions=["a", "b"])
        assert get_user_accessible_programs(u) == ["a", "b"]

    def test_regular_user_empty_dict_no_programs(self):
        u = _user(program_permissions={})
        assert get_user_accessible_programs(u) == []


class TestFilterByUserPrograms:
    def test_superuser_unchanged(self):
        u = _user(is_superuser=True)
        base = {"name": "x", "program_name": {"$in": ["any"]}}
        assert filter_by_user_programs(base, u) == base

    def test_admin_unchanged(self):
        u = _user(roles=["admin"])
        assert filter_by_user_programs({"foo": "bar"}, u) == {"foo": "bar"}

    def test_no_access_forces_empty_in(self):
        u = _user(program_permissions={})
        assert filter_by_user_programs({"name": "x"}, u) == {"program_name": {"$in": []}}

    def test_no_program_filter_enforces_allowed_set(self):
        u = _user(program_permissions={"p1": "analyst", "p2": "viewer"})
        assert filter_by_user_programs({"name": "x"}, u) == {
            "name": "x",
            "program_name": {"$in": ["p1", "p2"]},
        }

    def test_string_program_intersects(self):
        u = _user(program_permissions={"p1": "analyst"})
        assert filter_by_user_programs({"program_name": "p1"}, u) == {
            "program_name": {"$in": ["p1"]},
        }

    def test_string_program_not_allowed(self):
        u = _user(program_permissions={"p1": "analyst"})
        assert filter_by_user_programs({"program_name": "other"}, u) == {
            "program_name": {"$in": []},
        }

    def test_in_operator_intersects(self):
        u = _user(program_permissions={"a": "x", "b": "x", "c": "x"})
        out = filter_by_user_programs({"program_name": {"$in": ["b", "z"]}}, u)
        assert out["program_name"] == {"$in": ["b"]}

    def test_in_operator_no_overlap(self):
        u = _user(program_permissions={"a": "x"})
        out = filter_by_user_programs({"program_name": {"$in": ["z"]}}, u)
        assert out["program_name"] == {"$in": []}

    def test_eq_normalized(self):
        u = _user(program_permissions={"p1": "analyst"})
        out = filter_by_user_programs({"program_name": {"$eq": "p1"}}, u)
        assert out["program_name"] == {"$in": ["p1"]}

    def test_unknown_dict_operator_falls_back_to_full_allowed(self):
        u = _user(program_permissions={"p1": "analyst", "p2": "analyst"})
        out = filter_by_user_programs({"program_name": {"$regex": "x"}}, u)
        assert out["program_name"] == {"$in": ["p1", "p2"]}


class TestCheckProgramPermission:
    def test_superuser_all_levels(self):
        u = _user(is_superuser=True)
        assert check_program_permission(u, "any", "analyst") is True
        assert check_program_permission(u, "any", "manager") is True

    def test_admin_all_levels(self):
        u = _user(roles=["admin"])
        assert check_program_permission(u, "x", "manager") is True

    def test_dict_analyst_vs_manager(self):
        u = _user(program_permissions={"p1": "analyst", "p2": "manager"})
        assert check_program_permission(u, "p1", "analyst") is True
        assert check_program_permission(u, "p1", "manager") is False
        assert check_program_permission(u, "p2", "analyst") is True
        assert check_program_permission(u, "p2", "manager") is True

    def test_list_format_treated_as_analyst_only(self):
        u = _user(program_permissions=["legacy"])
        assert check_program_permission(u, "legacy", "analyst") is True
        assert check_program_permission(u, "legacy", "manager") is False

    def test_unknown_program(self):
        u = _user(program_permissions={"p1": "analyst"})
        assert check_program_permission(u, "missing", "analyst") is False


class TestGetUserProgramPermissionLevel:
    def test_superuser_manager(self):
        u = _user(is_superuser=True)
        assert get_user_program_permission_level(u, "anything") == "manager"

    def test_admin_manager(self):
        u = _user(roles=["admin"])
        assert get_user_program_permission_level(u, "x") == "manager"

    def test_dict_levels(self):
        u = _user(program_permissions={"a": "analyst", "b": "manager"})
        assert get_user_program_permission_level(u, "a") == "analyst"
        assert get_user_program_permission_level(u, "b") == "manager"
        assert get_user_program_permission_level(u, "c") is None

    def test_list_analyst(self):
        u = _user(program_permissions=["z"])
        assert get_user_program_permission_level(u, "z") == "analyst"
        assert get_user_program_permission_level(u, "other") is None
