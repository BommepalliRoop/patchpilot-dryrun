"""Stage 2 — OSV scan (T02). Falls back to the OSV.dev querybatch API when the CLI is missing (RISKS N3)."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import Any, NamedTuple

import httpx
from cvss import CVSS2, CVSS3, CVSS4
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from app.core.subproc import CommandTimeout, run
from app.models.domain import RawVuln
from app.services import ecosystems

logger = logging.getLogger("patchpilot.scanner")

CLI_TIMEOUT_S = 120  # N3
API_TIMEOUT_S = 15  # N3
OSV_API = "https://api.osv.dev/v1"
QUERYBATCH_CHUNK = 500
EXIT_VULNS_FOUND = 1  # osv-scanner exits 1 when it finds vulnerabilities: success
EXIT_NO_PACKAGES = 128  # nothing to scan: success, empty result

SEVERITY_SCORE = {"CRITICAL": 9.5, "HIGH": 8.0, "MODERATE": 5.5, "MEDIUM": 5.5, "LOW": 3.0}  # L8
DEFAULT_CVSS = 5.0
_UNPINNED = re.compile(r"[<>=!~^*,|\s]")
_REQ_LINE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*==\s*([A-Za-z0-9][A-Za-z0-9.!+_-]*)\s*$")


class ScanError(Exception):
    """Neither osv-scanner nor OSV.dev produced a result. The message is safe to show to users."""


class _Pkg(NamedTuple):
    ecosystem: str
    name: str
    version: str
    manifest: str


# --------------------------------------------------------------------------- helpers (L1, L2, L4, L8)

def canon(ecosystem: str, name: str) -> str:
    """L2: `PyYAML` / `py_yaml` / `Py.YAML` all compare equal for PyPI; other ecosystems are case-sensitive."""
    return str(canonicalize_name(name)) if ecosystem == "PyPI" else name


def vkey(version: str) -> Version:
    """L1: compare with `packaging.version.Version`, never as strings. Odd schemes fall back to their numbers."""
    v = version.strip().lstrip("vV")
    try:
        return Version(v)
    except InvalidVersion:
        nums = re.findall(r"\d+", v)
        return Version(".".join(nums)) if nums else Version("0")


def pick_cve_id(ids: Iterable[str]) -> str:
    """L4: best id available: CVE, else GHSA, else PYSEC, else whatever is left."""
    ordered = sorted(set(ids))
    for prefix in ("CVE-", "GHSA-", "PYSEC-"):
        for i in ordered:
            if i.startswith(prefix):
                return i
    return ordered[0]


def _cvss_from_vector(vector: str) -> float | None:
    try:
        if vector.startswith("CVSS:4"):
            return float(CVSS4(vector).base_score)
        if vector.startswith("CVSS:3"):
            return float(CVSS3(vector).scores()[0])
        if "AV:" in vector:
            return float(CVSS2(vector).scores()[0])
        return float(vector)  # plain numeric score
    except Exception:  # noqa: BLE001 - malformed vector: treat as missing
        return None


def cvss_for(record: dict[str, Any]) -> tuple[float, bool]:
    """Base score from the CVSS vector (v3 > v4 > v2), else database severity word, else 5.0. Returns (score, estimated)."""
    by_type = {s.get("type"): s.get("score", "") for s in record.get("severity", []) or []}
    for kind in ("CVSS_V3", "CVSS_V4", "CVSS_V2"):
        if by_type.get(kind):
            score = _cvss_from_vector(str(by_type[kind]))
            if score is not None:
                return round(score, 1), False
    words = [(record.get("database_specific") or {}).get("severity")]
    words += [(a.get("database_specific") or {}).get("severity") for a in record.get("affected", []) or []]
    for w in words:
        if isinstance(w, str) and w.upper() in SEVERITY_SCORE:
            return SEVERITY_SCORE[w.upper()], True
    return DEFAULT_CVSS, True


def fixed_versions_for(record: dict[str, Any], ecosystem: str, name: str, installed: str) -> list[str]:
    """Fixed versions that apply to `installed`, smallest first. Ranges that do not contain it are ignored."""
    want = canon(ecosystem, name)
    installed_key = vkey(installed)
    in_range: set[str] = set()
    newer: set[str] = set()
    for aff in record.get("affected", []) or []:
        pkg = aff.get("package") or {}
        if pkg.get("ecosystem") != ecosystem or canon(ecosystem, pkg.get("name", "")) != want:
            continue
        for rng in aff.get("ranges", []) or []:
            if rng.get("type") not in ("ECOSYSTEM", "SEMVER"):
                continue
            introduced: str | None = None
            for ev in rng.get("events", []) or []:
                if "introduced" in ev:
                    introduced = ev["introduced"]
                elif "fixed" in ev:
                    fixed = ev["fixed"]
                    if vkey(fixed) > installed_key:
                        newer.add(fixed)
                        if introduced is not None and vkey(introduced) <= installed_key:
                            in_range.add(fixed)
                    introduced = None
    return sorted(in_range or newer, key=vkey)


def _is_pinned(version: str) -> bool:
    """L6: osv-scanner / lockfiles can report a constraint instead of a version; we only handle exact versions."""
    return bool(version) and version != "0" and not _UNPINNED.search(version)


# --------------------------------------------------------------------------- record -> RawVuln

def _group_records(records: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Advisories that share an id or alias are one issue (GHSA-x + PYSEC-y + CVE-z)."""
    groups: list[tuple[set[str], list[dict[str, Any]]]] = []
    for rec in records:
        ids = {rec["id"], *rec.get("aliases", [])}
        hit = [g for g in groups if g[0] & ids]
        merged_ids, merged = set(ids), [rec]
        for g in hit:
            merged_ids |= g[0]
            merged = g[1] + merged
            groups.remove(g)
        groups.append((merged_ids, merged))
    return [g[1] for g in groups]


