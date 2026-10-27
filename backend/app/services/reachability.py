"""Stage 4 — reachability (T06). Python: `ast` ("deep"); other languages: text search + AI ("generic").

Deep (docs/ARCHITECTURE.md "Reachability algorithm"): walk `.py` files (skip venv/tests/migrations), build an import
alias map per file, resolve every call / reference to a dotted name, match against the vulnerable symbols, and mark
`in_route` when the enclosing function is a Flask/FastAPI route or is called (transitively) from one.

Generic ("Language support"): import regex per language, then a text search for the symbols in importing files.

Both send at most 5 redacted ±15-line snippets to the `reachability_verdict` prompt. AST evidence is authoritative
(RISKS S5): an unguarded call inside a route can only be lowered to `unsure`, never to `not_reachable`.
"""
from __future__ import annotations

import ast
import asyncio
import logging
import os
import re
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from app.core.security import redact
from app.models.domain import RawVuln, Verdict, VulnSymbols
from app.models.schemas import Evidence, Reachability
from app.services import llm
from app.services.ecosystems import DEEP_ECOSYSTEMS, SKIP_DIRS
from app.services.llm import LLMError

logger = logging.getLogger("patchpilot.reachability")

CONTEXT_LINES = 15             # snippet = call line ±15
MAX_PROMPT_SNIPPETS = 5        # E10
MAX_EVIDENCE = 20              # stored on the finding
MAX_LINE_CHARS = 300           # minified / generated lines are cut
MAX_SNIPPET_CHARS = 4000
MAX_FILE_BYTES = 1_000_000
MAX_FILES = 5000
READ_WORKERS = 8               # file opens dominate on Windows (antivirus); read in parallel
MAX_NOTES_CHARS = 500
MAX_EXPLANATION_CHARS = 600
GENERIC_CONFIDENCE_CAP = 0.8   # L11
NO_MATCH_CONFIDENCE = 0.9
SAFE_ONLY_CONFIDENCE = 0.85

SKIP_ANALYSIS_DIRS = SKIP_DIRS | frozenset({
    "env", "tests", "test", "testing", "__tests__", "spec", "migrations", "alembic", "build", "dist", "out",
    "coverage", "bower_components", ".eggs", ".mypy_cache", ".pytest_cache", ".next",
})
_PY_TEST_FILE = re.compile(r"^(?:test_.*|.*_test|conftest)\.py$")
_GENERIC_TEST_FILE = re.compile(r"(?:\.(?:test|spec)\.[jt]sx?|_test\.go|Tests?\.(?:java|kt|cs)|_spec\.rb|\.min\.js)$")

ROUTE_DECORATORS = frozenset({"route", "get", "post", "put", "patch", "delete", "head", "options", "websocket",
                              "api_route"})
SAFE_YAML_LOADERS = frozenset({"SafeLoader", "CSafeLoader", "BaseLoader", "CBaseLoader"})
TEMPLATE_FACTORIES = frozenset({"Template", "from_string"})

