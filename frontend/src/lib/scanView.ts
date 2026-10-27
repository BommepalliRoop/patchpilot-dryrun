// Pure view logic for the Overview and live scan pages (kept out of components so it is unit-testable).
import type { Analysis, FindingSummary, LanguageInfo, Priority, Reachability, Scan, ScanEvent, ScanStats } from './types'

export const MAX_FUNNEL_DOTS = 40
export const MAX_LOG_LINES = 500

// ---- Overview ----------------------------------------------------------------------------------

export interface Totals {
  alerts: number
  realRisks: number
  fixed: number
  /** Mean minutes from scan start to finish over completed scans that fixed something; null when unknown. */
  meanTimeToFixMin: number | null
}

export function aggregate(scans: readonly Scan[]): Totals {
  const num = (n: unknown) => (typeof n === 'number' && Number.isFinite(n) ? n : 0)
  let alerts = 0
  let realRisks = 0
  let fixed = 0
  const durations: number[] = []
  for (const s of scans) {
    alerts += num(s.stats?.total_alerts)
    realRisks += num(s.stats?.reachable)
    fixed += num(s.stats?.fixed)
    if (s.status === 'completed' && num(s.stats?.fixed) > 0 && s.started_at && s.finished_at) {
      const ms = Date.parse(s.finished_at) - Date.parse(s.started_at)
      if (Number.isFinite(ms) && ms >= 0) durations.push(ms / 60000)
    }
  }
  const mean = durations.length ? durations.reduce((a, b) => a + b, 0) / durations.length : null
  return { alerts, realRisks, fixed, meanTimeToFixMin: mean }
}

export interface FunnelModel {
  dots: number
  real: number
  fixed: number
}

/** Dots fall into the funnel; `real` come out glowing red, `fixed` of those turn into a green check. Capped at 40 dots. */
export function funnelModel(totals: Pick<Totals, 'alerts' | 'realRisks' | 'fixed'>): FunnelModel {
  const alerts = Math.max(0, Math.floor(totals.alerts))
  const dots = Math.min(alerts, MAX_FUNNEL_DOTS)
  const scale = alerts > dots && alerts > 0 ? dots / alerts : 1
  const scaled = (n: number) => (n > 0 && dots > 0 ? Math.max(1, Math.round(n * scale)) : 0)
  const real = Math.min(dots, scaled(totals.realRisks))
  const fixed = Math.min(real, scaled(totals.fixed))
  return { dots, real, fixed }
}

/** Evenly spread indices (0..dots-1) of the dots that survive the funnel. */
export function realIndices(dots: number, real: number): number[] {
  const n = Math.min(real, dots)
  if (n <= 0) return []
  return Array.from({ length: n }, (_, k) => Math.floor(((k + 0.5) * dots) / n))
}

export function formatMinutes(min: number | null): string {
  if (min === null) return '—'
  return min < 1 ? `${Math.round(min * 60)} s` : `${min.toFixed(1)} min`
}

// ---- Languages ---------------------------------------------------------------------------------

const LANGUAGE_NAMES: Record<string, string> = {
  PyPI: 'Python', npm: 'JavaScript', Maven: 'Java', Go: 'Go', 'crates.io': 'Rust', Packagist: 'PHP', NuGet: '.NET',
  RubyGems: 'Ruby',
}

export function languageName(ecosystem: string): string {
  return Object.prototype.hasOwnProperty.call(LANGUAGE_NAMES, ecosystem) ? LANGUAGE_NAMES[ecosystem] : ecosystem || 'Unknown'
}

/** "Python · deep" / "JavaScript · scan + AI". Unknown analysis values fall back to the generic wording. */
export function languageLabel(lang: Pick<LanguageInfo, 'ecosystem' | 'analysis'>): string {
  const depth = lang.analysis === 'deep' ? 'deep' : 'scan + AI'
  return `${languageName(lang.ecosystem)} · ${depth}`
}

export function analysisLabel(a?: Analysis | string | null): string {
  return a === 'deep' ? 'AST + AI' : 'text + AI'
}

// ---- Findings table ----------------------------------------------------------------------------

export interface FindingFiltersState {
  priority: Priority | ''
  reachability: Reachability | ''
  ecosystem: string
}
export const NO_FILTERS: FindingFiltersState = { priority: '', reachability: '', ecosystem: '' }

export function filterFindings(list: readonly FindingSummary[], f: FindingFiltersState): FindingSummary[] {
  return list.filter(
    (x) =>
      (!f.priority || x.priority === f.priority) &&
      (!f.reachability || x.reachability === f.reachability) &&
      (!f.ecosystem || x.ecosystem === f.ecosystem),
  )
}

export function ecosystemsOf(list: readonly FindingSummary[]): string[] {
  return [...new Set(list.map((x) => x.ecosystem).filter(Boolean))].sort()
}

/** Tooltip text for the threat cell, e.g. "EPSS top 7% · 6.0% exploitation probability". Missing data is stated. */
export function epssLabel(percentile?: number | null, epss?: number | null): string {
  if (typeof percentile !== 'number' || !Number.isFinite(percentile)) return 'EPSS unavailable'
  const top = Math.max(1, Math.round((1 - percentile) * 100))
  const prob = typeof epss === 'number' && Number.isFinite(epss) ? ` · ${(epss * 100).toFixed(1)}% exploitation probability` : ''
  return `EPSS top ${top}%${prob}`
}

// ---- Live log ----------------------------------------------------------------------------------

export interface LogLine {
  key: string
  stage: string
  status: string
  message: string
  at: number
}

const eventKey = (e: ScanEvent) => `${e.stage}|${e.status}|${e.progress}|${e.message}`

/** Appends an SSE event; a replayed duplicate (reconnect, RISKS N8) is ignored. Capped so a long scan cannot grow unbounded. */
export function appendLog(log: readonly LogLine[], e: ScanEvent, now = Date.now()): LogLine[] {
  const key = eventKey(e)
  if (log.some((l) => l.key === key)) return log as LogLine[]
  const next = [...log, { key, stage: e.stage, status: e.status, message: e.message, at: now }]
  return next.length > MAX_LOG_LINES ? next.slice(next.length - MAX_LOG_LINES) : next
}

export const isActiveScan = (status?: string | null) => status === 'queued' || status === 'running'

export const progressPct = (p?: number | null) =>
  typeof p === 'number' && Number.isFinite(p) ? Math.round(Math.min(1, Math.max(0, p)) * 100) : 0

export const STAT_FIELDS: { key: keyof ScanStats; label: string }[] = [
  { key: 'total_alerts', label: 'Alerts' },
  { key: 'reachable', label: 'Reachable' },
  { key: 'p1', label: 'P1' },
  { key: 'fixed', label: 'Fixed' },
  { key: 'prs_opened', label: 'PRs' },
]