def _to_raw(pkg: _Pkg, group: list[dict[str, Any]]) -> RawVuln:
    ids: set[str] = set()
    for rec in group:
        ids |= {rec["id"], *rec.get("aliases", [])}
    cve_id = pick_cve_id(ids)
    scores = [cvss_for(r) for r in group]
    measured = [s for s, estimated in scores if not estimated]
    cvss, estimated = (max(measured), False) if measured else (max(s for s, _ in scores), True)
    fixed: set[str] = set()
    refs: list[str] = []
    for rec in group:
        fixed.update(fixed_versions_for(rec, pkg.ecosystem, pkg.name, pkg.version))
        refs += [r["url"] for r in rec.get("references", []) or [] if r.get("url")]
    richest = max(group, key=lambda r: len(r.get("details") or ""))
    summary = next((r["summary"] for r in [richest, *group] if r.get("summary")), "")
    return RawVuln(
        cve_id=cve_id, aliases=sorted(ids - {cve_id}), ecosystem=pkg.ecosystem,
        analysis=ecosystems.analysis_for(pkg.ecosystem),  # type: ignore[arg-type]
        package=canon(pkg.ecosystem, pkg.name), installed_version=pkg.version,
        fixed_versions=sorted(fixed, key=vkey), summary=summary, details=richest.get("details") or "",
        references=list(dict.fromkeys(refs))[:10], cvss=cvss, cvss_estimated=estimated, manifest=pkg.manifest,
    )


def _build(entries: list[tuple[_Pkg, list[dict[str, Any]]]]) -> list[RawVuln]:
    """Merge duplicates: same package + version reported from several manifests or under several advisory ids."""
    merged: dict[tuple[str, str, str], tuple[_Pkg, list[dict[str, Any]]]] = {}
    for pkg, records in entries:
        key = (pkg.ecosystem, canon(pkg.ecosystem, pkg.name), pkg.version)
        if key in merged:
            merged[key][1].extend(records)
        else:
            merged[key] = (pkg, list(records))
    out: list[RawVuln] = []
    for pkg, records in merged.values():
        for group in _group_records(records):
            out.append(_to_raw(pkg, group))
    out.sort(key=lambda v: (v.ecosystem, v.package, v.cve_id))
    return out


# --------------------------------------------------------------------------- osv-scanner CLI

def _find_cli() -> str | None:
    return shutil.which("osv-scanner")


def _relative_manifest(source: str, root: Path) -> str:
    try:
        return Path(source).resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return Path(source).name


def _parse_cli_output(stdout: str, root: Path) -> list[tuple[_Pkg, list[dict[str, Any]]]]:
    start = stdout.find("{")
    if start < 0:
        return []
    data = json.loads(stdout[start:])
    entries: list[tuple[_Pkg, list[dict[str, Any]]]] = []
    for result in data.get("results", []) or []:
        manifest = _relative_manifest((result.get("source") or {}).get("path", ""), root)
        for item in result.get("packages", []) or []:
            p = item.get("package") or {}
            vulns = item.get("vulnerabilities") or []
            if not vulns:
                continue
            if not _is_pinned(p.get("version", "")):
                logger.info("skipping %s: no pinned version (%s)", p.get("name"), manifest)  # L6
                continue
            entries.append((_Pkg(p.get("ecosystem", ""), p["name"], p["version"], manifest), vulns))
    return entries


async def _scan_via_cli(cli: str, path: Path) -> list[tuple[_Pkg, list[dict[str, Any]]]]:
    """Raises on any failure so the caller can fall back to the API."""
    ver = await run([cli, "--version"], timeout=20)
    m = re.search(r"(\d+)\.\d+\.\d+", ver.stdout + ver.stderr)
    major = int(m.group(1)) if m else 2
    logger.info("osv-scanner major version %s", major)
    cmd = ([cli, "scan", "source", "-r", "--format", "json", str(path)] if major >= 2
           else [cli, "--format", "json", "-r", str(path)])
    res = await run(cmd, timeout=CLI_TIMEOUT_S)
    if res.returncode == EXIT_NO_PACKAGES:
        return []
    if res.returncode not in (0, EXIT_VULNS_FOUND):
        last = res.stderr.strip().splitlines()[-1] if res.stderr.strip() else "no output"
        raise RuntimeError(f"osv-scanner exited with {res.returncode}: {last}")
    return _parse_cli_output(res.stdout, path)


