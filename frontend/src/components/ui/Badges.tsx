import { motion } from 'motion/react'
import { Flame } from 'lucide-react'
import { priorityTone, reachabilityTone, statusTone } from '../../lib/ui'

const base = 'inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap'

/** Pulses once when it appears. Unknown priority renders a neutral badge (E15). */
export function PriorityBadge({ priority }: { priority?: string | null }) {
  const tone = priorityTone(priority)
  return (
    <motion.span
      className={`${base} font-mono ${tone.cls}`}
      initial={{ scale: 0.8, opacity: 0 }}
      animate={{ scale: [0.8, 1.15, 1], opacity: 1 }}
      transition={{ duration: 0.4 }}
    >
      {tone.label}
    </motion.span>
  )
}

export function ReachabilityChip({ reachability }: { reachability?: string | null }) {
  const tone = reachabilityTone(reachability)
  return <span className={`${base} ${tone.cls}`}>{tone.label}</span>
}

export function StatusPill({ status }: { status?: string | null }) {
  const tone = statusTone(status)
  return (
    <span className={`${base} ${tone.cls}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />
      {tone.label}
    </span>
  )
}

export function KevFlame() {
  return (
    <span title="Actively exploited (CISA KEV)" role="img" aria-label="Actively exploited (CISA KEV)" className="text-danger">
      <Flame size={14} />
    </span>
  )
}

/** LLM / Boomi / GitHub mode: `live` green, anything else neutral. */
export function ModeBadge({ label, mode }: { label: string; mode?: string | null }) {
  const live = mode === 'live'
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-muted">{label}</span>
      <span className={`rounded-full border px-2 py-0.5 font-mono ${live ? 'border-success/40 text-success' : 'border-border text-muted'}`}>
        {mode ?? '…'}
      </span>
    </div>
  )
}

/** Shown when the SSE stream drops (E14). */
export function ReconnectingBanner({ show }: { show: boolean }) {
  if (!show) return null
  return (
    <div role="status" className="flex items-center gap-2 rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning">
      <span className="h-2 w-2 animate-pulse rounded-full bg-warning" aria-hidden />
      Reconnecting…
    </div>
  )
}
