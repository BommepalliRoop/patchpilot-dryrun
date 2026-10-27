# UI spec — professional, motion-rich security console

## Look and feel
- Dark-first security console (light mode optional). Background `#0B0F17`, surfaces `#111827` / `#161E2E`,
  borders `rgba(255,255,255,0.08)`. Accent electric teal `#2DD4BF`; danger `#F43F5E`, warning `#F59E0B`, success `#22C55E`.
- Font: Inter (UI) + JetBrains Mono (code, CVE ids). Sizes 12/14/16/20/28/40. Weights 400/500/600.
- Glass cards: `backdrop-blur`, 1px border, 16px radius, subtle inner highlight. No harsh shadows.
- Icons: lucide-react. Charts: Recharts. Code: Shiki (theme `github-dark`) with highlighted evidence line.

## Motion (motion/react)
- Page transitions: fade + 8px slide, 250 ms.
- Stat counters count up on load (spring).
- The signature animation — **Noise funnel**: N alert dots (N = total_alerts, ~30 on the demo repo; cap at 40 dots) fall into a funnel and only 2 come out glowing red,
  then 1 turns into a "Fixed" green check. Drive it from real scan stats.
- Live pipeline stepper: 8 stages (clone → … → notify) light up as SSE events arrive; active stage pulses.
- Lists animate in with stagger 40 ms. Priority badges pulse once when they appear.
- Respect `prefers-reduced-motion`.

## Component libraries (use these, don't build from scratch)
- shadcn/ui — base components: Button, Table, Dialog, Tabs, Badge, Tooltip, Toast (sonner), Command palette.
- Magic UI / Aceternity UI — animated pieces: NumberTicker (hero stats), AnimatedBeam (pipeline flow between stages),
  BorderBeam / glowing card (P1 finding), animated grid background (hero), Marquee (live activity feed).
- Tremor or Recharts — stat cards, trend charts (alerts vs real risks over time).
- Copy components into `src/components/ui/` (shadcn style). Theme them with the tokens above.

## UX rules
- Every action gives instant feedback (optimistic state, toast, skeleton).
- One primary action per screen (Run scan). Clear empty, loading, error states.
- Keyboard: `/` focuses search, `Cmd/Ctrl+K` command palette, Shift+R demo reset.
- Readable from a projector: high contrast, large numbers, no tiny grey text on dark.

## Pages
1. **Overview** `/` — hero stats (alerts scanned, real risks, fixed, mean time to fix), Noise funnel, recent scans table,
   "Run scan" button (opens a modal: client, repo URL, branch, auto-fix toggle, optional owner email).
2. **Scan live view** `/scans/:id` — "Languages detected" strip (Python · deep, JavaScript · text + AI), live pipeline stepper, log stream (terminal style), findings table with filters
   (priority, reachability). Rows: CVE, package `installed → fixed`, priority badge, reachability chip, KEV flame icon, status.
3. **Finding detail** `/findings/:id` — header with CVE + score ring + threat chips ("Actively exploited (CISA KEV)", "EPSS top 7%"); left: AI explanation + evidence code viewer with the
   vulnerable line highlighted and "in route" tag; right: fix card (diff viewer, tests passed, attempts, PR button),
   integration card (Jira key link, Slack sent, compliance id), vertical timeline.
4. **Integrations** `/integrations` — Boomi process cards B1–B4 with health dots, activity feed of integration events.
5. **Compliance** `/compliance` — per-client table from B4 with time-to-fix, export CSV button.

## Layout
Left sidebar (logo "PatchPilot", nav, mode badges: LLM/Boomi/GitHub mock|live), top bar (client switcher, search, run scan),
content max-width 1280px. Responsive down to 1024px; mobile is not a priority.

## Demo-friendly details
- Big readable numbers (judges watch from a distance) — hero stats at 40px.
- "Demo mode" badge and a hidden reset button (Shift+R asks for the admin key, then calls `/api/demo/reset`; the key is never stored in the bundle).
- Empty states with illustration-style icons, never blank.
