"""Stage 3 — vulnerable symbol extraction (T05). LLM via `app.services.llm`, cached by CVE id."""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

from packaging.utils import canonicalize_name
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from app.core.config import get_settings
from app.core.db import get_engine
from app.core.security import redact
from app.models.domain import RawVuln, VulnSymbols
from app.models.tables import SymbolCacheRow
from app.services import llm
from app.services.llm import LLMError

logger = logging.getLogger("patchpilot.symbols")

MAX_DETAILS_CHARS = 4000  # E10
MAX_SUMMARY_CHARS = 500
MAX_REFERENCES = 10
MAX_SYMBOLS = 30
MAX_NAME_LEN = 120
MIN_CONFIDENCE = 0.5  # below this (or no symbols) the seed map is preferred

_NAME = re.compile(r"^[A-Za-z_$][\w$]*(?:[.:#][A-Za-z_$][\w$]*)*$")  # identifier path, never prose or an instruction

_memory: dict[str, VulnSymbols] = {}


def clear_cache() -> None:
    """Drop the in-memory cache (tests; the SQLite cache is cleared with the DB)."""
    _memory.clear()


# --- seed map ------------------------------------------------------------------------------------------------
# Keyed by OSV ecosystem, then normalised package name. `by_advisory` overrides `default` for that CVE/GHSA id.

_SEED: dict[str, dict[str, dict]] = {
    "PyPI": {
        "pyyaml": {
            "import_names": ["yaml"],
            "default": ["yaml.load", "yaml.load_all", "yaml.full_load", "yaml.full_load_all", "yaml.unsafe_load",
                        "yaml.unsafe_load_all", "yaml.FullLoader", "yaml.UnsafeLoader"],
            "notes": "yaml.safe_load, yaml.safe_load_all and Loader=yaml.SafeLoader are not affected.",
        },
        "jinja2": {
            "import_names": ["jinja2"],
            "default": ["jinja2.Template", "jinja2.Environment.from_string", "jinja2.Environment.get_template",
                        "jinja2.sandbox.SandboxedEnvironment", "jinja2.utils.urlize", "jinja2.filters.do_xmlattr"],
            "notes": "Rendering fixed template files with trusted data is not affected; user-controlled templates and keys are.",
        },
        "requests": {
            "import_names": ["requests"],
            "default": ["requests.get", "requests.post", "requests.put", "requests.delete", "requests.request",
                        "requests.Session", "requests.Session.request", "requests.utils.get_netrc_auth"],
            "notes": "Requests to trusted hosts without proxies, redirects or netrc credentials are lower risk.",
        },
        "urllib3": {
            "import_names": ["urllib3"],
            "default": ["urllib3.PoolManager", "urllib3.ProxyManager", "urllib3.PoolManager.request",
                        "urllib3.HTTPConnectionPool.urlopen", "urllib3.request", "urllib3.util.retry.Retry"],
            "notes": "Requests that never follow redirects or use proxies are not affected by the redirect advisories.",
        },
        "werkzeug": {
            "import_names": ["werkzeug"],
            "default": ["werkzeug.utils.secure_filename", "werkzeug.serving.run_simple",
                        "werkzeug.debug.DebuggedApplication", "werkzeug.formparser.parse_form_data",
                        "werkzeug.datastructures.MultiDict"],
            "notes": "The debugger advisories only apply when debug mode is enabled.",
        },
        "flask": {
            "import_names": ["flask"],
            "default": ["flask.Flask", "flask.session", "flask.Flask.run"],
            "notes": "Apps that do not use sessions or run with the dev server are less exposed.",
        },
    },
    "npm": {
        "lodash": {
            "import_names": ["lodash", "_"],
            "default": ["_.template", "lodash.template", "template"],
            "notes": "Calls that never pass user-controlled data to these functions are not affected.",
            "by_advisory": {
                "CVE-2021-23337": ["_.template", "lodash.template", "template"],
                "CVE-2026-4800": ["_.template", "lodash.template", "template"],
                "CVE-2020-8203": ["_.zipObjectDeep", "lodash.zipObjectDeep", "zipObjectDeep",
                                  "_.set", "lodash.set", "set"],
            },
        },
    },
}


def _normalise(package: str, ecosystem: str) -> str:
    """L2: PyYAML / pyyaml / Py_YAML all map to one key. Other ecosystems keep their exact name."""
    return str(canonicalize_name(package)) if ecosystem == "PyPI" else package


