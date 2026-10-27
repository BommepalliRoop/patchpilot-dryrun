import type { ReactNode } from 'react'

// Page heading + body. The page transition (fade + 8px slide) lives in Layout's AnimatePresence.
export default function PageShell({ title, subtitle, children }: { title: string; subtitle?: string; children?: ReactNode }) {
  return (
    <div>
      <h1 className="text-[28px] leading-tight font-semibold">{title}</h1>
      {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      <div className="mt-6">{children}</div>
    </div>
  )
}
