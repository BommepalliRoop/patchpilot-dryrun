"""Stage 6 — fix engine (T08): bump, install, test in an isolated venv, AI patch loop (max 2 attempts).

docs/ARCHITECTURE.md "Fix engine" and "Fix adapters". One fix per package (RISKS L7):
1. `git clone` the scan's clone into `<WORK_DIR>/<scan_id>/fix-<package>/repo` (the original is never touched).
2. Bump to the smallest version that fixes every routed CVE (L1, L2, L5, S14). If the install itself fails, try the
   next fixed / newer releases of the same package, up to the latest (max 3 tries).
3. Install + test in an isolated env with a clean environment and no package scripts (S2, S15, E7, N4).
4. Tests fail -> the LLM returns a unified diff, which is checked (S6) and applied with `git apply --3way` (E12).
   Max 2 attempts, then `needs_human`. Only small, redacted file excerpts are sent to the LLM (S7, E10).
5. The fix is committed on branch `patchpilot/<package>-<version>`; T09 pushes it from `FixResult.work_dir`.
Toolchain missing (other ecosystems) -> manifest bump only, `fixed_untested`. Work dirs are deleted in `finally`
(E13); on success only the repo copy is kept for the PR stage, and the pipeline deletes it with the scan dir.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import stat
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, NamedTuple
from urllib.parse import quote

import httpx
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.security import redact
from app.core.subproc import CommandResult, CommandTimeout, clean_env, run
from app.models.domain import FixResult, RawVuln
from app.services import cloner, llm
from app.services.ecosystems import SKIP_DIRS
from app.services.llm import LLMError
from app.services.reachability import mask_secrets

logger = logging.getLogger("patchpilot.fixer")

GIT_TIMEOUT_S = 60
VENV_TIMEOUT_S = 120
INSTALL_TIMEOUT_S = 180      # N4
TEST_TIMEOUT_S = 120
REGISTRY_TIMEOUT_S = 10
MAX_INSTALL_TRIES = 3
MAX_AI_ATTEMPTS = 2
OUTPUT_TAIL_LINES = 200
MAX_PATCH_FILES = 3          # E10
MAX_PATCH_FILE_LINES = 400   # E10
MAX_PATCH_CHANGED_LINES = 200  # S6
MAX_PROMPT_OUTPUT_CHARS = 12_000

BOT_NAME = "PatchPilot"
BOT_EMAIL = "patchpilot@users.noreply.github.com"

_FIXED = ("fixed", "fixed_untested")
_SAFE_ARG = re.compile(r"^[A-Za-z0-9@][A-Za-z0-9@._/:+~-]{0,213}$")  # package names / versions passed to tools
_DELIMITER = re.compile(r"=====\s*(?:BEGIN|END) UNTRUSTED CODE", re.IGNORECASE)
_TEST_DIRS = frozenset({"test", "tests", "__tests__", "spec", "specs", ".github"})
_TEST_FILE = re.compile(r"^(?:test_.*\.py|.*_test\.py|conftest\.py|setup\.py|.*\.(?:test|spec)\.[cm]?[jt]sx?)$")

# PyPI distribution -> import names, where they differ from the distribution name (L2).
_PY_IMPORT_NAMES: dict[str, list[str]] = {
    "pyyaml": ["yaml"], "pillow": ["PIL"], "beautifulsoup4": ["bs4"], "python-dateutil": ["dateutil"],
    "scikit-learn": ["sklearn"], "pyjwt": ["jwt"], "opencv-python": ["cv2"], "protobuf": ["google.protobuf"],
    "pycryptodome": ["Crypto"], "python-jose": ["jose"], "attrs": ["attr", "attrs"],
}


class _Fail(Exception):
    """The fix cannot be completed automatically -> `needs_human` with `reason`."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


class PatchRejected(Exception):
    """The AI diff breaks a RISKS S6 rule or does not apply."""


class PatchOutput(BaseModel):
    """Shape of the `patch_code` prompt output."""

    diff: str
    explanation: str = ""


class TestRun(NamedTuple):
    status: Literal["passed", "failed", "no_tests"]
    output: str


# --- versions (L1, L5, S14) ----------------------------------------------------------------------------------

def parse_version(v: str) -> Version | None:
    try:
        return Version(v.strip().lstrip("vV"))
    except InvalidVersion:
        return None


def _stable(v: Version) -> bool:
    return not (v.is_prerelease or v.is_devrelease)


def target_version(installed: str, vulns: list[RawVuln]) -> str | None:
    """Smallest version above `installed` that fixes *every* CVE in `vulns`; None if one has no fixed version (L5).

    Per CVE take its smallest fixed version above the installed one; the target is the largest of those.
    """
    current = parse_version(installed)
    needed: list[tuple[Version, str]] = []
    for vuln in vulns:
        fixes = sorted((p, f) for f in vuln.fixed_versions
                       if (p := parse_version(f)) is not None and (current is None or p > current))
        if not fixes:
            return None
        needed.append(fixes[0])
    return max(needed)[1] if needed else None


