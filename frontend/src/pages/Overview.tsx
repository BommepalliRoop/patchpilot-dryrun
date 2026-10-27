import { useEffect } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { motion } from 'motion/react'
import { Play, ShieldCheck } from 'lucide-react'
import PageShell from '../components/PageShell'
import NoiseFunnel from '../components/NoiseFunnel'
import RunScanModal from '../components/RunScanModal'
import { RESET_EVENT } from '../components/DemoReset'
import GlassCard from '../components/ui/GlassCard'
import StatCard from '../components/ui/StatCard'
import { EmptyState, ErrorState, Skeleton } from '../components/ui/States'
import { StatusPill } from '../components/ui/Badges'
import { listScans } from '../lib/api'
import { aggregate, formatMinutes } from '../lib/scanView'
import { useLoad } from '../lib/useLoad'

const GRID_BG =
  'linear-gradient(rgb(255 255 255 / 0.04) 1px, transparent 1px), linear-gradient(90deg, rgb(255 255 255 / 0.04) 1px, transparent 1px)'

const fmtTime = (iso?: string | null) => (iso ? new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '—')

export default function Overview() {
  const scans = useLoad(listScans, [])
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const { reload } = scans

  // Demo reset (Shift+R) clears the DB; refetch so the page never shows stale scans.
  useEffect(() => {
    window.addEventListener(RESET_EVENT, reload)
    return () => window.removeEventListener(RESET_EVENT, reload)
  }, [reload])

  const openModal = params.get('run') === '1'
  const setModal = (open: boolean) => setParams(open ? { run: '1' } : {}, { replace: true })
  const list = scans.data ?? []
  const totals = aggregate(list)

  const runButton = (
    <button
      onClick={() => setModal(true)}
      className="inline-flex items-center gap-2 rounded-lg bg-accent px-5 py-2.5 text-sm font-semibold text-bg hover:brightness-110 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
    >
      <Play size={14} aria-hidden /> Run scan
    </button>
  )

  return (
    <PageShell title="Overview" subtitle="Alerts scanned, real risks and fixes across all clients.">
      <div className="flex flex-col gap-6">
        {scans.error && <ErrorState message={scans.error} onRetry={reload} />}

        {scans.loading && !scans.data ? (
          <div className="grid grid-cols-4 gap-4" aria-busy="true" aria-label="Loading overview">
            {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-32" />)}
          </div>
        ) : !scans.data ? null : list.length === 0 ? (
          <EmptyState
            icon={<ShieldCheck size={26} />}
            title="No scans yet"
            hint="Run your first scan to see which vulnerabilities are real and get fix pull requests."
            action={runButton}
          />
        ) : (
          <>
            <div className="grid grid-cols-4 gap-4">
              <StatCard label="Alerts scanned" value={totals.alerts} />
              <StatCard label="Real risks" value={totals.realRisks} hint="Reachable from your code" />
              <StatCard label="Fixed" value={totals.fixed} hint="Pull requests opened" />
              <StatCard
                label="Mean time to fix"
                value={totals.meanTimeToFixMin === null ? null : Number(totals.meanTimeToFixMin.toFixed(1))}
                suffix={totals.meanTimeToFixMin === null ? undefined : 'min'}
                hint={totals.meanTimeToFixMin === null ? 'No completed fixes yet' : formatMinutes(totals.meanTimeToFixMin)}
              />
            </div>

            <GlassCard className="relative overflow-hidden" style={{ backgroundImage: GRID_BG, backgroundSize: '32px 32px' }}>
              <div className="flex items-start justify-between">
                <div>
                  <h2 className="text-xl font-semibold">Noise funnel</h2>
                  <p className="text-sm text-muted">Every alert goes in. Only reachable, exploitable risks come out.</p>
                </div>
                {runButton}
              </div>
              <div className="mt-2 flex justify-center">
                <NoiseFunnel totals={totals} />
              </div>
            </GlassCard>

            <GlassCard>
              <h2 className="mb-3 text-xl font-semibold">Recent scans</h2>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px] border-collapse text-left text-sm">
                  <thead className="text-xs tracking-wide text-muted uppercase">
                    <tr className="border-b border-border">
                      {['Client', 'Repository', 'Status', 'Alerts', 'Real risks', 'Fixed', 'Started'].map((h) => (
                        <th key={h} scope="col" className="px-3 py-2 font-medium">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {list.map((s, i) => (
                      <motion.tr
                        key={s.scan_id}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.25, delay: Math.min(i, 15) * 0.04 }}
                        onClick={() => navigate(`/scans/${encodeURIComponent(s.scan_id)}`)}
                        className="cursor-pointer border-b border-border/60 hover:bg-white/5"
                      >
                        <td className="px-3 py-2.5 font-medium">
                          <Link
                            to={`/scans/${encodeURIComponent(s.scan_id)}`}
                            onClick={(e) => e.stopPropagation()}
                            className="text-accent hover:underline focus-visible:outline-2 focus-visible:outline-accent"
                          >
                            {s.client_name}
                          </Link>
                        </td>
                        <td className="px-3 py-2.5 font-mono text-xs text-muted">
                          {s.repo_url.replace(/^https:\/\//, '')}@{s.branch}
                        </td>
                        <td className="px-3 py-2.5"><StatusPill status={s.status} /></td>
                        <td className="px-3 py-2.5 tabular-nums">{s.stats?.total_alerts ?? '—'}</td>
                        <td className="px-3 py-2.5 tabular-nums">{s.stats?.reachable ?? '—'}</td>
                        <td className="px-3 py-2.5 tabular-nums">{s.stats?.fixed ?? '—'}</td>
                        <td className="px-3 py-2.5 text-muted">{fmtTime(s.started_at)}</td>
                      </motion.tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </GlassCard>
          </>
        )}
      </div>
      <RunScanModal open={openModal} onClose={() => setModal(false)} />
    </PageShell>
  )
}
