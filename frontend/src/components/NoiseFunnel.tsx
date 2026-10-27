import { motion } from 'motion/react'
import { Check } from 'lucide-react'
import { funnelModel, realIndices, type Totals } from '../lib/scanView'

const W = 520
const H = 330
const CX = W / 2
const DOT = 14
const FUNNEL_Y = 150 // where dots disappear into the neck
const OUT_Y = 280 // where real risks land
const FALL = 2.2 // seconds for the fall

/**
 * Signature animation (UI_SPEC): N alert dots fall into a funnel, only the real risks come out glowing red and the
 * fixed ones turn into a green check. Driven by the aggregated scan stats; remounts (replays) when they change.
 */
export default function NoiseFunnel({ totals }: { totals: Pick<Totals, 'alerts' | 'realRisks' | 'fixed'> }) {
  const { dots, real, fixed } = funnelModel(totals)
  const survivors = realIndices(dots, real)
  const slot = (k: number) => CX - DOT / 2 + (k - (real - 1) / 2) * 34
  const stagger = 0.05

  return (
    <div className="flex flex-col items-center">
      <div
        key={`${dots}-${real}-${fixed}`}
        className="relative"
        style={{ width: W, height: H }}
        role="img"
        aria-label={`${totals.alerts} alerts, ${totals.realRisks} real risks, ${totals.fixed} fixed`}
      >
        <svg width={W} height={H} className="absolute inset-0" aria-hidden>
          <defs>
            <linearGradient id="funnel" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor="#2DD4BF" stopOpacity="0.16" />
              <stop offset="1" stopColor="#2DD4BF" stopOpacity="0.03" />
            </linearGradient>
          </defs>
          <path
            d={`M20 110 L${W - 20} 110 L${CX + 22} 190 L${CX + 22} 215 L${CX - 22} 215 L${CX - 22} 190 Z`}
            fill="url(#funnel)"
            stroke="rgba(255,255,255,0.14)"
          />
        </svg>

        {Array.from({ length: dots }, (_, i) => {
          const sx = (W - 10 * 44) / 2 + (i % 10) * 44 + 15
          const sy = 6 + Math.floor(i / 10) * 24
          const isReal = survivors.includes(i)
          const delay = i * stagger
          return (
            <motion.span
              key={i}
              className="absolute top-0 left-0 rounded-full bg-muted"
              style={{ width: DOT, height: DOT }}
              initial={{ x: sx, y: sy, opacity: 1, scale: 1 }}
              animate={{
                x: [sx, CX - DOT / 2, CX - DOT / 2],
                y: [sy, 118, FUNNEL_Y + 60],
                opacity: [1, 1, 0],
                scale: [1, 1, isReal ? 1 : 0.3],
              }}
              transition={{ duration: FALL, delay, times: [0, 0.55, 1], ease: 'easeIn' }}
            />
          )
        })}

        {survivors.map((_, k) => {
          const landed = (dots - 1) * stagger + FALL * 0.8 + k * 0.12
          const isFixed = k < fixed
          return (
            <span key={k}>
              <motion.span
                className="absolute top-0 left-0 rounded-full bg-danger"
                style={{ width: DOT + 4, height: DOT + 4 }}
                initial={{ x: slot(k) - 2, y: FUNNEL_Y + 60, opacity: 0 }}
                animate={{
                  y: OUT_Y,
                  opacity: isFixed ? [0, 1, 1, 0] : 1,
                  boxShadow: ['0 0 0 0 rgba(244,63,94,0.6)', '0 0 18px 6px rgba(244,63,94,0.55)', '0 0 10px 2px rgba(244,63,94,0.4)'],
                }}
                transition={{ duration: isFixed ? 3 : 0.9, delay: landed, times: isFixed ? [0, 0.15, 0.7, 1] : undefined }}
              />
              {isFixed && (
                <motion.span
                  className="absolute top-0 left-0 flex items-center justify-center rounded-full bg-success text-bg"
                  style={{ width: DOT + 8, height: DOT + 8 }}
                  initial={{ x: slot(k) - 4, y: OUT_Y - 2, scale: 0, opacity: 0 }}
                  animate={{ scale: [0, 1.25, 1], opacity: 1 }}
                  transition={{ duration: 0.5, delay: landed + 2.2 }}
                >
                  <Check size={12} strokeWidth={3} aria-hidden />
                </motion.span>
              )}
            </span>
          )
        })}
      </div>
      <div className="mt-1 flex items-center gap-3 text-sm text-muted">
        <span><b className="text-fg">{totals.alerts}</b> alerts</span>
        <span aria-hidden>→</span>
        <span><b className="text-danger">{totals.realRisks}</b> real risks</span>
        <span aria-hidden>→</span>
        <span><b className="text-success">{totals.fixed}</b> fixed</span>
      </div>
    </div>
  )
}
