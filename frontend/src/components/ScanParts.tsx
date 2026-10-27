import { useEffect, useRef } from 'react'
import { motion } from 'motion/react'
import { Languages } from 'lucide-react'
import { languageLabel, progressPct, type LogLine } from '../lib/scanView'
import type { LanguageInfo } from '../lib/types'

/** "Languages detected" strip: `Python · deep`, `JavaScript · scan + AI`. */
export function LanguageStrip({ languages }: { languages?: readonly LanguageInfo[] }) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm" aria-label="Languages detected">
      <span className="inline-flex items-center gap-1.5 text-muted"><Languages size={14} aria-hidden /> Languages detected</span>
      {languages?.length ? (
        languages.map((l) => (
          <span
            key={l.ecosystem}
            title={l.manifests?.join(', ')}
            className={`rounded-full border px-2.5 py-0.5 font-mono text-xs ${l.analysis === 'deep' ? 'border-accent/40 bg-accent/10 text-accent' : 'border-border bg-white/5 text-fg'}`}
          >
            {languageLabel(l)}
          </span>
        ))
      ) : (
        <span className="text-muted">detecting…</span>
      )}
    </div>
  )
}

const TONE: Record<string, string> = { completed: 'text-success', failed: 'text-danger', error: 'text-danger' }

/** Terminal-style log; sticks to the bottom as lines arrive. */
export function LogStream({ lines, empty }: { lines: readonly LogLine[]; empty: string }) {
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = box.current
    if (el) el.scrollTop = el.scrollHeight
  }, [lines.length])
  return (
    <div
      ref={box}
      role="log"
      aria-label="Scan log"
      className="h-56 overflow-y-auto rounded-xl border border-border bg-black/40 p-3 font-mono text-[13px] leading-relaxed"
    >
      {lines.length === 0 && <div className="text-muted">$ {empty}</div>}
      {lines.map((l) => (
        <motion.div key={l.key} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.2 }} className="flex gap-3">
          <span className="shrink-0 text-muted">{new Date(l.at).toLocaleTimeString([], { hour12: false })}</span>
          <span className="w-24 shrink-0 text-accent">{l.stage}</span>
          <span className={TONE[l.status] ?? 'text-fg'}>{l.message}</span>
        </motion.div>
      ))}
    </div>
  )
}

export function ProgressBar({ progress }: { progress?: number | null }) {
  const pct = progressPct(progress)
  return (
    <div role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} aria-label="Scan progress" className="h-1.5 overflow-hidden rounded-full bg-white/10">
      <motion.div className="h-full rounded-full bg-accent" animate={{ width: `${pct}%` }} transition={{ duration: 0.5 }} />
    </div>
  )
}
