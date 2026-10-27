import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { AnimatePresence, motion } from 'motion/react'
import { ClipboardCheck, LayoutDashboard, Play, Plug, Search, ShieldCheck } from 'lucide-react'
import { USE_MOCK, getHealth } from '../lib/api'
import type { Health } from '../lib/types'
import { ModeBadge } from './ui/Badges'
import DemoReset from './DemoReset'

const NAV = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/integrations', label: 'Integrations', icon: Plug, end: false },
  { to: '/compliance', label: 'Compliance', icon: ClipboardCheck, end: false },
]

// App shell: sidebar (logo, nav, mode badges) + top bar + animated page transitions (fade + 8px slide, 250 ms).
export default function Layout() {
  const [health, setHealth] = useState<Health | null>(null)
  const search = useRef<HTMLInputElement>(null)
  const { pathname } = useLocation()
  const navigate = useNavigate()

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealth(null))
  }, [])

  // "/" focuses search (UI_SPEC keyboard rules); ignored while typing in a field.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if (e.key === '/' && !(t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) && !t?.isContentEditable) {
        e.preventDefault()
        search.current?.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  return (
    <div className="flex h-full">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-surface-2 focus:p-2">
        Skip to content
      </a>
      <DemoReset />
      <aside className="flex w-60 shrink-0 flex-col gap-6 border-r border-border bg-surface px-4 py-5">
        <div className="flex items-center gap-2 text-lg font-semibold">
          <ShieldCheck className="text-accent" size={22} aria-hidden />
          PatchPilot
        </div>
        <nav aria-label="Main" className="flex flex-col gap-1">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-accent ${
                  isActive ? 'bg-surface-2 text-accent' : 'text-muted hover:bg-surface-2 hover:text-fg'
                }`
              }
            >
              <Icon size={16} aria-hidden />
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
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-4 border-b border-border bg-surface/60 px-8 py-3 backdrop-blur-md">
          <label className="sr-only" htmlFor="client">
            Client
          </label>
          <select id="client" className="rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-sm text-fg">
            <option>All clients</option>
          </select>
          <div className="relative max-w-sm flex-1">
            <Search size={14} className="absolute top-1/2 left-3 -translate-y-1/2 text-muted" aria-hidden />
            <input
              ref={search}
              type="search"
              aria-label="Search findings (press / to focus)"
              placeholder="Search CVE or package   /"
              className="w-full rounded-lg border border-border bg-surface-2 py-1.5 pr-3 pl-8 text-sm text-fg placeholder:text-muted focus-visible:outline-2 focus-visible:outline-accent"
            />
          </div>
          <button
            onClick={() => navigate('/?run=1')}
            className="ml-auto inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-bg hover:brightness-110 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            <Play size={14} aria-hidden /> Run scan
          </button>
        </header>
        <main id="main" className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[1280px] px-8 py-8">
            <AnimatePresence mode="wait">
              <motion.div
                key={pathname}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.25 }}
              >
                <Outlet />
              </motion.div>
            </AnimatePresence>
          </div>
        </main>
      </div>
    </div>
  )
}
