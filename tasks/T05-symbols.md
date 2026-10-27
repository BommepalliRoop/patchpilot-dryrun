# T05 — Vulnerable symbol extraction (AI)

| Field | Value |
|---|---|
| Owner lane | Dev B |
| Model | Sonnet 5.5 |
| Effort | medium |
| Wave | 2 |
| Depends on | T04 |
| Unblocks | T06 |
| Branch | `t05-symbols` |

## Goal
Turn an advisory into the exact functions that are dangerous.

## Scope
- Prompt `prompts/extract_symbols.md`: given package, CVE, summary, details and references, return `{package, import_names[], symbols[] (fully-qualified, e.g. yaml.load), safe_usage_notes, confidence}`. Rules: prefer public API names a user would call; include aliases; empty list if unknown.
- `symbols.extract(raw_vuln) -> VulnSymbols` with an in-memory + SQLite cache by CVE id.
- Seed a small static map for demo packages (pyyaml, jinja2, requests, urllib3, werkzeug, flask — the T15 pins) used when the LLM is unsure; in `LLM_MODE=mock` it is the source of truth.

- Works for every ecosystem: the prompt gets `ecosystem` and returns names as a developer of that language writes them (e.g. npm lodash → `_.template`, `lodash.template`, `template`). Seed map also covers npm `lodash` (CVE-2021-23337 / CVE-2026-4800 → `template`; CVE-2020-8203 → `zipObjectDeep`, `set`).

## Acceptance criteria
- For the demo CVEs, returns the expected symbols (unit tests with mock LLM).
- Cache hit avoids a second LLM call.

## Hardening (docs/RISKS.md)
Implement and test these rows: S7, E10, L2, L3.

## Rules
- Follow CLAUDE.md and docs/API_CONTRACTS.md exactly. Stay inside this task's scope.
- Use mock modes for anything another lane has not finished.

## When done
Update `tasks/STATUS.md`, commit `T05: Vulnerable symbol extraction (AI)`, push, and print the NEXT block.
