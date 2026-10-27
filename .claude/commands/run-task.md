---
description: Implement one PatchPilot task end to end (usage: /run-task T06)
argument-hint: <task-id e.g. T06>
---
You are implementing PatchPilot task **$ARGUMENTS**.

1. Read `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/API_CONTRACTS.md`, `tasks/BOARD.md` and the task file `tasks/$ARGUMENTS-*.md`. For UI tasks also read `docs/UI_SPEC.md`. Read the rows of `docs/RISKS.md` listed in the task's "Hardening" section — they are part of the scope and need tests too.
2. Check `tasks/STATUS.md`. If a dependency is not `done`, continue only if you can use its mock mode or interface stub; say so clearly.
3. `git pull origin main`, create branch from the task file, set the task to `in_progress` in STATUS.md.
4. Make a short plan (max 8 bullets), then implement exactly the Scope. Do not edit files owned by other tasks except to wire your module in where the task says.
5. Write tests for each acceptance criterion and run them (`cd backend && pytest -q` or `cd frontend && npm run build`). Fix until green.
6. Update STATUS.md to `done` with a one-line note, commit `$ARGUMENTS: <title>`, push, and open a PR to main (or merge if the team agreed fast-merge).
7. Work out the queue: re-read `tasks/STATUS.md` (after your update) and the "Task queue" table in `tasks/BOARD.md`. A task is unblocked when every task in its "Depends on" is `done` and it is still `todo`. Take model and effort from each task file's header table.
8. End your reply with exactly this block:

```
✅ DONE: $ARGUMENTS — <title>
Tests: <passed/total>
Changed: <key files>
Mock/stub left in place: <none or list>

NEXT (unblocked now):
- <id> <title> — lane <lane> — model <model> — effort <effort>
- ...

▶ Suggested next for this lane: <id> <title>
  1. Start a NEW Claude Code session (CLI: /clear or new `claude`; desktop app: New session)
  2. Set model: <model>   effort: <effort>   (/model picker or the app's model menu)
  3. Run: /run-task <id>
  (If the lane's next task is still blocked, say which dependency it waits on and suggest /next-task.)
```
