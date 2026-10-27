import type { ReactNode } from 'react'
import { AlertTriangle, Inbox, RefreshCw } from 'lucide-react'

/** Empty state with an illustration-style icon (never a blank area). */
export function EmptyState({ title, hint, icon, action }: { title: string; hint?: string; icon?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-border px-6 py-12 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-full bg-accent/10 text-accent">{icon ?? <Inbox size={26} />}</div>
      <div className="text-base font-medium">{title}</div>
      {hint && <p className="max-w-sm text-sm text-muted">{hint}</p>}
      {action}
    </div>
  )
}

/** Error state with retry (E14). Pages with last-good data show this as a banner above it. */
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex items-center gap-3 rounded-xl border border-danger/40 bg-danger/10 px-4 py-3 text-sm">
      <AlertTriangle size={18} className="shrink-0 text-danger" />
      <span className="flex-1">{message}</span>
      {onRetry && (
        <button
          onClick={onRetry}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-fg hover:bg-white/5 focus-visible:outline-2 focus-visible:outline-accent"
        >
          <RefreshCw size={14} /> Retry
        </button>
      )}
    </div>
  )
}

export function Skeleton({ className = '' }: { className?: string }) {
  return <div aria-hidden className={`animate-pulse rounded-lg bg-white/10 ${className}`} />
}
