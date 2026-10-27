"""Secret redaction (RISKS S4) and API-key check for machine callers (S8, S10)."""
from __future__ import annotations

import hmac
import re

from fastapi import Header

from app.core.config import get_settings
from app.core.errors import ApiError

_MASK = "***"

# Order matters: URL credentials first so the user part is not left behind.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(://)[^/\s:@]+:[^/\s@]+@"), r"\1" + _MASK + "@"),  # https://user:pass@host
    (re.compile(r"(://)(?:ghp_|github_pat_|gho_|ghs_|glpat-)[A-Za-z0-9_\-]+@"), r"\1" + _MASK + "@"),  # token as user
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{10,}"), _MASK),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{10,}"), _MASK),
    (re.compile(r"\bglpat-[A-Za-z0-9_\-]{10,}"), _MASK),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"), _MASK),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=\-]{6,}"), "Bearer " + _MASK),
    (re.compile(r"(?i)(x-api-key|api-key|authorization)(\s*[:=]\s*)(?:(?:Bearer|Basic|token)\s+)?[^\s,;\"']+"),
     r"\1\2" + _MASK),
]


def redact(text: object) -> str:
    """Mask tokens and credentials in any text that may be logged, streamed, stored or returned."""
    s = text if isinstance(text, str) else str(text)
    for secret in get_settings().secret_values:
        if len(secret) >= 6:
            s = s.replace(secret, _MASK)
    for pattern, repl in _PATTERNS:
        s = pattern.sub(repl, s)
    return s


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Machine-caller auth (Boomi B1, demo reset). Constant-time compare (S10)."""
    expected = get_settings().patchpilot_api_key
    if not expected or not x_api_key or not hmac.compare_digest(x_api_key.encode(), expected.encode()):
        raise ApiError(401, "unauthorized", "Missing or invalid X-API-Key")
