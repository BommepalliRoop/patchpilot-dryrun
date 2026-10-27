"""Structured logging with scan_id / finding_id context and secret redaction (RISKS O2, S4)."""
from __future__ import annotations

import contextvars
import logging
from collections.abc import Iterator
from contextlib import contextmanager

from app.core.security import redact

_scan_id: contextvars.ContextVar[str] = contextvars.ContextVar("scan_id", default="-")
_finding_id: contextvars.ContextVar[str] = contextvars.ContextVar("finding_id", default="-")


@contextmanager
def log_context(scan_id: str | None = None, finding_id: str | None = None) -> Iterator[None]:
    """Every log line emitted inside the block carries these ids."""
    tokens = []
    if scan_id is not None:
        tokens.append((_scan_id, _scan_id.set(scan_id)))
    if finding_id is not None:
        tokens.append((_finding_id, _finding_id.set(finding_id)))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.scan_id = _scan_id.get()
        record.finding_id = _finding_id.get()
        return True


class RedactingFormatter(logging.Formatter):
    """Formats, then masks secrets in the whole line including tracebacks."""

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


_FORMAT = "%(asctime)s %(levelname)-7s %(name)s scan_id=%(scan_id)s finding_id=%(finding_id)s %(message)s"


def setup_logging(level: int = logging.INFO) -> None:
    """Idempotent. Installs one redacting handler on the root logger."""
    root = logging.getLogger()
    for handler in root.handlers:
        if getattr(handler, "_patchpilot", False):
            return
    handler = logging.StreamHandler()
    handler._patchpilot = True  # type: ignore[attr-defined]
    handler.addFilter(ContextFilter())
    handler.setFormatter(RedactingFormatter(_FORMAT))
    root.addHandler(handler)
    root.setLevel(level)
