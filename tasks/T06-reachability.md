# T06 — Reachability analyzer (AST + AI)

| Field | Value |
|---|---|
| Owner lane | Dev B |
| Model | Opus 5.5 |
| Wave | 2 |
| Depends on | T04, T05 |
| Unblocks | T03, T17 |
| Branch | `t06-reachability` |

## Goal
Decide if our code really calls the vulnerable function. This is the core differentiator — be precise.

## Scope
- Implement the algorithm in docs/ARCHITECTURE.md (alias map, call resolution, `in_route` detection for Flask/FastAPI decorators, skip venv/tests/migrations, handle `from x import y as z`, attribute chains, `getattr` best-effort).
- Evidence: file (repo-relative), line, start_line, code_snippet (±15 lines), in_route.
- Prompt `prompts/reachability_verdict.md`: given symbols, safe_usage_notes and evidence snippets, return `{reachability, confidence, explanation}`; must recognise safe usage (e.g. `yaml.load(x, Loader=yaml.SafeLoader)`).
- No call-site matches → `not_reachable`, confidence 0.9, no LLM call.

## Acceptance criteria
- Tests on fixture code covering: direct call, aliased import, from-import alias, safe usage, no usage, call inside route.
- Runs in < 3 s on the demo repo excluding LLM time.

## Rules
- Follow CLAUDE.md and docs/API_CONTRACTS.md exactly. Stay inside this task's scope.
- Use mock modes for anything another lane has not finished.

## When done
Update `tasks/STATUS.md`, commit `T06: Reachability analyzer (AST + AI)`, push, and print the NEXT block.