def fallback_versions(target: str, vulns: list[RawVuln], releases: list[str], limit: int) -> list[str]:
    """Next versions to try when the target does not install: OSV fixed versions and registry releases of the same
    package above the target (S14), stable only. More than `limit` -> the next ones plus the latest."""
    floor = parse_version(target)
    pool: dict[Version, str] = {}
    for raw in [f for v in vulns for f in v.fixed_versions] + releases:
        p = parse_version(raw)
        if p is not None and floor is not None and p > floor and _stable(p):
            pool.setdefault(p, raw)
    ordered = [pool[k] for k in sorted(pool)]
    if limit <= 0:
        return []
    return ordered if len(ordered) <= limit else ordered[:limit - 1] + [ordered[-1]]


# --- manifest bumps (formatting and comments preserved) -------------------------------------------------------

_REQ_LINE = re.compile(r"^(?P<lead>\s*)(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)(?P<extras>\s*\[[^\]]*\])?"
                       r"(?P<spec>[^;#]*?)(?P<tail>\s*(?:[;#].*)?)$")


def _requirement_name(line: str) -> str | None:
    body = line.strip()
    if not body or body.startswith(("#", "-")):
        return None
    m = _REQ_LINE.match(body)
    return canonicalize_name(m["name"]) if m else None


def bump_requirements(text: str, package: str, version: str) -> str | None:
    """Pin `package` to `version` in a requirements file; keeps extras, markers, comments, spacing and line endings.

    `==` pins stay pins, anything else becomes `>=version`. None if the package is not listed (S14: never add it).
    """
    want = canonicalize_name(package)
    found = False
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        eol = line[len(body):]
        m = _REQ_LINE.match(body)
        if m and _requirement_name(body) == want and not m["spec"].strip().startswith("@"):
            spec = m["spec"]
            pin = re.match(r"^(\s*)(===?)(\s*)[^\s,]+(\s*)$", spec)
            if pin:
                new_spec = f"{pin[1]}{pin[2]}{pin[3]}{version}{pin[4]}"
            else:  # range or bare name -> minimum version
                new_spec = f"{spec[:len(spec) - len(spec.lstrip())]}>={version}{spec[len(spec.rstrip()):]}"
            body = f"{m['lead']}{m['name']}{m['extras'] or ''}{new_spec}{m['tail']}"
            found = True
        out.append(body + eol)
    return "".join(out) if found else None


def bump_package_json(text: str, package: str, version: str) -> str | None:
    """Text-only bump of `package.json` (used when npm is missing); keeps the `^` / `~` prefix."""
    try:
        data = json.loads(text)
    except ValueError:
        return None
    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        spec = (data.get(section) or {}).get(package)
        if isinstance(spec, str):
            prefix = spec[0] if spec[:1] in ("^", "~") else ""
            pattern = re.compile(r'("' + re.escape(package) + r'"\s*:\s*")' + re.escape(spec) + '"')
            new, n = pattern.subn(lambda m: f'{m.group(1)}{prefix}{version}"', text, count=1)
            return new if n else None
    return None


def _regex_bump(pattern: str, repl: Callable[[re.Match[str]], str], flags: int = 0) -> Callable[[str, str, str], str | None]:
    def bump(text: str, package: str, version: str) -> str | None:
        name = re.escape(package.split(":")[-1]) if "{artifact}" in pattern else re.escape(package)
        rx = re.compile(pattern.replace("{artifact}", name).replace("{name}", name), flags)
        new, n = rx.subn(lambda m: repl(m).replace("{version}", version), text)
        return new if n else None
    return bump


# Text bumps for ecosystems without a full adapter (ARCHITECTURE "Language support"), keyed by manifest file name.
_TEXT_BUMPS: dict[str, Callable[[str, str, str], str | None]] = {
    "pom.xml": _regex_bump(r"(<artifactId>\s*{artifact}\s*</artifactId>(?:(?!</dependency>|</plugin>).)*?<version>\s*)"
                         r"[^<$\s]+(\s*</version>)", lambda m: m.group(1) + "{version}" + m.group(2), re.DOTALL),
    "gradle.lockfile": _regex_bump(r"^({name}:)[^=\s]+", lambda m: m.group(1) + "{version}", re.MULTILINE),
    "go.mod": _regex_bump(r"^(\s*(?:require\s+)?{name}\s+)v[^\s]+", lambda m: m.group(1) + "v{version}", re.MULTILINE),
    "Cargo.lock": _regex_bump(r'(name = "{name}"\r?\nversion = ")[^"]+(")', lambda m: m.group(1) + "{version}" + m.group(2)),
    "composer.json": _regex_bump(r'("{name}"\s*:\s*")[^"]*(")', lambda m: m.group(1) + "{version}" + m.group(2)),
    ".csproj": _regex_bump(r'(<PackageReference\s+Include="{name}"\s+Version=")[^"]+(")',
                         lambda m: m.group(1) + "{version}" + m.group(2), re.IGNORECASE),
    "Gemfile.lock": _regex_bump(r"^(    {name} \()[^)]+(\))", lambda m: m.group(1) + "{version}" + m.group(2), re.MULTILINE),
}


def _read(path: Path) -> str:
    with path.open(encoding="utf-8", newline="") as f:  # newline="" keeps CRLF files CRLF
        return f.read()


