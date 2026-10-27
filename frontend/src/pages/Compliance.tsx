import { useState, type FormEvent } from 'react'
import { Download } from 'lucide-react'
import PageShell from '../components/PageShell'
import GlassCard from '../components/ui/GlassCard'
import { PriorityBadge, StatusPill } from '../components/ui/Badges'
import { EmptyState, ErrorState, Skeleton } from '../components/ui/States'
import { useToast } from '../components/ui/Toast'
import { getCompliance } from '../lib/api'
import { safeUrl } from '../lib/findingView'
import { complianceCsv } from '../lib/integrations'
import { useLoad } from '../lib/useLoad'

const DEFAULT_CLIENT = 'Acme Retail'

interface Filter {
  client: string
  from: string
}

const fmtTime = (iso?: string | null) => (iso ? new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '—')

const inputCls =
  'rounded-lg border border-border bg-surface px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-accent'

export default function Compliance() {
  const [draft, setDraft] = useState<Filter>({ client: DEFAULT_CLIENT, from: '' })
  const [applied, setApplied] = useState<Filter>({ client: DEFAULT_CLIENT, from: '' })
  const report = useLoad(
    () => getCompliance(applied.client || undefined, applied.from || undefined),
    [applied.client, applied.from],
  )
  const toast = useToast()
  const items = report.data?.items ?? []

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setApplied({ client: draft.client.trim(), from: draft.from })
  }

  const exportCsv = () => {
    if (!report.data) return
    const blob = new Blob([complianceCsv(report.data)], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const slug = report.data.client_name.toLowerCase().replace(/[^a-z0-9]+/g, '-')
    const a = document.createElement('a')
    a.href = url
    a.download = `compliance-${slug}-${applied.from || 'all'}.csv`
    a.click()
    URL.revokeObjectURL(url)
    toast.success(`Exported ${items.length} ${items.length === 1 ? 'row' : 'rows'}`)
  }

  return (
    <PageShell title="Compliance" subtitle="Audit trail per client from Boomi B4.">
      <div className="flex flex-col gap-6">
        <GlassCard>
          <form onSubmit={submit} className="flex flex-wrap items-end gap-4">
            <label className="flex flex-col gap-1 text-xs text-muted">
              Client
              <input
                className={`${inputCls} min-w-[220px]`}
                value={draft.client}
                onChange={(e) => setDraft({ ...draft, client: e.target.value })}
                placeholder={DEFAULT_CLIENT}
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-muted">
              From
              <input type="date" className={inputCls} value={draft.from} onChange={(e) => setDraft({ ...draft, from: e.target.value })} />
            </label>
            <button
              type="submit"
              className="rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-white/5 focus-visible:outline-2 focus-visible:outline-accent"
            >
              Apply
            </button>
            <button
              type="button"
              onClick={exportCsv}
              disabled={!report.data || items.length === 0}
              className="ml-auto inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg hover:brightness-110 disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-accent"
            >
              <Download size={14} aria-hidden /> Export CSV
            </button>
          </form>
        </GlassCard>

        {report.error && <ErrorState message={report.error} onRetry={report.reload} />}

        {!report.data ? (
          report.loading ? <Skeleton className="h-64" /> : null
        ) : items.length === 0 ? (
          <EmptyState title="No compliance entries" hint="Nothing was detected or fixed for this client in the selected range." />
        ) : (
          <GlassCard>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[960px] border-collapse text-left text-sm">
                <thead className="text-xs tracking-wide text-muted uppercase">
                  <tr className="border-b border-border">
                    {['Detected', 'CVE', 'Package', 'Priority', 'Jira', 'Pull request', 'Time to fix', 'Status'].map((h) => (
                      <th key={h} scope="col" className="px-3 py-2 font-medium">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => {
                    const pr = safeUrl(item.pr_url)
                    return (
                      <tr key={item.compliance_log_id} className="border-b border-border/60 hover:bg-white/5">
                        <td className="px-3 py-2.5 text-muted">{fmtTime(item.detected_at)}</td>
                        <td className="px-3 py-2.5 font-mono text-xs">{item.cve_id}</td>
                        <td className="px-3 py-2.5 font-mono text-xs">{item.package}</td>
                        <td className="px-3 py-2.5"><PriorityBadge priority={item.priority} /></td>
                        <td className="px-3 py-2.5 font-mono text-xs">{item.jira_key ?? '—'}</td>
                        <td className="px-3 py-2.5">
                          {pr ? (
                            <a href={pr} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                              View PR
                            </a>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td className="px-3 py-2.5 tabular-nums">
                          {item.time_to_fix_minutes === null || item.time_to_fix_minutes === undefined ? '—' : `${item.time_to_fix_minutes} min`}
                        </td>
                        <td className="px-3 py-2.5"><StatusPill status={item.status} /></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </GlassCard>
        )}
      </div>
    </PageShell>
  )
}
