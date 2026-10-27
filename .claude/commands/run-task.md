---
description: Implement one PatchPilot task end to end (usage: /run-task T06)
argument-hint: <task-id e.g. T06>
---
You are implementing PatchPilot task **$ARGUMENTS**.

1. Read `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/API_CONTRACTS.md`, `tasks/BOARD.md` and the task file `tasks/$ARGUMENTS-*.md`. For UI tasks also read `docs/UI_SPEC.md`.
2. Check `tasks/STATUS.md`. If a dependency is not `done`, continue only if you can use its mock mode or interface stub; say so clearly.
3. `git pull origin main`, create branch from the task file, set the task to `in_progress` in STATUS.md.
4. Make a short plan (max 8 bullets), then implement exactly the Scope. Do not edit files owned by other tasks except to wire your module in where the task says.
5. Write tests for each acceptance criterion and run them (`cd backend && pytest -q` or `cd frontend && npm run build`). Fix until green.
6. Update STATUS.md to `done` with a one-line note, commit `$ARGUMENTS: <title>`, push, and open a PR to main (or merge if the team agreed fast-merge).
7. End your reply with exactly this block:

```
✅ DONE: $ARGUMENTS — <title>
Tests: <passed/total>
Changed: <key files>
Mock/stub left in place: <none or list>
NEXT (unblocked now): <task ids + titles from BOARD.md whose dependencies are all done>
Suggested next for this lane: /run-task <id>  (model: <model from task file>)
```