def _write(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(text)


# --- AI patch checks (S6) ------------------------------------------------------------------------------------

def is_protected(path: str) -> bool:
    """Tests, CI and build hooks are never edited by an AI patch (S6)."""
    parts = PurePosixPath(path).parts
    return any(p.lower() in _TEST_DIRS for p in parts[:-1]) or bool(_TEST_FILE.match(parts[-1] if parts else ""))


def _check_path(raw: str) -> str:
    p = raw.replace("\\", "/")
    if p.startswith("/") or re.match(r"^[A-Za-z]:", p) or "\x00" in p:
        raise PatchRejected(f"absolute path not allowed: {raw}")
    parts = [s for s in p.split("/") if s not in ("", ".")]
    if not parts or ".." in parts:
        raise PatchRejected(f"path outside the repository: {raw}")
    return "/".join(parts)


def validate_patch(diff: str, allowed: set[str], manifest: str | None = None, package: str | None = None) -> list[str]:
    """RISKS S6. Returns the edited paths; raises PatchRejected.

    Only `allowed` files (sent to the LLM) plus the manifest lines of `package`; no new, deleted, renamed or binary
    files; no tests / CI / setup.py / conftest.py; no `..` or absolute paths; at most 200 changed lines.
    """
    if not diff.strip():
        raise PatchRejected("empty diff")
    lines = diff.splitlines()
    changed: dict[str, list[str]] = {}
    current: str | None = None
    total = 0
    for i, line in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if line.startswith("--- ") and nxt.startswith("+++ "):
            paths = [line[4:], nxt[4:]]
            clean: list[str] = []
            for raw in paths:
                raw = raw.split("\t")[0].strip().strip('"')
                if raw == "/dev/null":
                    raise PatchRejected("creating or deleting files is not allowed")
                if raw.startswith(("a/", "b/")):
                    raw = raw[2:]
                clean.append(_check_path(raw))
            if clean[0] != clean[1]:
                raise PatchRejected("renaming files is not allowed")
            current = clean[1]
            changed.setdefault(current, [])
            continue
        if line.startswith("+++ ") and i > 0 and lines[i - 1].startswith("--- "):
            continue
        if line.startswith(("new file mode", "deleted file mode", "rename from", "rename to", "copy from", "copy to",
                            "old mode", "new mode", "Binary files", "GIT binary patch")):
            raise PatchRejected(f"unsupported diff operation: {line.split(' ')[0]} {line.split(' ')[1]}")
        if current and line[:1] in ("+", "-"):
            total += 1
            changed[current].append(line[1:])
    if not changed:
        raise PatchRejected("diff has no --- a/<path> / +++ b/<path> file headers")
    if total > MAX_PATCH_CHANGED_LINES:
        raise PatchRejected(f"diff changes {total} lines (max {MAX_PATCH_CHANGED_LINES})")
    for path, edits in changed.items():
        if is_protected(path):
            raise PatchRejected(f"{path} is a test, CI or build file and may not be edited")
        if manifest and package and path == manifest:
            wrong = [e for e in edits if e.strip() and _requirement_name(e) != canonicalize_name(package)]
            if wrong:
                raise PatchRejected(f"{path} may only change the {package} line")
        elif path not in allowed:
            raise PatchRejected(f"{path} is not one of the files the patch may edit")
    return sorted(changed)


# --- adapters ------------------------------------------------------------------------------------------------

class _Adapter:
    """`bump` / `install` / `test` for one ecosystem (ARCHITECTURE "Fix adapters")."""

    patch_suffixes: tuple[str, ...] = ()  # files the AI patch may edit; empty = no AI patch for this ecosystem

    def __init__(self, ecosystem: str) -> None:
        self.ecosystem = ecosystem

    def locate(self, repo: Path, vulns: list[RawVuln]) -> str:
        manifest = next((v.manifest for v in vulns if v.manifest), "")
        if not manifest or not (repo / manifest).is_file():
            raise _Fail("unsupported_manifest", f"no manifest found for {self.ecosystem}")
        return manifest

    def toolchain(self) -> bool:
        return False

    def env(self, fix: _Fix) -> dict[str, str]:
        return clean_env()

    async def prepare(self, fix: _Fix) -> None:
        """Once per fix (e.g. the venv)."""

    def text_bump(self, fix: _Fix, version: str) -> None:
        path = fix.repo / fix.manifest
        name = path.name if path.suffix != ".csproj" else ".csproj"
        files = [path]
        if self.ecosystem == "NuGet" and path.suffix != ".csproj":  # packages.lock.json -> the projects next to it
            files, name = sorted(path.parent.glob("*.csproj")), ".csproj"
        bump = _TEXT_BUMPS.get(name)
        bumped = False
        for f in files:
            new = bump(_read(f), fix.package, version) if bump else None
            if new is not None:
                _write(f, new)
                bumped = True
        if not bumped:
            raise _Fail("package_not_in_manifest", f"cannot bump {fix.package} in {fix.manifest}")

    async def install(self, fix: _Fix, version: str) -> CommandResult:
        """Bump to `version` and install. Non-zero return code = install failed (try the next version)."""
        self.text_bump(fix, version)
        return CommandResult(0, "", "")

    async def test(self, fix: _Fix) -> TestRun:
        return TestRun("no_tests", "")

    async def releases(self, package: str) -> list[str]:
        return []

    def imports(self, package: str) -> re.Pattern[str] | None:
        return None


class _PyPI(_Adapter):
    patch_suffixes = (".py",)

    def locate(self, repo: Path, vulns: list[RawVuln]) -> str:
        manifest = next((v.manifest for v in vulns if v.manifest), "") or "requirements.txt"
        name = PurePosixPath(manifest).name.lower()
        if not (name.startswith("requirements") and name.endswith(".txt")):
            raise _Fail("unsupported_manifest", f"{manifest} is not supported (requirements.txt pins only)")
        path = repo / manifest
        if not path.is_file():
            raise _Fail("unsupported_manifest", "repository has no requirements.txt")
        if "--hash" in _read(path):
            raise _Fail("unsupported_manifest", "hash-pinned requirements are not supported")
        return manifest

    def toolchain(self) -> bool:
        return True  # the backend's own Python (or FIX_PYTHON) builds the venv

    def env(self, fix: _Fix) -> dict[str, str]:
        return clean_env({"PIP_CACHE_DIR": str(fix.cache / "pip"), "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                          "PIP_NO_INPUT": "1", "PYTHONDONTWRITEBYTECODE": "1"})

    def python(self, fix: _Fix) -> Path:
        return fix.venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    async def prepare(self, fix: _Fix) -> None:
        interpreter = get_settings().fix_python or sys.executable
        result = await fix.cmd([interpreter, "-m", "venv", str(fix.venv)], VENV_TIMEOUT_S, "venv_failed")
        if result.returncode != 0:
            raise _Fail("venv_failed", _tail(result))

    def text_bump(self, fix: _Fix, version: str) -> None:
        path = fix.repo / fix.manifest
        new = bump_requirements(_read(path), fix.package, version)
        if new is None:
            raise _Fail("package_not_in_manifest", f"{fix.package} is not pinned in {fix.manifest}")
        _write(path, new)

    async def install(self, fix: _Fix, version: str | None) -> CommandResult:
        if version is not None:
            self.text_bump(fix, version)
        cmd = [str(self.python(fix)), "-m", "pip", "install", "-r", fix.manifest]
        dev = (fix.repo / fix.manifest).with_name("requirements-dev.txt")
        if dev.is_file() and dev != fix.repo / fix.manifest:
            cmd += ["-r", dev.relative_to(fix.repo).as_posix()]
        return await fix.cmd(cmd + ["pytest"], INSTALL_TIMEOUT_S, "install_failed")

    async def test(self, fix: _Fix) -> TestRun:
        result = await fix.cmd([str(self.python(fix)), "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                               TEST_TIMEOUT_S, "test_timeout")
        status = "passed" if result.returncode == 0 else "no_tests" if result.returncode == 5 else "failed"  # E11
        return TestRun(status, _tail(result))

    async def releases(self, package: str) -> list[str]:
        data = await _registry_json(f"https://pypi.org/pypi/{canonicalize_name(package)}/json")
        return [v for v, files in (data.get("releases") or {}).items()
                if files and not all(f.get("yanked") for f in files)]

    def imports(self, package: str) -> re.Pattern[str]:
        names = _PY_IMPORT_NAMES.get(canonicalize_name(package), [canonicalize_name(package).replace("-", "_")])
        alt = "|".join(re.escape(n) for n in names)
        return re.compile(rf"^\s*(?:import|from)\s+(?:{alt})\b", re.MULTILINE)


class _Npm(_Adapter):
    patch_suffixes = (".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx")

    def locate(self, repo: Path, vulns: list[RawVuln]) -> str:
        manifest = next((v.manifest for v in vulns if v.manifest), "") or "package-lock.json"
        pkg_json = PurePosixPath(manifest).with_name("package.json").as_posix()
        if not (repo / pkg_json).is_file():
            raise _Fail("unsupported_manifest", f"no package.json next to {manifest}")
        self._lock = PurePosixPath(manifest).name
        return pkg_json

    def toolchain(self) -> bool:
        return shutil.which("npm") is not None and getattr(self, "_lock", "") in ("package-lock.json", "package.json")

    def env(self, fix: _Fix) -> dict[str, str]:
        extra = {"npm_config_cache": str(fix.cache / "npm"), "npm_config_ignore_scripts": "true",  # S15
                 "npm_config_audit": "false", "npm_config_fund": "false", "npm_config_update_notifier": "false"}
        if os.environ.get("COMSPEC"):
            extra["COMSPEC"] = os.environ["COMSPEC"]  # Windows: npm runs scripts through cmd.exe
        return clean_env(extra)

    def text_bump(self, fix: _Fix, version: str) -> None:
        path = fix.repo / fix.manifest
        new = bump_package_json(_read(path), fix.package, version)
        if new is None:
            raise _Fail("package_not_in_manifest", f"{fix.package} is not a direct dependency in {fix.manifest}")
        _write(path, new)

    async def install(self, fix: _Fix, version: str | None) -> CommandResult:
        path = fix.repo / fix.manifest
        data = json.loads(_read(path))
        section = next((s for s in ("dependencies", "devDependencies", "optionalDependencies")
                        if isinstance((data.get(s) or {}).get(fix.package), str)), None)
        if section is None:  # transitive only: `npm install` would add it as a new direct dependency (S14)
            raise _Fail("package_not_in_manifest", f"{fix.package} is not a direct dependency in {fix.manifest}")
        spec: str = data[section][fix.package]
        save = {"dependencies": "--save-prod", "devDependencies": "--save-dev",
                "optionalDependencies": "--save-optional"}[section]
        prefix = ["--save-prefix", spec[0]] if spec[:1] in ("^", "~") else ["--save-exact"]
        npm = shutil.which("npm") or "npm"
        cmd = [npm, "install", f"{fix.package}@{version or spec}", "--ignore-scripts", "--no-audit", "--no-fund",
               save, *prefix]
        return await fix.cmd(cmd, INSTALL_TIMEOUT_S, "install_failed", cwd=path.parent)

    async def test(self, fix: _Fix) -> TestRun:
        path = fix.repo / fix.manifest
        script = ((json.loads(_read(path)).get("scripts") or {}).get("test") or "")
        if not script or "no test specified" in script:
            return TestRun("no_tests", "")
        result = await fix.cmd([shutil.which("npm") or "npm", "test"], TEST_TIMEOUT_S, "test_timeout", cwd=path.parent)
        return TestRun("passed" if result.returncode == 0 else "failed", _tail(result))

    async def releases(self, package: str) -> list[str]:
        data = await _registry_json(f"https://registry.npmjs.org/{quote(package, safe='@')}")
        return [v for v, info in (data.get("versions") or {}).items() if not (info or {}).get("deprecated")]

    def imports(self, package: str) -> re.Pattern[str]:
        p = re.escape(package)
        return re.compile(rf"""require\(\s*['"]{p}(?:/[^'"]*)?['"]\s*\)|from\s+['"]{p}(?:/[^'"]*)?['"]"""
                          rf"""|import\s+['"]{p}(?:/[^'"]*)?['"]""")


@dataclass(frozen=True)
class _Tool:
    binary: str
    bump: list[str] | None   # tool command that bumps the version itself ({package}, {version})
    install: list[str] | None
    test: list[str]


# ARCHITECTURE "Language support" table. Scripts are never run (S15).
_TOOLS: dict[str, _Tool] = {
    "Maven": _Tool("mvn", None, None, ["mvn", "-q", "test"]),
    "Go": _Tool("go", ["go", "get", "{package}@v{version}"], None, ["go", "test", "./..."]),
    "crates.io": _Tool("cargo", ["cargo", "update", "-p", "{package}", "--precise", "{version}"], None, ["cargo", "test"]),
    "Packagist": _Tool("composer", ["composer", "require", "{package}:{version}", "--no-scripts", "--no-interaction"],
                       None, ["vendor/bin/phpunit"]),
    "NuGet": _Tool("dotnet", None, None, ["dotnet", "test"]),
    "RubyGems": _Tool("bundle", None, ["bundle", "install"], ["bundle", "exec", "rspec"]),
}


class _Generic(_Adapter):
    """Other ecosystems: bump the manifest; install + test only if the toolchain is on PATH, else `fixed_untested`."""

    def __init__(self, ecosystem: str) -> None:
        super().__init__(ecosystem)
        self.tool = _TOOLS.get(ecosystem)

    def locate(self, repo: Path, vulns: list[RawVuln]) -> str:
        manifest = super().locate(repo, vulns)
        if self.ecosystem == "Packagist" and PurePosixPath(manifest).name == "composer.lock":
            manifest = PurePosixPath(manifest).with_name("composer.json").as_posix()
        if PurePosixPath(manifest).name not in _TEXT_BUMPS and not manifest.endswith((".csproj", "packages.lock.json")):
            raise _Fail("unsupported_manifest", f"cannot bump {manifest}")
        return manifest

    def toolchain(self) -> bool:
        return self.tool is not None and shutil.which(self.tool.binary) is not None

    async def install(self, fix: _Fix, version: str | None) -> CommandResult:
        assert self.tool is not None and version is not None
        cwd = (fix.repo / fix.manifest).parent
        if self.tool.bump:
            cmd = [a.replace("{package}", fix.package).replace("{version}", version) for a in self.tool.bump]
            result = await fix.cmd(_which(cmd), INSTALL_TIMEOUT_S, "install_failed", cwd=cwd)
            if result.returncode != 0:
                return result
        else:
            self.text_bump(fix, version)
        if self.tool.install:
            return await fix.cmd(_which(self.tool.install), INSTALL_TIMEOUT_S, "install_failed", cwd=cwd)
        return CommandResult(0, "", "")

    async def test(self, fix: _Fix) -> TestRun:
        assert self.tool is not None
        cwd = (fix.repo / fix.manifest).parent
        result = await fix.cmd(_which(self.tool.test), TEST_TIMEOUT_S, "test_timeout", cwd=cwd)
        return TestRun("passed" if result.returncode == 0 else "failed", _tail(result))


def adapter_for(ecosystem: str) -> _Adapter:
    if ecosystem == "PyPI":
        return _PyPI(ecosystem)
    if ecosystem == "npm":
        return _Npm(ecosystem)
    return _Generic(ecosystem)


def _which(cmd: list[str]) -> list[str]:
    """Windows: npm/composer/... are .cmd shims that exec needs by full path."""
    return [shutil.which(cmd[0]) or cmd[0], *cmd[1:]]


async def _registry_json(url: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=REGISTRY_TIMEOUT_S) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {}
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("release lookup failed (%s): %s", url, redact(e))
        return {}


def _tail(result: CommandResult, lines: int = OUTPUT_TAIL_LINES) -> str:
    text = (result.stdout + ("\n" + result.stderr if result.stderr.strip() else "")).strip()
    return redact("\n".join(text.splitlines()[-lines:]))


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-.") or "pkg"


def _on_rm_error(func, path, _exc) -> None:  # noqa: ANN001
    """Windows: git object files are read-only."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _rmtree(path: Path) -> None:
    if not path.exists():
        return
    try:
        if sys.version_info >= (3, 12):
            shutil.rmtree(path, onexc=_on_rm_error)
        else:
            shutil.rmtree(path, onerror=_on_rm_error)
    except OSError as e:
        logger.warning("cleanup of %s failed: %s", path.name, redact(e))


# --- one package fix -----------------------------------------------------------------------------------------

class _Fix:
    def __init__(self, scan_id: str, repo_path: Path, package: str, vulns: list[RawVuln]) -> None:
        self.source = repo_path
        self.package = package
        self.vulns = vulns
        self.ecosystem = vulns[0].ecosystem
        self.installed = vulns[0].installed_version
        self.adapter = adapter_for(self.ecosystem)
        self.fix_dir = cloner.scan_dir(scan_id) / f"fix-{_slug(canonicalize_name(package))}"
        self.repo = self.fix_dir / "repo"
        self.venv = self.fix_dir / "venv"  # outside the repo copy, so it can never be committed
        self.cache = get_settings().work_path / "cache"  # shared pip / npm cache (N4)
        self.manifest = ""
        self.base_sha = ""
        self.bump_sha = ""
        self.branch = ""
        self.new_version: str | None = None
        self.attempts = 0
        self.explanation = ""

    # -- commands --

    async def cmd(self, cmd: list[str], timeout: float, timeout_reason: str, cwd: Path | None = None) -> CommandResult:
        """Run a tool in the repo copy with a clean env (S2) and timeout (E7). A timeout ends the fix (N4)."""
        try:
            return await run(cmd, cwd=cwd or self.repo, env=self.adapter.env(self), timeout=timeout)
        except CommandTimeout as e:
            raise _Fail(timeout_reason, str(e)) from None
        except FileNotFoundError:
            raise _Fail("toolchain_missing", f"{Path(cmd[0]).name} not found") from None

    async def git(self, *args: str, check: bool = True) -> CommandResult:
        env = clean_env({"GIT_TERMINAL_PROMPT": "0", "GIT_AUTHOR_NAME": BOT_NAME, "GIT_AUTHOR_EMAIL": BOT_EMAIL,
                         "GIT_COMMITTER_NAME": BOT_NAME, "GIT_COMMITTER_EMAIL": BOT_EMAIL})
        cmd = ["git", "-c", "core.autocrlf=false", "-c", "commit.gpgsign=false", *args]
        try:
            result = await run(cmd, cwd=self.repo if self.repo.exists() else self.fix_dir, env=env,
                               timeout=GIT_TIMEOUT_S)
        except CommandTimeout as e:
            raise _Fail("git_failed", str(e)) from None
        if check and result.returncode != 0:
            raise _Fail("git_failed", redact(result.stderr.strip()[-300:]))
        return result

    # -- flow --

    async def run(self) -> FixResult:
        keep = False
        try:
            result = await self._run()
            keep = result.status in _FIXED
            return result
        except _Fail as e:
            logger.info("fix %s %s -> needs_human (%s)", self.package, self.new_version or "", redact(e))
            return FixResult(package=self.package, new_version=self.new_version, patch_diff=await self._diff(),
                             attempts=self.attempts, status="needs_human", reason=e.reason)
        finally:  # E13
            _rmtree(self.venv)
            if not keep:
                _rmtree(self.fix_dir)

    async def _run(self) -> FixResult:
        target = target_version(self.installed, self.vulns)
        if target is None:
            raise _Fail("no_fix_available")  # L5
        if not _SAFE_ARG.match(self.package) or not _SAFE_ARG.match(target):
            raise _Fail("invalid_package_name", self.package)
        await self._clone()
        self.manifest = self.adapter.locate(self.repo, self.vulns)

        if not self.adapter.toolchain():
            self.adapter.text_bump(self, target)
            self.new_version = target
            await self._commit_bump()
            logger.info("fix %s %s: toolchain missing, tests not run", self.package, target)
            return await self._result("fixed_untested", "toolchain_missing")

        await self.adapter.prepare(self)
        await self._install(target)
        run = await self.adapter.test(self)
        if run.status == "no_tests":
            raise _Fail("no_tests")  # E11: cannot prove the fix
        if run.status == "passed":
            return await self._result("fixed")
        if not self.adapter.patch_suffixes:
            raise _Fail("tests_failed")
        return await self._ai_loop(run.output)

    async def _clone(self) -> None:
        """Local clone of the scan's clone: the original is never modified, and the copy has LF line endings."""
        _rmtree(self.fix_dir)
        self.fix_dir.mkdir(parents=True, exist_ok=True)
        await self.git("clone", "--quiet", "--no-hardlinks", "--", str(self.source), str(self.repo))
        await self.git("config", "core.autocrlf", "false")
        self.base_sha = (await self.git("rev-parse", "HEAD")).stdout.strip()

    async def _install(self, target: str) -> None:
        """Bump + install; if the install itself fails, try the next fixed / newer releases (max 3 tries, S14)."""
        candidates = [target]
        tried: list[str] = []
        output = ""
        while candidates and len(tried) < MAX_INSTALL_TRIES:
            version = candidates.pop(0)
            tried.append(version)
            await self.git("checkout", "--quiet", "--", ".")  # undo the previous try's bump
            result = await self.adapter.install(self, version)
            if result.returncode == 0:
                self.new_version = version
                await self._commit_bump()
                return
            output = _tail(result, 20)
            logger.info("fix %s: install of %s failed, trying a newer release", self.package, version)
            if len(tried) == 1:
                releases = await self.adapter.releases(self.package)
                candidates = fallback_versions(target, self.vulns, releases, MAX_INSTALL_TRIES - 1)
        self.new_version = tried[-1]
        raise _Fail("install_failed", f"tried {', '.join(tried)}: {output[-500:]}")  # N4

    async def _commit_bump(self) -> None:
        assert self.new_version is not None
        self.branch = f"patchpilot/{_slug(canonicalize_name(self.package) if self.ecosystem == 'PyPI' else self.package)}" \
                      f"-{_slug(self.new_version)}"
        await self.git("checkout", "--quiet", "-B", self.branch)
        await self.git("add", "--update")
        cves = ", ".join(dict.fromkeys(v.cve_id for v in self.vulns))
        await self.git("commit", "--quiet", "--allow-empty", "-m",
                       f"PatchPilot: upgrade {self.package} {self.installed} -> {self.new_version}", "-m", f"Fixes: {cves}")
        self.bump_sha = (await self.git("rev-parse", "HEAD")).stdout.strip()

    async def _ai_loop(self, test_output: str) -> FixResult:
        """Tests fail after the bump: LLM diff -> S6 checks -> `git apply --3way` -> re-test. Max 2 attempts."""
        files = self._relevant_files(test_output)
        if not files:
            raise _Fail("tests_failed", "no source file the AI patch may edit")
        previous = ""
        for attempt in range(1, MAX_AI_ATTEMPTS + 1):
            self.attempts = attempt
            try:
                patch = await llm.complete_json("patch_code", {
                    "package": self.package, "old_version": self.installed, "new_version": self.new_version,
                    "test_output": _for_prompt(test_output), "files": self._file_blocks(files),
                    "previous_attempt": previous or "(none)"}, PatchOutput)
            except LLMError as e:
                raise _Fail("ai_unavailable", str(e)) from None
            try:
                touched = await self._apply(patch.diff, attempt, set(files))
            except PatchRejected as e:  # E12: counts as an attempt; the next one sees the error
                logger.info("fix %s: AI patch %d rejected: %s", self.package, attempt, redact(e))
                previous = f"Your diff was rejected and not applied: {e}\nYour diff was:\n{patch.diff[:4000]}"
                await self.git("reset", "--quiet", "--hard", self.bump_sha)
                continue
            if self.manifest in touched and self.ecosystem == "PyPI":
                result = await self.adapter.install(self, None)
                if result.returncode != 0:
                    raise _Fail("install_failed", _tail(result, 20))
            run = await self.adapter.test(self)
            if run.status == "passed":
                self.explanation = patch.explanation
                await self.git("add", "--update", "--", *touched)
                await self.git("commit", "--quiet", "-m",
                               f"PatchPilot: adapt code to {self.package} {self.new_version}",
                               "-m", redact(patch.explanation)[:2000] or "AI patch")
                logger.info("fix %s %s: AI patch %d made the tests pass", self.package, self.new_version, attempt)
                return await self._result("fixed")
            test_output = run.output
            previous = (f"Your diff applied but the tests still fail.\nYour diff was:\n{patch.diff[:4000]}\n"
                        f"Test output after it:\n{_for_prompt(run.output)[-4000:]}")
            await self.git("reset", "--quiet", "--hard", self.bump_sha)
        raise _Fail("ai_patch_failed", f"tests still fail after {MAX_AI_ATTEMPTS} AI attempts")

    async def _apply(self, diff: str, attempt: int, allowed: set[str]) -> list[str]:
        touched = validate_patch(diff, allowed, self.manifest if self.ecosystem == "PyPI" else None, self.package)
        patch_file = self.fix_dir / f"ai-patch-{attempt}.diff"
        _write(patch_file, diff if diff.endswith("\n") else diff + "\n")
        result = await self.git("apply", "--3way", "--recount", "--whitespace=nowarn", str(patch_file), check=False)
        if result.returncode != 0:
            await self.git("reset", "--quiet", "--hard", self.bump_sha)
            raise PatchRejected(f"git apply failed: {redact(result.stderr.strip())[-600:]}")
        names = (await self.git("diff", "--name-only", "HEAD")).stdout.split()
        outside = [n for n in names if n not in touched]
        if outside:  # defence in depth: git apply touched something the checks did not see
            await self.git("reset", "--quiet", "--hard", self.bump_sha)
            raise PatchRejected(f"patch changed unexpected files: {', '.join(outside)}")
        if self.manifest in names:
            self._check_manifest_pin()
        return names or touched

    def _check_manifest_pin(self) -> None:
        """S14: an AI edit of the manifest may only move the target package to a version >= the bump."""
        floor = parse_version(self.new_version or "")
        for line in _read(self.repo / self.manifest).splitlines():
            if _requirement_name(line) == canonicalize_name(self.package):
                m = re.search(r"(?:==|>=|~=)\s*([^\s,;#]+)", line)
                p = parse_version(m.group(1)) if m else None
                if m is None or p is None or floor is None or p < floor:
                    raise PatchRejected(f"{self.package} may not be pinned below {self.new_version}")
                self.new_version = m.group(1)
                return
        raise PatchRejected(f"the patch removed {self.package} from {self.manifest}")

    def _relevant_files(self, test_output: str) -> list[str]:
        """Files the AI may see and edit (S6, E10): source files named in the failing output, then files importing
        the package. Never tests / CI / build files; max 3."""
        suffixes = self.adapter.patch_suffixes
        found: list[str] = []
        root = self.repo.resolve()

        def add(candidate: Path) -> None:
            try:
                path = candidate.resolve()
                rel = path.relative_to(root).as_posix()
            except (OSError, ValueError):
                return
            if (path.is_file() and path.suffix in suffixes and rel not in found and not is_protected(rel)
                    and not any(p in SKIP_DIRS for p in PurePosixPath(rel).parts)):
                found.append(rel)

        ext = "|".join(re.escape(s[1:]) for s in suffixes)
        for m in re.finditer(rf"((?:[A-Za-z]:)?[\w./\\-]+\.(?:{ext}))\b", test_output):
            raw = m.group(1).replace("\\", "/")
            add(Path(raw) if Path(raw).is_absolute() else self.repo / raw)
        pattern = self.adapter.imports(self.package)
        if pattern is not None:
            for dirpath, dirnames, filenames in os.walk(self.repo):
                dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
                for name in sorted(filenames):
                    if name.endswith(suffixes):
                        path = Path(dirpath) / name
                        try:
                            if pattern.search(path.read_text(encoding="utf-8", errors="replace")):
                                add(path)
                        except OSError:
                            continue
        return found[:MAX_PATCH_FILES]

    def _file_blocks(self, files: list[str]) -> str:
        """S7 + E10: masked, max 400 lines per file, wrapped as untrusted code."""
        blocks = []
        for rel in files:
            lines = _read(self.repo / rel).splitlines()
            body = "\n".join(lines[:MAX_PATCH_FILE_LINES])
            if len(lines) > MAX_PATCH_FILE_LINES:
                body += f"\n... ({len(lines) - MAX_PATCH_FILE_LINES} more lines not shown)"
            body = _DELIMITER.sub("= = = (marker removed)", mask_secrets(body))
            blocks.append(f"===== BEGIN UNTRUSTED CODE {rel} =====\n{body}\n===== END UNTRUSTED CODE =====")
        return "\n\n".join(blocks)

    async def _diff(self) -> str:
        """Full diff vs the scanned commit (committed fix plus anything left in the work tree)."""
        if not self.base_sha or not self.repo.exists():
            return ""
        try:
            result = await self.git("diff", self.base_sha, "--", ".", check=False)
        except _Fail:
            return ""
        return redact(result.stdout)

    async def _result(self, status: Literal["fixed", "fixed_untested"], reason: str = "") -> FixResult:
        return FixResult(package=self.package, new_version=self.new_version, patch_diff=await self._diff(),
                         tests_passed=status == "fixed", attempts=self.attempts, branch=self.branch,
                         work_dir=self.repo, status=status, reason=reason)


def _for_prompt(output: str) -> str:
    return _DELIMITER.sub("= = = (marker removed)", mask_secrets(output))[-MAX_PROMPT_OUTPUT_CHARS:]


async def fix_package(scan_id: str, repo_path: Path, package: str, vulns: list[RawVuln]) -> FixResult:
    """One fix per package: smallest version that fixes *all* of `vulns`, one branch `patchpilot/<package>-<version>`.

    Never modifies `repo_path`; works on a copy under `<WORK_DIR>/<scan_id>`. PRs are never auto-merged (RISKS S6).
    On `fixed` / `fixed_untested` the commit is on `branch` in `work_dir` (T09 pushes it); never raises for a
    fix that fails, it returns `needs_human` with a `reason`.
    """
    if not vulns:
        return FixResult(package=package, status="needs_human", reason="no_findings")
    return await _Fix(scan_id, repo_path, package, vulns).run()
