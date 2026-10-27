import PageShell from '../components/PageShell'

// Empty page — implemented in T12.
export default function Overview() {
  return (
    <PageShell title="Overview" subtitle="Alerts scanned, real risks and fixes across all clients.">
      <div className="rounded-2xl border border-dashed border-border p-10 text-center text-muted">
        Coming in T12
      </div>
    </PageShell>
  )
}