# Generic analyzer: language name, source extensions, import regexes (`{n}` = escaped import name).
_LANGUAGES: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    "npm": ("JavaScript/TypeScript", (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue", ".svelte"), (
        r"""\brequire\(\s*['"`]{n}(?:/[^'"`]*)?['"`]\s*\)""",
        r"""\bfrom\s+['"]{n}(?:/[^'"]*)?['"]""",
        r"""\bimport\s+['"]{n}(?:/[^'"]*)?['"]""",
        r"""\bimport\(\s*['"]{n}(?:/[^'"]*)?['"]\s*\)""",
    )),
    "Maven": ("Java/Kotlin", (".java", ".kt", ".kts", ".scala", ".groovy"), (
        r"^\s*import\s+(?:static\s+)?{n}\b",
    )),
    "Go": ("Go", (".go",), (r'"{n}(?:/[^"]*)?"',)),
    "crates.io": ("Rust", (".rs",), (
        r"\buse\s+(?:::)?{n}\b", r"\bextern\s+crate\s+{n}\b", r"(?<![\w:]){n}::",
    )),
    "Packagist": ("PHP", (".php",), (r"(?i)^\s*use\s+\\?{n}\\", r"(?i)\\?{n}\\\w+::")),
    "NuGet": (".NET (C#/F#/VB)", (".cs", ".fs", ".vb"), (r"^\s*(?:using|open|Imports)\s+(?:static\s+)?{n}\b",)),
    "RubyGems": ("Ruby", (".rb",), (r"""^\s*require(?:_relative)?\s*\(?\s*['"]{n}(?:/[^'"]*)?['"]""",)),
}
_GENERIC_ROUTE = re.compile(
    r"\b(?:app|router|server|api|routes?)\.(?:get|post|put|patch|delete|all|use|route)\s*\("
    r"|@(?:Get|Post|Put|Patch|Delete|Request)Mapping\b|@(?:GET|POST|PUT|PATCH|DELETE|Path)\b"
    r"|\[Http(?:Get|Post|Put|Patch|Delete)\b|\bHandleFunc\s*\(|\.(?:GET|POST|PUT|PATCH|DELETE)\s*\("
    r"|\bRoute::(?:get|post|put|patch|delete|any|match)\s*\(|^\s*(?:get|post|put|patch|delete)\s+['\"]/",
    re.MULTILINE)
_COMMENT_PREFIXES = ("//", "#", "*", "/*", "--")

# S7: secrets that `redact()` does not know (assignments, cloud keys, PEM blocks) are masked before code leaves the box.
_SECRET_ASSIGN = re.compile(
    r"""(?i)(\b[\w-]*(?:password|passwd|pwd|secret|token|api[_-]?key|apikey|private[_-]?key|access[_-]?key"""
    r"""|credential|auth)[\w-]*['"]?\s*(?:=|:|=>)\s*)(['"])[^'"\n]{3,}\2""")
_AWS_KEY = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
_PEM = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.DOTALL)
_DELIMITER = re.compile(r"=====\s*(?:BEGIN|END) UNTRUSTED CODE", re.IGNORECASE)


class LLMVerdict(BaseModel):
    """Shape of the `reachability_verdict` prompt output."""

    reachability: Reachability
    confidence: float
    explanation: str = ""


@dataclass
class _Hit:
    file: str
    line: int
    symbol: str
    in_route: bool = False
    safe_reason: str | None = None
    lines: list[str] = field(default_factory=list, repr=False)

    def evidence(self) -> Evidence:
        start, snippet = _snippet(self.lines, self.line)
        return Evidence(file=self.file, line=self.line, in_route=self.in_route, code_snippet=snippet,
                        start_line=start)


# --- shared helpers ------------------------------------------------------------------------------------------

def mask_secrets(text: str) -> str:
    """S7: mask likely secrets in a code snippet before it is stored or sent to the LLM."""
    text = _PEM.sub("***PRIVATE KEY***", text)
    text = _SECRET_ASSIGN.sub(lambda m: f"{m.group(1)}{m.group(2)}***{m.group(2)}", text)
    text = _AWS_KEY.sub("***", text)
    return redact(text)


def _snippet(lines: list[str], line: int) -> tuple[int, str]:
    start = max(1, line - CONTEXT_LINES)
    chunk = [ln if len(ln) <= MAX_LINE_CHARS else ln[:MAX_LINE_CHARS] + " ..." for ln in lines[start - 1:line + CONTEXT_LINES]]
    return start, mask_secrets("\n".join(chunk))[:MAX_SNIPPET_CHARS]


def _walk_files(repo: Path, extensions: tuple[str, ...], test_file: re.Pattern[str]) -> list[Path]:
    """Source files sorted by path; skips vendored, virtualenv, test and migration directories."""
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_ANALYSIS_DIRS and not d.startswith(".")
                             and not (Path(dirpath) / d / "pyvenv.cfg").exists())
        for name in sorted(filenames):
            if name.endswith(extensions) and not test_file.search(name):
                p = Path(dirpath) / name
                try:
                    if p.stat().st_size <= MAX_FILE_BYTES:
                        out.append(p)
                except OSError:
                    continue
                if len(out) >= MAX_FILES:
                    return out
    return out


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _read_all(paths: list[Path]) -> list[tuple[Path, str]]:
    with ThreadPoolExecutor(max_workers=READ_WORKERS) as pool:
        return [(p, t) for p, t in zip(paths, pool.map(_read, paths), strict=True) if t is not None]