def _seed(vuln: RawVuln) -> VulnSymbols | None:
    entry = _SEED.get(vuln.ecosystem, {}).get(_normalise(vuln.package, vuln.ecosystem))
    if entry is None:
        return None
    symbols = entry["default"]
    for advisory_id in (vuln.cve_id, *vuln.aliases):
        if advisory_id in entry.get("by_advisory", {}):
            symbols = entry["by_advisory"][advisory_id]
            break
    return VulnSymbols(package=vuln.package, import_names=list(entry["import_names"]), symbols=list(symbols),
                       safe_usage_notes=entry["notes"], confidence=0.9)


# --- cache ---------------------------------------------------------------------------------------------------

def _key(vuln: RawVuln) -> str:
    return f"{vuln.cve_id}|{vuln.ecosystem}|{_normalise(vuln.package, vuln.ecosystem)}"


def _db_get(key: str) -> VulnSymbols | None:
    try:
        with Session(get_engine()) as s:
            row = s.get(SymbolCacheRow, key)
        return VulnSymbols.model_validate_json(row.result_json) if row else None
    except (SQLAlchemyError, ValidationError) as e:
        logger.warning("symbol cache read failed: %s", redact(e))
        return None


def _db_put(key: str, result: VulnSymbols) -> None:
    try:
        with Session(get_engine()) as s:
            s.merge(SymbolCacheRow(key=key, result_json=result.model_dump_json(),
                                   created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")))
            s.commit()
    except SQLAlchemyError as e:
        logger.warning("symbol cache write failed: %s", redact(e))


# --- extraction ----------------------------------------------------------------------------------------------

def _clean(names: list[str]) -> list[str]:
    """Keep only identifier-shaped names (an advisory cannot smuggle prose into later prompts); dedupe, cap."""
    out: list[str] = []
    for n in names:
        n = n.strip()
        if n and len(n) <= MAX_NAME_LEN and _NAME.match(n) and n not in out:
            out.append(n)
    return out[:MAX_SYMBOLS]


def _finish(vuln: RawVuln, result: VulnSymbols, seed: VulnSymbols | None) -> VulnSymbols:
    """L3: import names always include the seed's (PyYAML -> yaml); symbols are sanitised."""
    imports = _clean(result.import_names + (seed.import_names if seed else []))
    return VulnSymbols(package=vuln.package, import_names=imports, symbols=_clean(result.symbols),
                       safe_usage_notes=result.safe_usage_notes[:500],
                       confidence=min(max(result.confidence, 0.0), 1.0))


def _variables(vuln: RawVuln) -> dict[str, str]:
    """S7 + E10: only advisory text leaves the box (never repo code), capped and redacted."""
    return {
        "ecosystem": vuln.ecosystem,
        "package": vuln.package,
        "cve_id": vuln.cve_id,
        "summary": redact(vuln.summary)[:MAX_SUMMARY_CHARS],
        "details": redact(vuln.details)[:MAX_DETAILS_CHARS],
        "references": "\n".join(redact(r) for r in vuln.references[:MAX_REFERENCES]),
    }


async def extract(vuln: RawVuln) -> VulnSymbols:
    """Turn the advisory text into the fully-qualified functions that are dangerous (e.g. `yaml.load`).

    Falls back to the seed map when the LLM is unsure or unavailable. `LLM_MODE=mock` uses the seed map only.
    """
    key = _key(vuln)
    if key in _memory:
        return _memory[key]
    cached = _db_get(key)
    if cached is not None:
        _memory[key] = cached
        return cached

    seed = _seed(vuln)
    if get_settings().llm_mode == "mock":
        result = _finish(vuln, seed, seed) if seed else VulnSymbols(
            package=vuln.package, confidence=0.0, safe_usage_notes="mock mode: no seed entry for this package")
    else:
        try:
            ai = await llm.complete_json("extract_symbols", _variables(vuln), VulnSymbols)
        except LLMError as e:
            logger.warning("symbols %s: LLM failed (%s); using seed map", vuln.cve_id, redact(e))
            # not cached, so the next scan retries the LLM
            return seed or VulnSymbols(package=vuln.package, confidence=0.0,
                                       safe_usage_notes="AI unavailable and no seed entry")
        result = _finish(vuln, ai, seed)
        if seed and (not result.symbols or result.confidence < MIN_CONFIDENCE):
            result = _finish(vuln, seed, seed)

    _memory[key] = result
    _db_put(key, result)
    return result
