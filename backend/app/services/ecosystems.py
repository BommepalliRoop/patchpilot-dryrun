"""Language / manifest detection and fix adapters per ecosystem (T02 detection, T08 adapters).

See docs/ARCHITECTURE.md "Language support".
"""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from app.models.schemas import LanguageInfo

# OSV ecosystem name -> manifest / lockfile name patterns (order = display order, PyPI first).
MANIFESTS: dict[str, tuple[str, ...]] = {
    "PyPI": ("requirements.txt", "poetry.lock", "Pipfile.lock"),
    "npm": ("package-lock.json", "yarn.lock", "pnpm-lock.yaml"),
    "Maven": ("pom.xml", "gradle.lockfile"),
    "Go": ("go.mod",),
    "crates.io": ("Cargo.lock",),
    "Packagist": ("composer.lock",),
    "NuGet": ("packages.lock.json", "*.csproj"),
    "RubyGems": ("Gemfile.lock",),
}
SKIP_DIRS = frozenset({"node_modules", "vendor", ".venv", "venv", "target", ".git", "__pycache__", ".tox", "site-packages"})
DEEP_ECOSYSTEMS = frozenset({"PyPI"})  # Python AST reachability; everything else is text + AI


def analysis_for(ecosystem: str) -> str:
    return "deep" if ecosystem in DEEP_ECOSYSTEMS else "generic"


def ecosystem_for_manifest(filename: str) -> str | None:
    for ecosystem, patterns in MANIFESTS.items():
        if any(fnmatch.fnmatch(filename, p) for p in patterns):
            return ecosystem
    return None


def detect(repo_path: Path) -> list[LanguageInfo]:
    """List the ecosystems and manifests found in the repo (skips node_modules, vendor, .venv, target).

    PyPI -> `analysis="deep"`, every other ecosystem -> `analysis="generic"`.
    """
    found: dict[str, list[str]] = {}
    for dirpath, dirnames, filenames in os.walk(repo_path):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            ecosystem = ecosystem_for_manifest(name)
            if ecosystem:
                rel = (Path(dirpath) / name).relative_to(repo_path).as_posix()
                found.setdefault(ecosystem, []).append(rel)
    return [
        LanguageInfo(ecosystem=eco, manifests=sorted(found[eco]), analysis=analysis_for(eco))  # type: ignore[arg-type]
        for eco in MANIFESTS if eco in found
    ]
