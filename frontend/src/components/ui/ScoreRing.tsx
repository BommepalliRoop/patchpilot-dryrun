import { motion } from 'motion/react'
import { ringModel } from '../../lib/findingView'

/** Animated 0–10 risk score ring. Reduced motion is handled by the app-level MotionConfig. */
export default function ScoreRing({ score, tone = 'text-accent' }: { score?: number | null; tone?: string }) {
  const r = 34
  const { value, circumference, offset } = ringModel(score, r)
  return (
    <div className="relative h-24 w-24 shrink-0" role="img" aria-label={`Risk score ${value.toFixed(1)} out of 10`}>
      <svg viewBox="0 0 80 80" className="h-full w-full -rotate-90">
        <circle cx="40" cy="40" r={r} fill="none" strokeWidth="6" className="stroke-white/10" />
        <motion.circle
          cx="40"
          cy="40"
          r={r}
          fill="none"
          strokeWidth="6"
          strokeLinecap="round"
          className={`stroke-current ${tone}`}
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 0.9, ease: 'easeOut' }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-[28px] leading-none font-semibold tabular-nums">{value.toFixed(1)}</span>
        <span className="text-[10px] text-muted">/ 10</span>
      </div>
    </div>
  )
}
