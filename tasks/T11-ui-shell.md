# T11 — Design system and app shell

| Field | Value |
|---|---|
| Owner lane | Dev D |
| Model | Sonnet 5.5 |
| Effort | medium |
| Wave | 1 |
| Depends on | T00 |
| Unblocks | T12, T13, T14 |
| Branch | `t11-ui-shell` |

## Goal
Make it look like a premium security product from the first screen.

## Scope
- Tailwind theme tokens from docs/UI_SPEC.md; fonts Inter + JetBrains Mono.
- Components: GlassCard, StatCard (count-up), PriorityBadge, ReachabilityChip, StatusPill, ModeBadge, PipelineStepper, CodeViewer (Shiki, highlighted line), DiffViewer, Timeline, EmptyState, Skeleton, Modal, Toast.
- Layout: sidebar + top bar + animated page transitions (`AnimatePresence`).
- `prefers-reduced-motion` respected.

## Acceptance criteria
- A `/styleguide` route shows every component in all states.
- Lighthouse accessibility ≥ 90 on the styleguide page.

## Hardening (docs/RISKS.md)
Implement and test these rows: S11, E14, E15.

## Rules
- Follow CLAUDE.md and docs/API_CONTRACTS.md exactly. Stay inside this task's scope.
- Use mock modes for anything another lane has not finished.

## When done
Update `tasks/STATUS.md`, commit `T11: Design system and app shell`, push, and print the NEXT block.
