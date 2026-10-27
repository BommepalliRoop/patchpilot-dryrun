import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import PageShell from '../components/PageShell'
import { EvidenceCard, ExplanationCard, FixCard, IntegrationCard, ThreatChips } from '../components/FindingParts'
import GlassCard from '../components/ui/GlassCard'
import ScoreRing from '../components/ui/ScoreRing'
import Timeline from '../components/ui/Timeline'
import { PriorityBadge, ReachabilityChip, StatusPill } from '../components/ui/Badges'
import { ErrorState, Skeleton } from '../components/ui/States'
import { useToast } from '../components/ui/Toast'
import { getFinding, runFix } from '../lib/api'
import { analysisLabel, fixState, threatChips } from '../lib/findingView'
import { useLoad } from '../lib/useLoad'

const POLL_MS = 3000
const MAX_POLLS = 40

export default function FindingDetail() {
  const { id = '' } = useParams()
  const finding = useLoad(() => getFinding(id), [id])
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [polls, setPolls] = useState(0)
  const { reload } = finding
  const d = finding.data
  const status = d?.status

  // After a (re-)run the status is `fixing`; refresh until it settles, bounded so a stuck fix cannot poll forever.
  const pollsRef = useRef(0)
  pollsRef.current = polls
  useEffect(() => {
    if (status !== 'fixing' || pollsRef.current >= MAX_POLLS) return
    const t = setTimeout(() => {
      setPolls((n) => n + 1)
      void reload()
    }, POLL_MS)
    return () => clearTimeout(t)
  }, [status, polls, reload])

  async function rerun() {
    if (!d || busy) return
    setBusy(true)
    try {
      await runFix(d.finding_id)
      toast.success('Fix started. This page refreshes when it finishes.')
      setPolls(0)
      await reload()
    } catch (e) {
      toast.error(e, rerun)
    } finally {
      setBusy(false)
    }
  }

  if (finding.loading && !d) {
    return (
      <PageShell title="Finding">
        <div className="flex flex-col gap-4" aria-busy="true" aria-label="Loading finding">
          <Skeleton className="h-32" />
          <Skeleton className="h-64" />
        </div>
      </PageShell>
    )
  }
  if (!d) {
    return (
      <PageShell title="Finding">
        <ErrorState message={finding.error ?? 'Finding not found.'} onRetry={reload} />
        <p className="mt-4 text-sm">
          <Link to="/" className="text-accent underline">
            Back to overview
          </Link>
        </p>
      </PageShell>
    )
  }

  const analysis = analysisLabel(d.analysis)
  const state = fixState(d)
  const ringTone = d.priority === 'P1' ? 'text-danger' : d.priority === 'P2' ? 'text-warning' : 'text-accent'

  return (
    <PageShell
      title={d.cve_id || 'Finding'}
      subtitle={`${d.package} ${d.installed_version}${d.fixed_version ? ` → ${d.fixed_version}` : ''} · ${d.ecosystem}`}
    >
      <div className="flex flex-col gap-5">
        {finding.error && <ErrorState message={finding.error} onRetry={reload} />}
        <p className="text-sm">
          <Link to="/" className="inline-flex items-center gap-1 text-muted hover:text-fg">
            <ArrowLeft size={14} aria-hidden /> Overview
          </Link>
        </p>

        <GlassCard glow={d.priority === 'P1'}>
          <div className="flex flex-wrap items-center gap-5">
            <ScoreRing score={d.score} tone={ringTone} />
            <div className="flex min-w-0 flex-1 flex-col gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <PriorityBadge priority={d.priority} />
                <ReachabilityChip reachability={d.reachability} />
                <StatusPill status={d.status} />
                <ThreatChips chips={threatChips(d)} />
                {analysis && <span className="inline-flex rounded-full border border-border bg-white/5 px-2.5 py-0.5 text-xs">{analysis}</span>}
              </div>
              <p className="text-sm text-muted">
                CVSS <span className="font-mono text-fg">{d.cvss ?? '—'}</span> · confidence{' '}
                <span className="font-mono text-fg">{typeof d.confidence === 'number' ? `${Math.round(d.confidence * 100)}%` : '—'}</span>
                {d.kev_date_added ? (
                  <>
                    {' '}
                    · on KEV since <span className="font-mono text-fg">{d.kev_date_added}</span>
                  </>
                ) : null}
              </p>
            </div>
          </div>
        </GlassCard>

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          <div className="flex min-w-0 flex-col gap-5">
            <ExplanationCard d={d} />
            <EvidenceCard evidence={d.evidence} reachability={d.reachability} />
          </div>
          <div className="flex min-w-0 flex-col gap-5">
            <FixCard d={d} state={state} onRerun={rerun} busy={busy} />
            <IntegrationCard d={d} />
            <GlassCard>
              <h2 className="mb-3 text-lg font-semibold">Timeline</h2>
              <Timeline items={d.timeline} />
            </GlassCard>
          </div>
        </div>
      </div>
    </PageShell>
  )
}