def _rel(repo: Path, path: Path) -> str:
    return path.relative_to(repo).as_posix()


def _sorted_hits(hits: list[_Hit]) -> list[_Hit]:
    """Dedupe by file:line (a line is safe only if every match on it is) and put the riskiest first."""
    by_loc: dict[tuple[str, int], _Hit] = {}
    for h in hits:
        prev = by_loc.get((h.file, h.line))
        if prev is None:
            by_loc[(h.file, h.line)] = h
        else:
            prev.in_route = prev.in_route or h.in_route
            prev.safe_reason = prev.safe_reason if (prev.safe_reason and h.safe_reason) else None
    return sorted(by_loc.values(), key=lambda h: (h.safe_reason is not None, not h.in_route, h.file, h.line))


def _where(h: _Hit) -> str:
    return f"{h.file}:{h.line}"


def _cap(v: Verdict) -> Verdict:
    """L11: generic verdicts are capped and say how they were made."""
    if v.analysis == "generic":
        v.confidence = min(v.confidence, GENERIC_CONFIDENCE_CAP)
        if "text + AI analysis" not in v.explanation:
            v.explanation = f"{v.explanation.rstrip()} (text + AI analysis)".strip()
    v.confidence = round(min(max(v.confidence, 0.0), 1.0), 2)
    return v


# --- verdict -------------------------------------------------------------------------------------------------

def _format_evidence(hits: list[_Hit], analysis: str) -> str:
    """S5: each snippet is wrapped in delimiters; marker text inside the code is neutralised."""
    blocks = []
    for h in hits[:MAX_PROMPT_SNIPPETS]:
        e = h.evidence()
        code = _DELIMITER.sub("= = = (marker removed)", e.code_snippet)
        found_by = "Python AST" if analysis == "deep" else "text search"
        facts = (f"matched symbol: {h.symbol}; inside HTTP route handler: {'yes' if h.in_route else 'no'}; "
                 f"known safe pattern: {h.safe_reason or 'none'}; found by: {found_by}")
        blocks.append(f"===== BEGIN UNTRUSTED CODE {e.file}:{e.line} (lines from {e.start_line}) =====\n{code}\n"
                      f"===== END UNTRUSTED CODE =====\nFacts: {facts}")
    return "\n\n".join(blocks)


async def _verdict(vuln: RawVuln, symbols: VulnSymbols, hits: list[_Hit], language: str, analysis: str) -> Verdict:
    evidence = [h.evidence() for h in hits[:MAX_EVIDENCE]]
    unsafe_route = next((h for h in hits if h.in_route and not h.safe_reason), None)

    if all(h.safe_reason for h in hits):
        h = hits[0]
        return _cap(Verdict(reachable="not_reachable", confidence=SAFE_ONLY_CONFIDENCE, evidence=evidence,
                            analysis=analysis,  # type: ignore[arg-type]
                            explanation=f"Every use of {h.symbol} follows a known safe pattern: {h.safe_reason} "
                                        f"({_where(h)}), so the vulnerable code path is not reachable."))

    variables = {
        "language": language,
        "package": vuln.package,
        "cve_id": vuln.cve_id,
        "advisory": redact(vuln.summary)[:MAX_NOTES_CHARS],
        "symbols": ", ".join(symbols.symbols[:20]),
        "safe_usage_notes": redact(symbols.safe_usage_notes)[:MAX_NOTES_CHARS] or "none",
        "evidence": _format_evidence(hits, analysis),
    }
    try:
        ai = await llm.complete_json("reachability_verdict", variables, LLMVerdict)
    except LLMError as e:
        logger.warning("reachability %s: AI verdict unavailable (%s)", vuln.cve_id, redact(e))
        h = unsafe_route or next(x for x in hits if not x.safe_reason)
        return _cap(Verdict(reachable="unsure", confidence=0.6 if unsafe_route else 0.5, evidence=evidence,
                            analysis=analysis,  # type: ignore[arg-type]
                            explanation=f"AI verdict unavailable; {h.symbol} is called at {_where(h)}"
                                        f"{' inside an HTTP route' if h.in_route else ''} without a known safe pattern."))

    reach: Reachability = ai.reachability
    confidence = ai.confidence
    explanation = redact(ai.explanation)[:MAX_EXPLANATION_CHARS]
    if reach == "not_reachable" and unsafe_route is not None:  # S5: AST evidence outranks the model
        reach, confidence = "unsure", 0.6
        explanation = (f"{unsafe_route.symbol} is called at {_where(unsafe_route)} inside an HTTP route without a "
                       f"known safe pattern, so the AI's 'not reachable' was downgraded to 'unsure'. AI said: {explanation}")
    return _cap(Verdict(reachable=reach, confidence=confidence, evidence=evidence, explanation=explanation,
                        analysis=analysis))  # type: ignore[arg-type]


