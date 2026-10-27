import { motion } from 'motion/react'
import { Link, useNavigate } from 'react-router-dom'
import { EmptyState } from './ui/States'
import { KevFlame, PriorityBadge, ReachabilityChip, StatusPill } from './ui/Badges'
import { analysisLabel, ecosystemsOf, epssLabel, NO_FILTERS, type FindingFiltersState } from '../lib/scanView'
import type { FindingSummary, Priority, Reachability } from '../lib/types'

const select =
  'rounded-lg border border-border bg-surface-2 px-2.5 py-1.5 text-sm text-fg focus-visible:outline-2 focus-visible:outline-accent'

export function FindingFilters({ all, value, onChange }: {
  all: readonly FindingSummary[]
  value: FindingFiltersState
  onChange: (v: FindingFiltersState) => void
}) {
  const active = value.priority || value.reachability || value.ecosystem
  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filter findings">
      <select aria-label="Priority" className={select} value={value.priority} onChange={(e) => onChange({ ...value, priority: e.target.value as Priority | '' })}>
        <option value="">All priorities</option>
        {(['P1', 'P2', 'P3', 'P4'] as const).map((p) => <option key={p}>{p}</option>)}
      </select>
      <select aria-label="Reachability" className={select} value={value.reachability} onChange={(e) => onChange({ ...value, reachability: e.target.value as Reachability | '' })}>
        <option value="">All reachability</option>
        <option value="reachable">Reachable</option>
        <option value="unsure">Unsure</option>
        <option value="not_reachable">Not reachable</option>
      </select>
      <select aria-label="Ecosystem" className={select} value={value.ecosystem} onChange={(e) => onChange({ ...value, ecosystem: e.target.value })}>
        <option value="">All ecosystems</option>
        {ecosystemsOf(all).map((e) => <option key={e}>{e}</option>)}
      </select>
      {active && (
        <button onClick={() => onChange(NO_FILTERS)} className="text-sm text-accent underline focus-visible:outline-2 focus-visible:outline-accent">
          Clear filters
        </button>
      )}
    </div>
  )
}

/** CVE | package installed → fixed | ecosystem | priority | reachability | threat (KEV flame, EPSS on hover) | status. */
export default function FindingsTable({ findings, filtered }: { findings: readonly FindingSummary[]; filtered?: boolean }) {
  const navigate = useNavigate()
  if (!findings.length) {
    return (
      <EmptyState
        title={filtered ? 'No findings match these filters' : 'No findings yet'}
        hint={filtered ? 'Clear a filter to see more.' : 'Findings appear here as the scan scores them.'}
      />
    )
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[820px] border-collapse text-left text-sm">
        <thead className="text-xs tracking-wide text-muted uppercase">
          <tr className="border-b border-border">
            {['CVE', 'Package', 'Ecosystem', 'Priority', 'Reachability', 'Threat', 'Status'].map((h) => (
              <th key={h} scope="col" className="px-3 py-2 font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {findings.map((f, i) => (
            <motion.tr
              key={f.finding_id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25, delay: Math.min(i, 15) * 0.04 }}
              onClick={() => navigate(`/findings/${encodeURIComponent(f.finding_id)}`)}
              className="cursor-pointer border-b border-border/60 hover:bg-white/5"
            >
              <td className="px-3 py-2.5 font-mono">
                <Link to={`/findings/${encodeURIComponent(f.finding_id)}`} onClick={(e) => e.stopPropagation()} className="text-accent hover:underline focus-visible:outline-2 focus-visible:outline-accent">
                  {f.cve_id}
                </Link>
              </td>
              <td className="px-3 py-2.5">
                <span className="font-medium">{f.package}</span>{' '}
                <span className="font-mono text-xs text-muted">
                  {f.installed_version} → {f.fixed_version ?? 'no fix yet'}
                </span>
              </td>
              <td className="px-3 py-2.5">
                <span className="text-muted" title={analysisLabel(f.analysis)}>{f.ecosystem}</span>
              </td>
              <td className="px-3 py-2.5"><PriorityBadge priority={f.priority} /></td>
              <td className="px-3 py-2.5"><ReachabilityChip reachability={f.reachability} /></td>
              <td className="px-3 py-2.5">
                <span className="group relative inline-flex h-6 min-w-6 items-center justify-center" tabIndex={0} aria-label={epssLabel(f.epss_percentile, f.epss)}>
                  {f.kev ? <KevFlame /> : <span className="text-muted" aria-hidden>·</span>}
                  <span
                    role="tooltip"
                    className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1 -translate-x-1/2 rounded-md border border-border bg-surface-2 px-2 py-1 text-xs whitespace-nowrap opacity-0 transition-opacity group-focus:opacity-100 group-hover:opacity-100"
                  >
                    {f.kev && 'Actively exploited (CISA KEV) · '}
                    {epssLabel(f.epss_percentile, f.epss)}
                  </span>
                </span>
              </td>
              <td className="px-3 py-2.5"><StatusPill status={f.status} /></td>
            </motion.tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
