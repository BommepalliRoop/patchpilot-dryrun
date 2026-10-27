"""Language / manifest detection and fix adapters per ecosystem (T02 detection, T08 adapters).

See docs/ARCHITECTURE.md "Language support".
"""
from __future__ import annotations

from pathlib import Path

from app.models.schemas import LanguageInfo


def detect(repo_path: Path) -> list[LanguageInfo]:
    """List the ecosystems and manifests found in the repo (skips node_modules, vendor, .venv, target).

    PyPI -> `analysis="deep"`, every other ecosystem -> `analysis="generic"`.
    """
    raise NotImplementedError("T02")
