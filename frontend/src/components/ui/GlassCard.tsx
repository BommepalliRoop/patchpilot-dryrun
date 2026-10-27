import type { HTMLAttributes } from 'react'

/** Glass surface: blur, 1px border, 16px radius, subtle inner highlight. `glow` is for P1 findings. */
export default function GlassCard({ glow, className = '', ...rest }: HTMLAttributes<HTMLDivElement> & { glow?: boolean }) {
  return (
    <div
      {...rest}
      className={`rounded-[16px] border bg-surface/70 p-5 backdrop-blur-md shadow-[inset_0_1px_0_rgb(255_255_255/0.06)] ${
        glow ? 'border-danger/50 shadow-[0_0_24px_-6px_rgb(244_63_94/0.45),inset_0_1px_0_rgb(255_255_255/0.06)]' : 'border-border'
      } ${className}`}
    />
  )
}