# --------------------------------------------------------------------------- OSV.dev API fallback

def parse_requirements(text: str, manifest: str) -> list[_Pkg]:
    """Pinned `name==version` lines only (L6); everything else is logged and skipped."""
    pkgs: list[_Pkg] = []
    for raw in text.splitlines():
        line = raw.split(" #")[0].split(";")[0].split(" --hash")[0].strip().rstrip("\\").strip()
        if not line or line.startswith(("#", "-", "http")):
            continue
        m = _REQ_LINE.match(line)
        if m and not m.group(2).endswith("*"):
            pkgs.append(_Pkg("PyPI", m.group(1), m.group(2), manifest))
        else:
            logger.info("skipping unpinned requirement %r in %s", line.split()[0], manifest)
    return pkgs


def parse_package_lock(text: str, manifest: str) -> list[_Pkg]:
    data = json.loads(text)
    found: dict[tuple[str, str], _Pkg] = {}
    for key, info in (data.get("packages") or {}).items():  # lockfileVersion 2 / 3
        if not key or info.get("link") or not info.get("version"):
            continue
        name = info.get("name") or key.split("node_modules/")[-1]
        found[(name, info["version"])] = _Pkg("npm", name, info["version"], manifest)

    def walk(deps: dict[str, Any]) -> None:  # lockfileVersion 1
        for name, info in deps.items():
            if info.get("version") and not info["version"].startswith(("file:", "git", "http")):
                found[(name, info["version"])] = _Pkg("npm", name, info["version"], manifest)
            walk(info.get("dependencies") or {})

    if not data.get("packages"):
        walk(data.get("dependencies") or {})
    return list(found.values())


def _packages_from_manifests(path: Path) -> list[_Pkg]:
    pkgs: list[_Pkg] = []
    for lang in ecosystems.detect(path):
        for manifest in lang.manifests:
            name = Path(manifest).name
            try:
                text = (path / manifest).read_text(encoding="utf-8", errors="replace")
                if name == "requirements.txt":
                    pkgs += parse_requirements(text, manifest)
                elif name == "package-lock.json":
                    pkgs += parse_package_lock(text, manifest)
                else:
                    logger.info("API fallback cannot parse %s", manifest)
            except (OSError, ValueError) as e:
                logger.warning("could not parse %s: %s", manifest, e)
    return pkgs


def _http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=API_TIMEOUT_S)


async def _scan_via_api(path: Path) -> list[tuple[_Pkg, list[dict[str, Any]]]]:
    pkgs = list({(p.ecosystem, canon(p.ecosystem, p.name), p.version): p for p in _packages_from_manifests(path)}.values())
    if not pkgs:
        return []
    ids_per_pkg: list[list[str]] = []
    async with _http_client() as client:
        for i in range(0, len(pkgs), QUERYBATCH_CHUNK):
            chunk = pkgs[i:i + QUERYBATCH_CHUNK]
            body = {"queries": [{"package": {"name": canon(p.ecosystem, p.name), "ecosystem": p.ecosystem},
                                 "version": p.version} for p in chunk]}
            r = await client.post(f"{OSV_API}/querybatch", json=body)
            r.raise_for_status()
            ids_per_pkg += [[v["id"] for v in res.get("vulns", [])] for res in r.json()["results"]]
        wanted = sorted({vid for ids in ids_per_pkg for vid in ids})
        sem = asyncio.Semaphore(8)

        async def fetch(vid: str) -> tuple[str, dict[str, Any]]:
            async with sem:
                resp = await client.get(f"{OSV_API}/vulns/{vid}")
                resp.raise_for_status()
                return vid, resp.json()

        records = dict(await asyncio.gather(*(fetch(v) for v in wanted)))
    return [(p, [records[v] for v in ids]) for p, ids in zip(pkgs, ids_per_pkg, strict=True) if ids]


# --------------------------------------------------------------------------- public API

async def scan(path: Path) -> list[RawVuln]:
    """Run `osv-scanner scan source -r <path> --format json`; return one RawVuln per vulnerable package + advisory.

    Exit code 1 from osv-scanner means "vulnerabilities found" and is success. Pinned dependencies only (RISKS L6).
    """
    cli = _find_cli()
    cli_error = "osv-scanner is not installed"
    if cli:
        try:
            return _build(await _scan_via_cli(cli, path))
        except CommandTimeout:
            cli_error = f"osv-scanner timed out after {CLI_TIMEOUT_S}s"
        except (RuntimeError, ValueError, OSError) as e:
            cli_error = str(e)
        logger.warning("%s; falling back to OSV.dev API", cli_error)
    try:
        return _build(await _scan_via_api(path))
    except (httpx.HTTPError, KeyError, ValueError) as e:
        raise ScanError(f"Vulnerability scan failed: {cli_error}; OSV.dev API unavailable ({type(e).__name__})") from None
