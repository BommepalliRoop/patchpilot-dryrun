"""ID helpers and UTC timestamps (RISKS L10: always timezone-aware UTC, ISO-8601 with `Z`)."""
from __future__ import annotations

import secrets
from datetime import UTC, datetime


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(4)}"


def new_scan_id() -> str:
    return _new_id("scn")


def new_finding_id() -> str:
    return _new_id("fnd")


def new_fix_id() -> str:
    return _new_id("fix")


def utcnow() -> datetime:
    return datetime.now(UTC)


def iso_z(dt: datetime | None = None) -> str:
    """`2026-10-28T05:10:00Z`; naive datetimes are treated as UTC."""
    dt = dt or utcnow()
    dt = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
