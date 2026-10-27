# Task board — who runs what, in which order

## Lanes (dev team)
| Lane | Person | Tasks in order |
|---|---|---|
| Lead | Roop | T00 → (help) → T17 → T18 |
| Dev A — backend core | ___ | T01 → T02 → T03 |
| Dev B — AI | ___ | T04 → T05 → T07 → T06 |
| Dev C — fix + integration + deploy | ___ | T10 → T08 → T09 → T16 |
| Dev D — UI | ___ | T11 → T12 → T13 → T14 |
| Dev E / presenter (if you have a 5th dev) | ___ | T15 → demo prep; otherwise Lead does T15 right after T00 |
| Boomi team (3–4) | ___ | B2 → B1 → B3 → B4 (docs/BOOMI_HANDOFF.md) |

If you have fewer developers, merge lanes A+B or C+E. Never merge two UI tasks with backend tasks on one person.

## Waves (Oct 28)
| Wave | Time | Parallel tasks | Gate to next wave |
|---|---|---|---|
| 0 | 9:20–9:35 | T00 (Lead only). Others: install deps, paste kickoff keys into `.env`, Boomi team starts B2 | T00 merged to main |
| 1 | 9:35–10:30 | T01, T02, T04, T10, T11, T15, Boomi B2 | each task's acceptance passes |
| 2 | 10:30–11:20 | T03, T05, T07, T06, T08, T12, T13, Boomi B1 | pipeline runs end-to-end in mock mode |
| 3 | 11:20–11:50 | T09, T14, T16, Boomi B3/B4, switch BOOMI_MODE=live | public URLs + live Boomi |
| 4 | 11:50–12:15 | T17, T18 | two clean rehearsals |
| — | 12:20 | Code freeze | |

## Dependency graph
```
T00 ─┬─ T01 ─┐
     ├─ T02 ─┴─ T03 ───────────────┐
     ├─ T04 ─┬─ T05 ── T06 ────────┤
     │       └─ T08 ── T09 ────────┤
     ├─ T07 ───────────────────────┤
     ├─ T10 ───────────────────────┼── T17 ── T18
     ├─ T11 ─┬─ T12 ───────────────┤
     │       ├─ T13 ───────────────┤
     │       └─ T14 ───────────────┤
     ├─ T15 (separate repo) ───────┤
     └─ T16 (after T03 + T11) ─────┘
Boomi: B2 → B1 → B3 → B4  (contract-only dependency; mocks until live)
```

## Model guide
| Model | Use for | Tasks |
|---|---|---|
| Opus 5.5 | Hard reasoning, orchestration, tricky correctness | T03, T06, T08, T17 |
| Sonnet 5.5 | Normal feature work and UI | T00, T01, T02, T04, T05, T09, T10, T11, T12, T13, T16, T18 |
| Haiku 5.5 | Small, well-defined tasks | T07, T14, T15 |

In Claude Code: `/model` to switch before running a task.

## How to run a task
```
/run-task T06
```
or paste this prompt:
```
Read CLAUDE.md, docs/ARCHITECTURE.md, docs/API_CONTRACTS.md and tasks/T06-reachability.md.
Implement T06 exactly within its scope. Create branch t06-reachability. Mark it in_progress in tasks/STATUS.md.
Write tests for every acceptance criterion and run them. When all pass, update STATUS.md to done,
commit "T06: Reachability analyzer (AST + AI)", push, and end with the NEXT block.
```
When Claude ends, it prints which tasks are now unblocked. Run `/next-task` any time to see it again.
