# T08 — Fix engine (upgrade, test, AI patch loop)

| Field | Value |
|---|---|
| Owner lane | Dev C |
| Model | Opus 5.5 |
| Effort | high |
| Wave | 2 |
| Depends on | T04 |
| Unblocks | T09 |
| Branch | `t08-fixer` |

## Goal
Produce a tested fix on a branch.

## Scope
- Implement docs/ARCHITECTURE.md Fix engine. Work dir `/tmp/patchpilot/<scan_id>/fix-<finding_id>`; git branch `patchpilot/<cve>`.
- Version bump preserves requirement formatting/comments; picks the smallest fixed version greater than installed.
- Test run in isolated venv with timeouts (install 180 s, pytest 120 s); capture output tail (last 200 lines).
- Prompt `prompts/patch_code.md`: input {package, old→new version, failing test output, relevant file contents}; output `{diff (unified), explanation}`; apply with `git apply --3way`, reject edits outside the repo.
- Max 2 AI attempts; final status fixed | needs_human; store patch_diff (full diff vs base).

## Acceptance criteria
- On the demo repo: upgrade that breaks one call gets fixed by the AI patch in mock mode (canned diff) and tests pass.
- Never leaves the original clone modified.

## Rules
- Follow CLAUDE.md and docs/API_CONTRACTS.md exactly. Stay inside this task's scope.
- Use mock modes for anything another lane has not finished.

## When done
Update `tasks/STATUS.md`, commit `T08: Fix engine (upgrade, test, AI patch loop)`, push, and print the NEXT block.
