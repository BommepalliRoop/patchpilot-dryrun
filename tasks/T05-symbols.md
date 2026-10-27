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
- Seed a small static map for demo packages (pyyaml, jinja2, requests, urllib3, pillow) used when the LLM is unsure.

## Acceptance criteria
- For the demo CVEs, returns the expected symbols (unit tests with mock LLM).
- Cache hit avoids a second LLM call.

## Rules
- Follow CLAUDE.md and docs/API_CONTRACTS.md exactly. Stay inside this task's scope.
- Use mock modes for anything another lane has not finished.

## When done
Update `tasks/STATUS.md`, commit `T05: Vulnerable symbol extraction (AI)`, push, and print the NEXT block.
