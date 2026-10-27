# T06 — Reachability analyzer (AST + AI)

| Field | Value |
|---|---|
| Owner lane | Dev B |
| Model | Opus 5.5 |
| Effort | high |
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

- **Generic analyzer for non-Python ecosystems** per docs/ARCHITECTURE.md "Language support": import regex table per language, symbol text search, snippets → same verdict prompt with the language named; package never imported → `not_reachable` without LLM; confidence capped at 0.8; `analysis: generic`. Python keeps the AST analyzer (`analysis: deep`).

## Acceptance criteria
- Tests on fixture code covering: direct call, aliased import, from-import alias, safe usage, no usage, call inside route.
- Runs in < 3 s on the demo repo excluding LLM time.

- Tests: JS file with `const _ = require('lodash'); _.template(userInput)` → reachable; JS repo where lodash is only in the lockfile → not_reachable, no LLM call.

## Hardening (docs/RISKS.md)
Implement and test these rows: S5, S7, E10, L3, L9, L11.

## Rules
- Follow CLAUDE.md and docs/API_CONTRACTS.md exactly. Stay inside this task's scope.
- Use mock modes for anything another lane has not finished.

## When done
Update `tasks/STATUS.md`, commit `T06: Reachability analyzer (AST + AI)`, push, and print the NEXT block.
