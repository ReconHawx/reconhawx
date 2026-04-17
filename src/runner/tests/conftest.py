"""Pytest path setup and shared fixtures for runner Tier-1 task tests.

Tests live at ``src/runner/tests/`` (outside ``app/``) so they are not baked
into the runner Docker image. This conftest adds ``src/runner/app`` to
``sys.path`` so test modules can ``import recon_tasks`` etc. as if they were
running from the app root.
"""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path
from typing import Callable

import pytest

_app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)


_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_RESOLVERS_FIXTURE = _FIXTURES_DIR / "resolvers.txt"


@pytest.fixture(autouse=True, scope="session")
def _freeze_random() -> None:
    """Seed ``random`` once per session so tasks that pick random resolvers
    produce deterministic commands in assertions."""
    random.seed(0)


@pytest.fixture(autouse=True)
def _stub_parameter_manager(monkeypatch) -> None:
    """Replace ``recon_tasks.base.parameter_manager`` accessors so tasks that
    read timeouts / chunk sizes at unit scope don't hit the API manifest
    loader."""
    import recon_tasks.base as base

    monkeypatch.setattr(base.parameter_manager, "get_timeout", lambda name: 300)
    monkeypatch.setattr(base.parameter_manager, "get_chunk_size", lambda name: 10)
    monkeypatch.setattr(
        base.parameter_manager, "get_last_execution_threshold", lambda name: 24
    )


@pytest.fixture
def fixture_path() -> Path:
    """Return the path to ``tests/fixtures``."""
    return _FIXTURES_DIR


@pytest.fixture
def load_fixture(fixture_path: Path) -> Callable[[str], str]:
    """Return a helper that loads a fixture file as text.

    Usage:
        content = load_fixture("resolve_domain/dnsx_success.json")
    """

    def _load(relative: str) -> str:
        path = fixture_path / relative
        with open(path, encoding="utf-8") as f:
            return f.read()

    return _load


@pytest.fixture
def patched_resolvers(monkeypatch, tmp_path: Path) -> Path:
    """Give tasks that ``open("files/resolvers.txt")`` a deterministic file.

    Copies the shared ``tests/fixtures/resolvers.txt`` into ``tmp_path/files/``
    and ``chdir``'s into ``tmp_path`` so the relative open succeeds.
    """
    files_dir = tmp_path / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    target = files_dir / "resolvers.txt"
    target.write_text(_RESOLVERS_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return target
