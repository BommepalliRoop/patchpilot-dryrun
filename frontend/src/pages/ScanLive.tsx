import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { RotateCcw } from 'lucide-react'
import PageShell from '../components/PageShell'
import FindingsTable, { FindingFilters } from '../components/FindingsTable'
import { LanguageStrip, LogStream, ProgressBar } from '../components/ScanParts'
import GlassCard from '../components/ui/GlassCard'
import PipelineStepper from '../components/ui/PipelineStepper'
import { ReconnectingBanner, StatusPill } from '../components/ui/Badges'
import { EmptyState, ErrorState, Skeleton } from '../components/ui/States'
import { USE_MOCK, getScan, listFindings, replayMockRun, subscribeScanEvents } from '../lib/api'
import {
  appendLog, filterFindings, isActiveScan, NO_FILTERS, STAT_FIELDS, type FindingFiltersState, type LogLine,
} from '../lib/scanView'
import type { ScanEvent } from '../lib/types'
import { useLoad } from '../lib/useLoad'

export default function ScanLive() {
  const { id = '' } = useParams()
  const scan = useLoad(() => getScan(id), [id])
  const findings = useLoad(() => listFindings({ scan_id: id }), [id])
  const [log, setLog] = useState<LogLine[]>([])
  const [last, setLast] = useState<ScanEvent | null>(null)
  const [reconnecting, setReconnecting] = useState(false)
  const [filters, setFilters] = useState<FindingFiltersState>(NO_FILTERS)
  const lastStage = useRef<string | null>(null)
  const { reload: reloadScan } = scan
  const { reload: reloadFindings } = findings

  // Live: always subscribe against the real backend (its replay buffer rebuilds the log, RISKS N8); in mock mode only
  // while the scripted run is in progress, so finished fixtures do not replay for 25 s.
  const loaded = scan.data !== null
  const subscribe = loaded && (!USE_MOCK || isActiveScan(scan.data?.status))

  useEffect(() => {
    if (!subscribe) return
    const refresh = () => {
      void reloadScan()
      void reloadFindings()
    }
    return subscribeScanEvents(
      id,
      (ev) => {
        setReconnecting(false)
        setLast(ev)
        setLog((l) => appendLog(l, ev))
        if (ev.stage !== lastStage.current || ev.stage === 'done') {
          lastStage.current = ev.stage
          refresh() // stage change or done: keep stats and findings in step with the stream
        }
      },
      () => {
        setReconnecting(true) // EventSource retries by itself
        refresh()
      },
      () => {
        setReconnecting(false)
        refresh() // (re)connect: re-sync from the REST API
      },
    )
  }, [id, subscribe, reloadScan, reloadFindings])

  const all = findings.data ?? []
  const shown = useMemo(() => filterFindings(all, filters), [all, filters])
  const s = scan.data
  const stage = last?.stage ?? s?.current_stage
  const failed = s?.status === 'failed'
  const progress = s?.status === 'completed' ? 1 : (last?.progress ?? 0)

  function replay() {
    replayMockRun()
    lastStage.current = null
    setLog([])
    setLast(null)
    void reloadScan()
    void reloadFindings()
  }

  if (scan.loading && !s) {
    return (
      <PageShell title="Scan">
        <div className="flex flex-col gap-4" aria-busy="true" aria-label="Loading scan">
          <Skeleton className="h-24" />
          <Skeleton className="h-56" />
        </div>
      </PageShell>
    )
  }
  if (!s) {
    return (
      <PageShell title="Scan">
        <ErrorState message={scan.error ?? 'Scan not found.'} onRetry={reloadScan} />
        <p className="mt-4 text-sm"><Link to="/" className="text-accent underline">Back to overview</Link></p>
      </PageShell>
    )
  }

  return (
    <PageShell title={s.client_name} subtitle={`${s.repo_url.replace(/^https:\/\//, '')}@${s.branch} · ${s.scan_id}`}>
      <div className="flex flex-col gap-5">
        {(scan.error || findings.error) && (
          <ErrorState message={scan.error ?? findings.error ?? ''} onRetry={() => { void reloadScan(); void reloadFindings() }} />
        )}
        <ReconnectingBanner show={reconnecting} />

        <GlassCard>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <StatusPill status={s.status} />
              <LanguageStrip languages={s.languages} />
            </div>
            {USE_MOCK && !isActiveScan(s.status) && (
              <button onClick={replay} className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm hover:bg-white/5 focus-visible:outline-2 focus-visible:outline-accent">
                <RotateCcw size={14} aria-hidden /> Replay run
              </button>
            )}
          </div>
          <PipelineStepper current={stage} failed={failed} />
          <div className="mt-4"><ProgressBar progress={progress} /></div>
          <dl className="mt-4 grid grid-cols-5 gap-3">
            {STAT_FIELDS.map(({ key, label }) => (
              <div key={key}>
                <dt className="text-xs text-muted">{label}</dt>
                <dd className="text-xl font-semibold tabular-nums">{s.stats?.[key] ?? '—'}</dd>
              </div>
            ))}
          </dl>
        </GlassCard>

        <GlassCard>
          <h2 className="mb-3 text-lg font-semibold">Live log</h2>
          <LogStream lines={log} empty={isActiveScan(s.status) ? 'waiting for events…' : 'no events recorded for this scan'} />
        </GlassCard>

        <GlassCard>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">Findings <span className="text-muted">({shown.length}{shown.length !== all.length ? ` of ${all.length}` : ''})</span></h2>
            <FindingFilters all={all} value={filters} onChange={setFilters} />
          </div>
          {findings.loading && !findings.data ? (
            <Skeleton className="h-32" />
          ) : all.length === 0 ? (
            <EmptyState title="No findings yet" hint={isActiveScan(s.status) ? 'Findings appear here as the scan scores them.' : 'This scan found no vulnerable dependencies.'} />
          ) : (
            <FindingsTable findings={shown} filtered={all.length > 0} />
          )}
        </GlassCard>
      </div>
    </PageShell>
  )
}
