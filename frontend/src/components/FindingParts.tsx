import type { ReactElement } from 'react'
import { AlertTriangle, CheckCircle2, ExternalLink, Flame, GitPullRequest, Loader2, MessageSquare, ShieldCheck, Ticket } from 'lucide-react'
import GlassCard from './ui/GlassCard'
import CodeViewer from './ui/CodeViewer'
import DiffViewer from './ui/DiffViewer'
import { EmptyState } from './ui/States'
import { formatAttempts, safeUrl, type FixState, type ThreatChip } from '../lib/findingView'
import type { Evidence, FindingDetail } from '../lib/types'

const chip = 'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap'

export function ThreatChips({ chips }: { chips: ThreatChip[] }) {
  return (
    <>
      {chips.map((c) => (
        <span key={c.key} className={`${chip} ${c.tone === 'danger' ? 'border-danger/50 bg-danger/15 text-danger' : 'border-border bg-white/5 text-fg'}`}>
          {c.key === 'kev' && <Flame size={12} aria-hidden />}
          {c.label}
        </span>
      ))}
    </>
  )
}

/** AI text is rendered as plain text only (RISKS S11). */
export function ExplanationCard({ d }: { d: FindingDetail }) {
  const symbols = d.vulnerable_symbols ?? []
  return (
    <GlassCard>
      <h2 className="mb-2 text-lg font-semibold">AI explanation</h2>
      {d.summary && <p className="mb-2 text-sm text-muted">{d.summary}</p>}
      <p className="text-[15px] whitespace-pre-wrap">{d.ai_explanation || 'No explanation recorded for this finding.'}</p>
      {symbols.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted">Vulnerable symbols</span>
          {symbols.map((s) => (
            <code key={s} className="rounded-md border border-border bg-white/5 px-2 py-0.5 font-mono text-xs">
              {s}
            </code>
          ))}
        </div>
      )}
    </GlassCard>
  )
}

export function EvidenceCard({ evidence, reachability }: { evidence?: Evidence[] | null; reachability: string }) {
  const items = evidence ?? []
  const none = reachability === 'not_reachable'
  return (
    <GlassCard>
      <h2 className="mb-3 text-lg font-semibold">Evidence</h2>
      {items.length === 0 ? (
        <EmptyState
          icon={<ShieldCheck size={26} />}
          title={none ? 'No call path to the vulnerable code' : 'No evidence recorded'}
          hint={
            none
              ? 'Nothing in this repository reaches the vulnerable symbols, so there is no code to show.'
              : 'The analyzer did not record a code location for this finding.'
          }
        />
      ) : (
        <div className="flex flex-col gap-3">
          {items.map((e, i) => (
            <CodeViewer key={`${e.file}:${e.line}:${i}`} code={e.code_snippet} file={e.file} line={e.line} startLine={e.start_line} inRoute={e.in_route} />
          ))}
        </div>
      )}
    </GlassCard>
  )
}

const FIX_BANNER: Record<FixState, { cls: string; icon: ReactElement; text: string } | null> = {
  none: null,
  fixing: { cls: 'border-accent/40 bg-accent/10 text-accent', icon: <Loader2 size={16} className="animate-spin" aria-hidden />, text: 'Fix in progress…' },
  fixed: { cls: 'border-success/40 bg-success/10 text-success', icon: <CheckCircle2 size={16} aria-hidden />, text: 'Fixed — tests passed' },
  untested: { cls: 'border-warning/50 bg-warning/15 text-warning', icon: <AlertTriangle size={16} aria-hidden />, text: 'Upgrade PR ready — tests not run' },
  needs_human: { cls: 'border-danger/50 bg-danger/15 text-danger', icon: <AlertTriangle size={16} aria-hidden />, text: 'Needs human — automatic fix did not pass tests' },
  failed: { cls: 'border-danger/50 bg-danger/15 text-danger', icon: <AlertTriangle size={16} aria-hidden />, text: 'Fix did not succeed' },
}

export function FixCard({ d, state, onRerun, busy }: { d: FindingDetail; state: FixState; onRerun: () => void; busy: boolean }) {
  const fix = d.fix
  const banner = FIX_BANNER[state]
  const pr = safeUrl(fix?.pr_url)
  const working = busy || state === 'fixing'
  return (
    <GlassCard>
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Fix</h2>
        <button
          onClick={onRerun}
          disabled={working}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm hover:bg-white/5 focus-visible:outline-2 focus-visible:outline-accent disabled:opacity-50"
        >
          {working ? <Loader2 size={14} className="animate-spin" aria-hidden /> : <GitPullRequest size={14} aria-hidden />}
          Re-run fix
        </button>
      </div>
      {banner && (
        <div role="status" className={`mb-3 flex items-center gap-2 rounded-lg border px-3 py-2 text-sm ${banner.cls}`}>
          {banner.icon}
          {banner.text}
        </div>
      )}
      {!fix ? (
        <p className="text-sm text-muted">
          {d.reachability === 'not_reachable' ? 'Not reachable, so no fix is needed right now.' : 'No fix has been attempted yet.'}
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          <dl className="grid grid-cols-3 gap-3 text-sm">
            <div>
              <dt className="text-xs text-muted">Upgrade to</dt>
              <dd className="font-mono">{fix.new_version || '—'}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted">Tests</dt>
              <dd>{state === 'untested' ? 'Not run' : fix.tests_passed ? 'Passed' : 'Failed'}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted">AI patch</dt>
              <dd>{formatAttempts(fix.attempts)}</dd>
            </div>
          </dl>
          {fix.patch_diff ? <DiffViewer diff={fix.patch_diff} /> : null}
          {pr ? (
            <a
              href={pr}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex w-fit items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-black hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              <GitPullRequest size={16} aria-hidden /> Open PR <ExternalLink size={13} aria-hidden />
            </a>
          ) : (
            <p className="text-sm text-muted">No pull request opened.</p>
          )}
        </div>
      )}
    </GlassCard>
  )
}

export function IntegrationCard({ d }: { d: FindingDetail }) {
  const i = d.integration
  const jira = safeUrl(i?.jira_url)
  return (
    <GlassCard>
      <h2 className="mb-3 text-lg font-semibold">Integrations</h2>
      {!i ? (
        <p className="text-sm text-muted">Boomi has not been notified about this finding.</p>
      ) : (
        <ul className="flex flex-col gap-3 text-sm">
          <li className="flex items-center gap-2">
            <Ticket size={16} className="text-muted" aria-hidden />
            <span className="text-muted">Jira</span>
            {i.jira_key ? (
              jira ? (
                <a href={jira} target="_blank" rel="noopener noreferrer" className="font-mono text-accent hover:underline">
                  {i.jira_key}
                </a>
              ) : (
                <span className="font-mono">{i.jira_key}</span>
              )
            ) : (
              <span className="text-muted">not created</span>
            )}
          </li>
          <li className="flex items-center gap-2">
            <MessageSquare size={16} className="text-muted" aria-hidden />
            <span className="text-muted">Slack</span>
            <span className={i.slack_sent ? 'text-success' : 'text-muted'}>{i.slack_sent ? 'Sent' : 'Not sent'}</span>
          </li>
          <li className="flex items-center gap-2">
            <ShieldCheck size={16} className="text-muted" aria-hidden />
            <span className="text-muted">Compliance log</span>
            <span className="font-mono">{i.compliance_log_id || '—'}</span>
          </li>
        </ul>
      )}
    </GlassCard>
  )
}
