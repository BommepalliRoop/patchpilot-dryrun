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
- Implement docs/ARCHITECTURE.md Fix engine. Work dir `/tmp/patchpilot/<scan_id>/fix-<finding_id>`; one fix per **package** covering all its routed CVEs; git branch `patchpilot/<package>-<new-version>`. Venv created once per fix; retries only re-run pytest. Cross-platform venv paths (`bin/` vs `Scripts\`).
- Version bump preserves requirement formatting/comments; picks the smallest fixed version greater than installed. If `pip install` itself fails (not the tests), try the next fixed/newer releases up to the latest (max 3 tries) before giving up — e.g. PyYAML 5.4 / 5.4.1 do not build on Python 3.11+ with Cython 3, 6.0.1+ installs fine (checked Oct 27).
- Test run in isolated venv with timeouts (install 180 s, pytest 120 s); capture output tail (last 200 lines).
- Prompt `prompts/patch_code.md`: input {package, old→new version, failing test output, relevant file contents}; output `{diff (unified), explanation}`; apply with `git apply --3way`, reject edits outside the repo.
- Max 2 AI attempts; final status fixed | needs_human; store patch_diff (full diff vs base).

## Acceptance criteria
- On the demo repo: upgrade that breaks one call gets fixed by the AI patch in mock mode (canned diff) and tests pass.
- Never leaves the original clone modified.

## Hardening (docs/RISKS.md)
Implement and test these rows: S2, S6, S7, S14, N4, E7, E10, E11, E12, E13, L1, L2, L5, L7.

## Rules
- Follow CLAUDE.md and docs/API_CONTRACTS.md exactly. Stay inside this task's scope.
- Use mock modes for anything another lane has not finished.

## When done
Update `tasks/STATUS.md`, commit `T08: Fix engine (upgrade, test, AI patch loop)`, push, and print the NEXT block.
