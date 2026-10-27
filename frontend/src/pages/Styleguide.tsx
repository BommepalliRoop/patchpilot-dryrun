import { useState, type ReactNode } from 'react'
import { Inbox } from 'lucide-react'
import PageShell from '../components/PageShell'
import { KevFlame, ModeBadge, PriorityBadge, ReachabilityChip, ReconnectingBanner, StatusPill } from '../components/ui/Badges'
import CodeViewer from '../components/ui/CodeViewer'
import DiffViewer from '../components/ui/DiffViewer'
import GlassCard from '../components/ui/GlassCard'
import Modal from '../components/ui/Modal'
import PipelineStepper from '../components/ui/PipelineStepper'
import StatCard from '../components/ui/StatCard'
import { EmptyState, ErrorState, Skeleton } from '../components/ui/States'
import Timeline from '../components/ui/Timeline'
import { useToast } from '../components/ui/Toast'
import { mockFindingDetail } from '../lib/mock'

const PRIORITIES = ['P1', 'P2', 'P3', 'P4', 'P9']
const REACH = ['reachable', 'unsure', 'not_reachable', 'something_new']
const STATUSES = ['open', 'fixing', 'fixed', 'needs_human', 'ignored', 'brand_new']
const STAGE_SAMPLES: { label: string; current?: string; failed?: boolean }[] = [
  { label: 'Not started' },
  { label: 'Running: reachability', current: 'reachability' },
  { label: 'Failed at fix', current: 'fix', failed: true },
  { label: 'Done', current: 'done' },
]

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={`sg-${title}`} className="mb-10">
      <h2 id={`sg-${title}`} className="mb-3 text-xl font-semibold">
        {title}
      </h2>
      {children}
    </section>
  )
}

// Every component in all its states (acceptance criterion). Unknown enum values show the neutral fallback (E15).
export default function Styleguide() {
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const ev = mockFindingDetail.evidence[0]
  const btn =
    'rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-sm text-fg hover:bg-white/5 focus-visible:outline-2 focus-visible:outline-accent'

  return (
    <PageShell title="Styleguide" subtitle="Every design-system component in every state.">
      <Section title="Stat cards">
        <div className="grid grid-cols-4 gap-4">
          <StatCard label="Alerts scanned" value={39} />
          <StatCard label="Real risks" value={2} hint="reachable" />
          <StatCard label="Mean time to fix" value={4.5} decimals={1} suffix="min" />
          <StatCard label="No data yet" value={null} />
        </div>
      </Section>

      <Section title="Badges and chips">
        <div className="flex flex-wrap items-center gap-3">
          {PRIORITIES.map((p) => <PriorityBadge key={p} priority={p} />)}
          <PriorityBadge priority={undefined} />
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          {REACH.map((r) => <ReachabilityChip key={r} reachability={r} />)}
          <KevFlame />
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          {STATUSES.map((s) => <StatusPill key={s} status={s} />)}
        </div>
        <div className="mt-3 flex w-64 flex-col gap-2 rounded-xl border border-border p-3">
          <ModeBadge label="LLM" mode="mock" />
          <ModeBadge label="Boomi" mode="live" />
          <ModeBadge label="GitHub" />
        </div>
      </Section>

      <Section title="Pipeline stepper">
        <div className="flex flex-col gap-6">
          {STAGE_SAMPLES.map((s) => (
            <GlassCard key={s.label}>
              <div className="mb-3 text-sm text-muted">{s.label}</div>
              <PipelineStepper current={s.current} failed={s.failed} />
            </GlassCard>
          ))}
        </div>
        <div className="mt-4">
          <ReconnectingBanner show />
        </div>
      </Section>

      <Section title="Code viewer">
        <CodeViewer code={ev.code_snippet} file={ev.file} line={ev.start_line + 2} startLine={ev.start_line} inRoute={ev.in_route} />
        <div className="mt-3">
          <CodeViewer code={'<img src=x onerror="alert(1)">  # rendered as text, never as HTML'} file="notes.txt" />
        </div>
      </Section>

      <Section title="Diff viewer">
        <DiffViewer diff={mockFindingDetail.fix?.patch_diff} />
        <div className="mt-3">
          <DiffViewer diff="" />
        </div>
      </Section>

      <Section title="Timeline">
        <GlassCard glow>
          <Timeline items={mockFindingDetail.timeline} />
        </GlassCard>
        <div className="mt-3">
          <Timeline items={[]} />
        </div>
      </Section>

      <Section title="Empty, loading and error states">
        <div className="grid grid-cols-3 gap-4">
          <EmptyState title="No scans yet" hint="Run your first scan to see real risks." icon={<Inbox size={26} />} />
          <div className="flex flex-col gap-3">
            <Skeleton className="h-6 w-2/3" />
            <Skeleton className="h-24" />
            <Skeleton className="h-6 w-1/2" />
          </div>
          <ErrorState message="Cannot reach the PatchPilot backend. Check your connection and retry." onRetry={() => toast.info('Retrying…')} />
        </div>
      </Section>

      <Section title="Modal and toasts">
        <div className="flex gap-3">
          <button className={btn} onClick={() => setOpen(true)}>Open modal</button>
          <button className={btn} onClick={() => toast.success('Scan started')}>Success toast</button>
          <button className={btn} onClick={() => toast.info('Fix is running')}>Info toast</button>
          <button className={btn} onClick={() => toast.error(new Error('boom'), () => toast.success('Retried'))}>Error toast + retry</button>
        </div>
        <Modal open={open} onClose={() => setOpen(false)} title="Example dialog">
          <p className="text-sm text-muted">Esc, backdrop click and the close button all dismiss this dialog. Focus stays inside.</p>
          <div className="mt-4 flex justify-end">
            <button className={btn} onClick={() => setOpen(false)}>Close</button>
          </div>
        </Modal>
      </Section>
    </PageShell>
  )
}
