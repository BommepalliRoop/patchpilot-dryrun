import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { ClipboardCheck, LayoutDashboard, Plug, ShieldCheck } from 'lucide-react'
import { USE_MOCK, getHealth } from '../lib/api'
import type { Health } from '../lib/types'

const NAV = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/integrations', label: 'Integrations', icon: Plug, end: false },
  { to: '/compliance', label: 'Compliance', icon: ClipboardCheck, end: false },
]

function ModeBadge({ label, mode }: { label: string; mode?: string }) {
  const live = mode === 'live'
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-muted">{label}</span>
      <span
        className={`rounded-full border px-2 py-0.5 font-mono ${
          live ? 'border-success/40 text-success' : 'border-border text-muted'
        }`}
      >
        {mode ?? '…'}
      </span>
    </div>
  )
}

// App shell: sidebar (logo, nav, mode badges) + content (max 1280px). T11 turns this into the full design system.
export default function Layout() {
  const [health, setHealth] = useState<Health | null>(null)

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealth(null))
  }, [])

  return (
    <div className="flex h-full">
      <aside className="flex w-60 shrink-0 flex-col gap-6 border-r border-border bg-surface px-4 py-5">
        <div className="flex items-center gap-2 text-lg font-semibold">
          <ShieldCheck className="text-accent" size={22} />
          PatchPilot
        </div>
        <nav className="flex flex-col gap-1">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors ${
                  isActive ? 'bg-surface-2 text-accent' : 'text-muted hover:bg-surface-2 hover:text-fg'
                }`
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto flex flex-col gap-2 rounded-xl border border-border bg-surface-2 p-3">
          <ModeBadge label="LLM" mode={health?.llm_mode} />
          <ModeBadge label="Boomi" mode={health?.boomi_mode} />
          <ModeBadge label="GitHub" mode={health?.github_mode} />
          {USE_MOCK && <div className="pt-1 text-xs text-warning">UI fixtures (VITE_USE_MOCK)</div>}
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[1280px] px-8 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