def _no_symbols(vuln: RawVuln, imported: bool, analysis: str) -> Verdict:
    if not imported:
        return _not_imported(vuln, analysis)
    return _cap(Verdict(reachable="unsure", confidence=0.5, analysis=analysis,  # type: ignore[arg-type]
                        explanation=f"{vuln.package} is imported, but the vulnerable functions of {vuln.cve_id} are "
                                    "unknown, so its use could not be checked."))


def _not_imported(vuln: RawVuln, analysis: str) -> Verdict:
    return _cap(Verdict(reachable="not_reachable", confidence=NO_MATCH_CONFIDENCE, analysis=analysis,  # type: ignore[arg-type]
                        explanation=f"{vuln.package} is never imported and not called directly by application code "
                                    "(a transitive or unused dependency; a framework may still use it internally)."))


def _no_calls(vuln: RawVuln, symbols: VulnSymbols, analysis: str) -> Verdict:
    """L9: framework-internal use (e.g. Werkzeug via Flask) is invisible to us; say so honestly."""
    names = ", ".join(symbols.symbols[:4]) + (", ..." if len(symbols.symbols) > 4 else "")
    return _cap(Verdict(reachable="not_reachable", confidence=NO_MATCH_CONFIDENCE, analysis=analysis,  # type: ignore[arg-type]
                        explanation=f"No call to {names} found: {vuln.package} is not called directly by application "
                                    "code (a framework may still use it internally)."))


# --- deep analyzer (Python AST) ------------------------------------------------------------------------------

def _module_name(repo: Path, path: Path) -> tuple[str, bool]:
    parts = list(path.relative_to(repo).with_suffix("").parts)
    is_package = parts[-1] == "__init__"
    if is_package:
        parts = parts[:-1]
    return ".".join(parts) or "__main__", is_package


def _canonical(name: str) -> str:
    """`jinja2.environment.Environment.from_string` ~ `jinja2.Environment.from_string` (re-exported submodules)."""
    parts = name.split(".")
    if len(parts) <= 2:
        return name
    middle = [p for p in parts[1:-1] if not p.islower()]
    return ".".join([parts[0], *middle, parts[-1]])


@dataclass
class _Module:
    name: str
    path: Path
    rel: str
    tree: ast.Module
    lines: list[str]
    names: dict[str, str]                 # local name -> dotted name (imports, assignments, own defs)
    imports: dict[str, str]               # local name -> dotted name (imports only)
    parents: dict[int, ast.AST]
    functions: dict[str, tuple[int, int]]  # function key -> (first line incl. decorators, last line)
    routes: set[str]
    refs: dict[str, set[str]]             # function key -> dotted names it calls or references
    imported_roots: set[str]


