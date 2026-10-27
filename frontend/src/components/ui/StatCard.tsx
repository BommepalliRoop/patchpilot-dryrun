import { useEffect, useState } from 'react'
import { animate, useReducedMotion } from 'motion/react'
import GlassCard from './GlassCard'

/** Number that counts up on mount (spring). Shows the final value under prefers-reduced-motion. */
export function CountUp({ value, decimals = 0 }: { value: number; decimals?: number }) {
  const reduced = useReducedMotion()
  const safe = Number.isFinite(value) ? value : 0
  const [shown, setShown] = useState(reduced ? safe : 0)
  useEffect(() => {
    if (reduced) {
      setShown(safe)
      return
    }
    const c = animate(0, safe, { type: 'spring', stiffness: 60, damping: 18, onUpdate: setShown })
    return () => c.stop()
  }, [safe, reduced])
  return <span className="tabular-nums">{shown.toFixed(decimals)}</span>
}

export default function StatCard({ label, value, decimals, suffix, hint }: {
  label: string
  value?: number | null
  decimals?: number
  suffix?: string
  hint?: string
}) {
  return (
    <GlassCard>
      <div className="text-sm text-muted">{label}</div>
      <div className="mt-2 text-[40px] font-semibold leading-none">
        {value == null ? '—' : <CountUp value={value} decimals={decimals} />}
        {value != null && suffix && <span className="ml-1 text-base text-muted">{suffix}</span>}
      </div>
      {hint && <div className="mt-2 text-xs text-muted">{hint}</div>}
    </GlassCard>
  )
}
