import type { ReactNode } from 'react'
import { motion } from 'motion/react'

// Page transition per docs/UI_SPEC.md: fade + 8px slide, 250 ms. (prefers-reduced-motion is handled in index.css.)
export default function PageShell({ title, subtitle, children }: { title: string; subtitle?: string; children?: ReactNode }) {
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
      <h1 className="text-[28px] font-semibold leading-tight">{title}</h1>
      {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      <div className="mt-6">{children}</div>
    </motion.div>
  )
}
