"""Resolve Program rows from runner/API payloads (program_id)."""

from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from sqlalchemy.orm import Session

from models.postgres import Program


def resolve_program_from_payload(db: Session, data: Dict[str, Any]) -> Program:
    """Require ``program_id`` (UUID string) and return the Program row."""
    pid = data.get("program_id")
    if not pid:
        raise ValueError("program_id is required")
    try:
        uid = UUID(str(pid))
    except ValueError as e:
        raise ValueError(f"Invalid program_id: {pid!r}") from e
    program = db.query(Program).filter(Program.id == uid).first()
    if not program:
        raise ValueError(f"Program not found for id {pid!r}")
    # Keep display name on payload for event payloads / logs
    if not data.get("program_name"):
        data["program_name"] = program.name
    return program
