import { parseDiff, type DiffKind } from '../../lib/ui'

const KIND: Record<DiffKind, string> = {
  add: 'bg-success/15 text-success',
  del: 'bg-danger/15 text-danger',
  hunk: 'text-accent',
  meta: 'text-muted',
  ctx: 'text-fg',
}

/** Unified diff. Lines render as text (S11), never as HTML. */
export default function DiffViewer({ diff }: { diff?: string | null }) {
  const lines = parseDiff(diff)
  if (!lines.length) return <div className="rounded-xl border border-border p-3 text-sm text-muted">No diff recorded.</div>
  return (
    <pre className="m-0 overflow-x-auto rounded-xl border border-border bg-[#0d1117] py-2 font-mono text-[13px]" aria-label="Patch diff">
      {lines.map((l, i) => (
        <div key={i} className={`whitespace-pre px-3 ${KIND[l.kind]}`}>
          {l.text || ' '}
        </div>
      ))}
    </pre>
  )
}
