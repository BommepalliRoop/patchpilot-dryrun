import { motion } from 'motion/react'
import { Check, X } from 'lucide-react'
import { STAGES } from '../../lib/types'
import { humanize, stepStates } from '../../lib/ui'

/** 8-stage pipeline; `current` comes from SSE events. The active stage pulses; an unknown stage leaves all pending. */
export default function PipelineStepper({ current, failed = false }: { current?: string; failed?: boolean }) {
  const states = stepStates(STAGES, current, failed)
  return (
    <ol className="flex items-center gap-2" aria-label="Scan pipeline">
      {STAGES.map((s, i) => {
        const st = states[i]
        const color =
          st === 'done' ? 'border-success bg-success/20 text-success'
          : st === 'active' ? 'border-accent bg-accent/20 text-accent'
          : st === 'failed' ? 'border-danger bg-danger/20 text-danger'
          : 'border-border bg-white/5 text-muted'
        return (
          <li key={s} className="flex flex-1 items-center gap-2" aria-current={st === 'active' ? 'step' : undefined}>
            <div className="flex flex-col items-center gap-1.5">
              <motion.div
                className={`flex h-8 w-8 items-center justify-center rounded-full border font-mono text-xs ${color}`}
                animate={
                  st === 'active'
                    ? { boxShadow: ['0 0 0 0 rgba(45,212,191,0.5)', '0 0 0 10px rgba(45,212,191,0)'] }
                    : { boxShadow: '0 0 0 0 rgba(0,0,0,0)' }
                }
                transition={st === 'active' ? { duration: 1.4, repeat: Infinity } : { duration: 0.2 }}
              >
                {st === 'done' ? <Check size={14} /> : st === 'failed' ? <X size={14} /> : i + 1}
              </motion.div>
              <span className={`text-xs ${st === 'pending' ? 'text-muted' : 'text-fg'}`}>{humanize(s)}</span>
              <span className="sr-only">{st}</span>
            </div>
            {i < STAGES.length - 1 && <div className={`mb-5 h-px flex-1 ${st === 'done' ? 'bg-success/60' : 'bg-border'}`} aria-hidden />}
          </li>
        )
      })}
    </ol>
  )
}