class _Resolver:
    def __init__(self, names: dict[str, str]) -> None:
        self.names = names

    def __call__(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return self.names.get(node.id)
        if isinstance(node, ast.Attribute):
            base = self(node.value)
            return f"{base}.{node.attr}" if base else None
        if isinstance(node, ast.Call):
            f = node.func
            if (isinstance(f, ast.Name) and f.id == "getattr" and "getattr" not in self.names
                    and len(node.args) >= 2):
                base = self(node.args[0])
                if not base:
                    return None
                attr = node.args[1]
                if isinstance(attr, ast.Constant) and isinstance(attr.value, str):
                    return f"{base}.{attr.value}"
                return f"{base}.<dynamic>"
            return self(f)  # an instance: jinja2.Environment().from_string -> jinja2.Environment.from_string
        return None


def _import_names(tree: ast.Module, module: str, is_package: bool) -> dict[str, str]:
    names: dict[str, str] = {}
    pkg_parts = module.split(".") if is_package else module.split(".")[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    names[a.asname] = a.name
                else:
                    root = a.name.split(".")[0]
                    names[root] = root
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base_parts = pkg_parts[:len(pkg_parts) - (node.level - 1)] if node.level > 1 else pkg_parts
                base = ".".join([*base_parts, *([node.module] if node.module else [])])
            else:
                base = node.module or ""
            if not base:
                continue
            for a in node.names:
                if a.name != "*":
                    names[a.asname or a.name] = f"{base}.{a.name}"
    return names


def _parse_module(repo: Path, path: Path, text: str) -> _Module | None:
    try:
        tree = ast.parse(text, filename=str(path))
    except (SyntaxError, ValueError, RecursionError):
        return None
    module, is_package = _module_name(repo, path)
    names: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names[node.name] = f"{module}.{node.name}"
    imports = _import_names(tree, module, is_package)
    names.update(imports)
    resolve = _Resolver(names)
    for _ in range(2):  # `env = jinja2.Environment()`, `loader = yaml.load`, `y = yaml` (two passes for chains)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                target, value = node.targets[0].id, node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
                target, value = node.target.id, node.value
            else:
                continue
            r = resolve(value)
            # a call result is tracked only when it is an instance (`env = Environment()`), never a return value
            if r and target not in imports and (not isinstance(value, ast.Call) or r.split(".")[-1][:1].isupper()):
                names[target] = r

    parents = {id(c): p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}
    functions: dict[str, tuple[int, int]] = {}
    routes: set[str] = set()
    refs: dict[str, set[str]] = {}

    def add_function(fn: ast.FunctionDef | ast.AsyncFunctionDef, key: str, owner: str | None) -> None:
        first = min([fn.lineno, *(d.lineno for d in fn.decorator_list)])
        functions[key] = (first, fn.end_lineno or fn.lineno)
        local = _Resolver({**names, "self": owner, "cls": owner} if owner else names)
        if any(_is_route_decorator(d) for d in fn.decorator_list):
            routes.add(key)
        refs[key] = {r for n in ast.walk(fn) if isinstance(n, (ast.Name, ast.Attribute))
                     and isinstance(n.ctx, ast.Load) and (r := local(n))}

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            add_function(node, f"{module}.{node.name}", None)
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    add_function(item, f"{module}.{node.name}.{item.name}", f"{module}.{node.name}")
    for node in ast.walk(tree):  # Flask: app.add_url_rule("/x", "x", view) / view_func=view
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_url_rule"):
            view = next((k.value for k in node.keywords if k.arg == "view_func"),
                        node.args[2] if len(node.args) >= 3 else None)
            if view is not None and (r := resolve(view)):
                routes.add(r)

    return _Module(name=module, path=path, rel=_rel(repo, path), tree=tree, lines=text.splitlines(), names=names,
                   imports=imports, parents=parents, functions=functions, routes=routes, refs=refs,
                   imported_roots={v.split(".")[0] for v in imports.values()})


def _is_route_decorator(d: ast.expr) -> bool:
    target = d.func if isinstance(d, ast.Call) else d
    return isinstance(target, ast.Attribute) and target.attr in ROUTE_DECORATORS


def _safe_reason(call: ast.Call, resolved: str, resolve: _Resolver) -> str | None:
    """Known safe patterns, checked on the AST (comments cannot fake them — RISKS S5)."""
    loader = next((k.value for k in call.keywords if k.arg == "Loader"), call.args[1] if len(call.args) >= 2 else None)
    if resolved.split(".")[0] == "yaml" and loader is not None:
        name = resolve(loader) or (loader.id if isinstance(loader, ast.Name) else "")
        if name.split(".")[-1] in SAFE_YAML_LOADERS:
            return f"Loader={name.split('.')[-1]}"
    if resolved.split(".")[-1] in TEMPLATE_FACTORIES and resolved.split(".")[0] == "jinja2":
        source = call.args[0] if call.args else next((k.value for k in call.keywords if k.arg == "source"), None)
        if isinstance(source, ast.Constant) and isinstance(source.value, str):
            return "fixed template string, not user-controlled"
    return None


def _route_reachable(modules: list[_Module]) -> set[str]:
    """Functions that are routes or are called / referenced (transitively) from a route."""
    lookup: dict[str, str] = {}
    graph: dict[str, set[str]] = {}
    starts: set[str] = set()
    for m in modules:
        parts = m.name.split(".")
        for key in m.functions:
            local = key[len(m.name) + 1:]
            for i in range(len(parts)):  # src.pkg.mod.f is also known as pkg.mod.f and mod.f
                lookup.setdefault(".".join([*parts[i:], local]), key)
        graph.update(m.refs)
        starts |= m.routes
    seen = {lookup.get(s, s) for s in starts}
    queue = deque(seen)
    while queue:
        for ref in graph.get(queue.popleft(), ()):
            target = lookup.get(ref)
            if target and target not in seen:
                seen.add(target)
                queue.append(target)
    return seen


def _deep_scan(repo: Path, symbols: VulnSymbols) -> tuple[list[_Hit], bool]:
    roots = {n for n in symbols.import_names if n.isidentifier()} or {symbols.package.lower().replace("-", "_")}
    first_root = sorted(roots)[0]
    wanted: dict[str, str] = {}
    for s in symbols.symbols:
        full = s if s.split(".")[0] in roots else f"{first_root}.{s}"
        wanted.setdefault(full, s)
        wanted.setdefault(_canonical(full), s)

    def match(resolved: str) -> str | None:
        hit = wanted.get(resolved) or wanted.get(_canonical(resolved))
        if hit or not resolved.endswith(".<dynamic>"):
            return hit
        base = resolved[: -len(".<dynamic>")]  # getattr(yaml, name): any vulnerable symbol of that module
        return next((orig for full, orig in wanted.items() if full.startswith(base + ".")), None)

    files = _read_all(_walk_files(repo, (".py",), _PY_TEST_FILE))
    modules = [m for p, text in files if (m := _parse_module(repo, p, text))]
    imported = any(m.imported_roots & roots for m in modules)
    hits: list[tuple[_Module, _Hit]] = []
    for m in modules:
        if not m.imported_roots & roots:
            continue
        resolve, resolve_import = _Resolver(m.names), _Resolver(m.imports)
        for node in ast.walk(m.tree):
            if isinstance(node, ast.Call):
                resolved, line = resolve(node.func), node.lineno
            elif isinstance(node, (ast.Name, ast.Attribute)) and isinstance(node.ctx, ast.Load):
                parent = m.parents.get(id(node))
                if isinstance(parent, ast.Attribute) or (isinstance(parent, ast.Call) and parent.func is node):
                    continue  # only the longest chain counts; calls are handled above
                resolved, line = resolve_import(node), node.lineno  # `session["user"]`, `map(yaml.load, ...)`
            else:
                continue
            if resolved and (sym := match(resolved)):
                safe = _safe_reason(node, resolved, resolve) if isinstance(node, ast.Call) else None
                hits.append((m, _Hit(file=m.rel, line=line, symbol=sym, safe_reason=safe, lines=m.lines)))
    if hits:
        reachable = _route_reachable(modules)
        for m, h in hits:
            owner = next((k for k, (a, b) in m.functions.items() if a <= h.line <= b), None)
            h.in_route = owner is not None and owner in reachable
    return _sorted_hits([h for _, h in hits]), imported


# --- generic analyzer (text search) --------------------------------------------------------------------------

def _generic_import_names(vuln: RawVuln, symbols: VulnSymbols) -> list[str]:
    names = [n for n in symbols.import_names if len(n) > 1 and n not in {"_", "$"}]
    pkg = vuln.package
    if vuln.ecosystem == "Maven":  # Java packages rarely equal the groupId: com.fasterxml.jackson.core -> ...jackson
        group = pkg.split(":")[0]
        names += [group, group.rsplit(".", 1)[0]] if group.count(".") >= 2 else [group]
    elif vuln.ecosystem == "crates.io":
        names.append(pkg.replace("-", "_"))
    elif vuln.ecosystem == "Packagist":
        names.append(pkg.split("/")[0])
    else:
        names.append(pkg)
    return list(dict.fromkeys(names))


def _symbol_patterns(symbols: VulnSymbols) -> list[tuple[re.Pattern[str], str]]:
    out: list[tuple[re.Pattern[str], str]] = []
    for s in symbols.symbols:
        last = re.split(r"[.:#\\]+", s)[-1]
        if not last:
            continue
        e = re.escape(last)
        if last == s:  # bare function, e.g. `template(` after `import { template } from 'lodash'`
            out.append((re.compile(rf"(?<![\w$.]){e}\s*\("), s))
        else:          # any call of that member: `_.template(`, `mapper.readValue(`, `Foo::bar(`, `$x->bar(`
            out.append((re.compile(rf"(?:\.|::|->|\\){e}\s*\(|(?<![\w$]){re.escape(s)}\b"), s))
    return out


def _generic_scan(repo: Path, vuln: RawVuln, symbols: VulnSymbols) -> tuple[list[_Hit], bool]:
    _, extensions, templates = _LANGUAGES[vuln.ecosystem]
    imports = [re.compile(t.replace("{n}", re.escape(n)), re.MULTILINE)
               for n in _generic_import_names(vuln, symbols) for t in templates]
    patterns = _symbol_patterns(symbols)
    hits: list[_Hit] = []
    imported = False
    for path, text in _read_all(_walk_files(repo, extensions, _GENERIC_TEST_FILE)):
        if not any(p.search(text) for p in imports):
            continue
        imported = True
        lines = text.splitlines()
        rel = _rel(repo, path)
        for i, line in enumerate(lines, start=1):
            if line.lstrip().startswith(_COMMENT_PREFIXES):
                continue
            sym = next((s for p, s in patterns if p.search(line)), None)
            if sym:
                window = "\n".join(lines[max(0, i - 1 - CONTEXT_LINES):i])
                hits.append(_Hit(file=rel, line=i, symbol=sym, in_route=bool(_GENERIC_ROUTE.search(window)),
                                 lines=lines))
    return _sorted_hits(hits), imported


# --- entry point ---------------------------------------------------------------------------------------------

async def analyze(repo_path: Path, vuln: RawVuln, symbols: VulnSymbols) -> Verdict:
    """Decide whether application code calls the vulnerable symbols; return file:line evidence.

    No call-site matches -> `not_reachable` (confidence 0.9) without an LLM call. AST evidence is authoritative
    over LLM output (RISKS S5).
    """
    repo = Path(repo_path)
    if vuln.ecosystem in DEEP_ECOSYSTEMS:
        analysis, language = "deep", "Python"
        hits, imported = await asyncio.to_thread(_deep_scan, repo, symbols)
    elif vuln.ecosystem in _LANGUAGES:
        analysis, language = "generic", _LANGUAGES[vuln.ecosystem][0]
        hits, imported = await asyncio.to_thread(_generic_scan, repo, vuln, symbols)
    else:
        return _cap(Verdict(reachable="unsure", confidence=0.3, analysis="generic",
                            explanation=f"No source analyzer for the {vuln.ecosystem} ecosystem yet."))

    if not symbols.symbols:
        return _no_symbols(vuln, imported, analysis)
    if not hits:
        return _no_calls(vuln, symbols, analysis) if imported else _not_imported(vuln, analysis)
    return await _verdict(vuln, symbols, hits, language, analysis)
