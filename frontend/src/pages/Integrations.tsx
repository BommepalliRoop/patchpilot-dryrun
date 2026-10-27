import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Plug } from 'lucide-react'
import PageShell from '../components/PageShell'
import GlassCard from '../components/ui/GlassCard'
import { EmptyState, ErrorState, Skeleton } from '../components/ui/States'
import { listIntegrationActivity } from '../lib/api'
import { freshEventIds, PROCESSES, processHealth, type ProcessHealth } from '../lib/integrations'
import type { IntegrationEvent } from '../lib/types'
import { useLoad } from '../lib/useLoad'

const POLL_MS = 3000

const DOT: Record<ProcessHealth, string> = { ok: 'bg-success', failed: 'bg-danger', unknown: 'bg-muted' }
const DOT_LABEL: Record<ProcessHealth, string> = {
  ok: 'Last call ok',
  failed: 'Last call failed',
  unknown: 'No calls yet',
}

const fmtTime = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })

export default function Integrations() {
  const activity = useLoad(() => listIntegrationActivity(50), [])
  const { data, reload } = activity
  const prevRef = useRef<IntegrationEvent[] | null>(null)
  const [fresh, setFresh] = useState<Set<number>>(new Set())

  // Poll every 3 s. Failed polls keep the last good data on screen (RISKS E14).
  useEffect(() => {
    const id = window.setInterval(reload, POLL_MS)
    return () => window.clearInterval(id)
  }, [reload])

  // Mark events that arrived since the last poll so the feed can animate them in.
  useEffect(() => {
    if (!data) return
    setFresh(freshEventIds(prevRef.current, data))
    prevRef.current = data
  }, [data])

  const events = data ?? []

  return (
    <PageShell title="Integrations" subtitle="Boomi processes B1–B4 and recent activity.">
      <div className="flex flex-col gap-6">
        {activity.error && <ErrorState message={activity.error} onRetry={reload} />}

        {!data ? (
          <div className="grid grid-cols-4 gap-4" aria-busy="true" aria-label="Loading integrations">
            {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-28" />)}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
            {PROCESSES.map((p) => {
              const health = processHealth(events, p.id)
              return (
                <GlassCard key={p.id}>
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-sm text-accent">{p.id}</span>
                    <span
                      role="img"
                      aria-label={DOT_LABEL[health]}
                      title={DOT_LABEL[health]}
                      className={`h-2.5 w-2.5 rounded-full ${DOT[health]}`}
                    />
                  </div>
                  <div className="mt-3 font-medium">{p.name}</div>
                  <div className="text-xs text-muted">{p.direction}</div>
                </GlassCard>
              )
            })}
          </div>
        )}

        <GlassCard>
          <h2 className="mb-3 text-xl font-semibold">Recent activity</h2>
          {!data ? (
            <Skeleton className="h-48" />
          ) : events.length === 0 ? (
            <EmptyState
              icon={<Plug size={26} />}
              title="No integration calls yet"
              hint="Boomi events appear here as soon as a scan notifies them."
            />
          ) : (
            <ul className="flex flex-col divide-y divide-border/60" aria-live="polite">
              <AnimatePresence initial={false}>
                {events.map((e) => (
                  <motion.li
                    key={e.id}
                    layout
                    initial={fresh.has(e.id) ? { opacity: 0, y: -8, backgroundColor: 'rgb(94 234 212 / 0.12)' } : false}
                    animate={{ opacity: 1, y: 0, backgroundColor: 'rgb(94 234 212 / 0)' }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.4 }}
                    className="flex items-center gap-3 py-2.5 text-sm"
                  >
                    <span className={`h-2 w-2 shrink-0 rounded-full ${e.ok ? 'bg-success' : 'bg-danger'}`} aria-hidden />
                    <span className="sr-only">{e.ok ? 'ok' : 'failed'}</span>
                    <span className="w-8 font-mono text-xs text-accent">{e.process}</span>
                    <span className="min-w-0 flex-1 truncate">{e.summary || e.endpoint}</span>
                    <span className="font-mono text-xs text-muted">{e.status_code ?? '—'}</span>
                    <time dateTime={e.created_at} className="text-xs text-muted tabular-nums">
                      {fmtTime(e.created_at)}
                    </time>
                  </motion.li>
                ))}
              </AnimatePresence>
            </ul>
          )}
        </GlassCard>
      </div>
    </PageShell>
  )
}
