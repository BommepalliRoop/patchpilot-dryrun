import { motion } from 'motion/react'
import type { TimelineItem } from '../../lib/types'
import { humanize } from '../../lib/ui'

function when(at?: string): string {
  const d = at ? new Date(at) : null
  return d && !Number.isNaN(d.getTime()) ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''
}

/** Vertical timeline; messages are plain text (S11). Items stagger in at 40 ms. */
export default function Timeline({ items }: { items?: TimelineItem[] | null }) {
  if (!items?.length) return <p className="text-sm text-muted">No events yet.</p>
  return (
    <ol className="relative ml-2 border-l border-border">
      {items.map((it, i) => (
        <motion.li key={i} className="relative mb-4 ml-4" initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.04 }}>
          <span className="absolute top-1.5 -left-[21px] h-2.5 w-2.5 rounded-full bg-accent" aria-hidden />
          <div className="flex items-baseline gap-2">
            <span className="text-sm font-medium">{humanize(it.stage ?? '')}</span>
            <time className="font-mono text-xs text-muted">{when(it.at)}</time>
          </div>
          <p className="mt-0.5 whitespace-pre-wrap text-sm text-muted">{it.message}</p>
        </motion.li>
      ))}
    </ol>
  )
}
