// Pure view helpers for the finding detail page. RISKS E15: missing or unknown values never throw.
import type { Analysis, FindingDetail, FindingSummary } from './types'

/** Links from the API are only followed when they are http(s) (S11: no `javascript:` URLs from data). */
export function safeUrl(url?: string | null): string | null {
  if (!url) return null
  try {
    const u = new URL(url)
    return u.protocol === 'https:' || u.protocol === 'http:' ? u.toString() : null
  } catch {
    return null
  }
}

export interface ThreatChip {
  key: 'kev' | 'epss'
  label: string
  tone: 'danger' | 'neutral'
}

/** Red KEV chip when `kev`; "EPSS 6% · top 7%" when EPSS data exists. Both hidden when there is no data. */
export function threatChips(f: Pick<FindingSummary, 'kev' | 'epss' | 'epss_percentile'>): ThreatChip[] {
  const chips: ThreatChip[] = []
  if (f.kev === true) chips.push({ key: 'kev', label: 'Actively exploited (CISA KEV)', tone: 'danger' })
  const hasEpss = typeof f.epss === 'number' && Number.isFinite(f.epss)
  const hasPct = typeof f.epss_percentile === 'number' && Number.isFinite(f.epss_percentile)
  if (hasEpss || hasPct) {
    const top = hasPct ? Math.max(1, Math.round((1 - (f.epss_percentile as number)) * 100)) : null
    const pct = top !== null ? ` · top ${top}%` : ''
    const prob = hasEpss ? `EPSS ${Math.round((f.epss as number) * 100)}%` : 'EPSS'
    chips.push({ key: 'epss', label: `${prob}${pct}`, tone: 'neutral' })
  }
  return chips
}

export function analysisLabel(analysis?: Analysis | string | null): string | null {
  if (analysis === 'deep') return 'Deep analysis (code parser)'
  if (analysis === 'generic') return 'Text + AI analysis'
  return null
}

export type FixState = 'none' | 'fixing' | 'fixed' | 'untested' | 'needs_human' | 'failed'

/** Which Fix card variant to show. `fixed_untested` is the amber "Upgrade PR ready — tests not run" state. */
export function fixState(d: Pick<FindingDetail, 'status' | 'fix'>): FixState {
  if (d.status === 'fixing') return 'fixing'
  if (d.status === 'needs_human' || d.fix?.status === 'needs_human') return 'needs_human'
  if (!d.fix) return 'none'
  if (d.fix.status === 'fixed_untested') return 'untested'
  if (d.fix.status === 'fixed') return d.fix.tests_passed ? 'fixed' : 'untested'
  return 'failed'
}

/** Ring geometry for a 0–10 score. Out-of-range or non-numeric scores clamp. */
export function ringModel(score: unknown, radius = 34): { value: number; circumference: number; offset: number } {
  const n = typeof score === 'number' && Number.isFinite(score) ? Math.min(10, Math.max(0, score)) : 0
  const circumference = 2 * Math.PI * radius
  return { value: n, circumference, offset: circumference * (1 - n / 10) }
}

export function formatAttempts(n?: number | null): string {
  if (typeof n !== 'number' || !Number.isFinite(n) || n < 0) return '—'
  return n === 1 ? '1 attempt' : `${n} attempts`
}
