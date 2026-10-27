// The ONLY place the frontend talks to the backend (CLAUDE.md rule 7).
// VITE_USE_MOCK=true serves src/lib/mock fixtures so UI work never blocks on the backend.
import {
  MOCK_SCAN_ID,
  mockCompliance,
  mockFindingDetails,
  mockElapsed,
  mockFindings,
  mockHealth,
  mockIntegrationEvents,
  mockRunStage,
  mockScanScript,
  mockScans,
  startMockRun,
} from './mock'
import { STAGES } from './types'
import type {
  ApiErrorBody,
  ComplianceReport,
  FindingDetail,
  FindingFilters,
  FindingSummary,
  FixStarted,
  Health,
  IntegrationEvent,
  Scan,
  ScanCreated,
  ScanCreateRequest,
  ScanEvent,
} from './types'

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '')
export const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

/** Error envelope from the backend: { error: { code, message } } (docs/API_CONTRACTS.md). */
export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

const delay = (ms = 150) => new Promise<void>((resolve) => setTimeout(resolve, ms))

async function request<T>(path: string, init?: RequestInit & { apiKey?: string }): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (init?.body) headers['Content-Type'] = 'application/json'
  if (init?.apiKey) headers['X-API-Key'] = init.apiKey // supplied per call by the user, never stored or bundled

  let res: Response
  try {
    res = await fetch(`${API_BASE_URL}${path}`, { ...init, headers: { ...headers, ...init?.headers } })
  } catch {
    throw new ApiError(0, 'network_error', 'Cannot reach the PatchPilot backend. Check your connection and retry.')
  }
  if (!res.ok) {
    let code = 'internal_error'
    let message = `Request failed (${res.status})`
    try {
      const body = (await res.json()) as Partial<ApiErrorBody>
      if (body.error) ({ code, message } = body.error)
    } catch {
      /* non-JSON error body: keep the generic message */
    }
    throw new ApiError(res.status, code, message)
  }
  return (await res.json()) as T
}

function query(params: Record<string, string | number | undefined>): string {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== '') q.set(k, String(v))
  const s = q.toString()
  return s ? `?${s}` : ''
}

// ---- Scans ---------------------------------------------------------------------------------

/** POST /api/scans */
export async function createScan(body: ScanCreateRequest): Promise<ScanCreated> {
  if (USE_MOCK) {
    startMockRun()
    return delay().then(() => ({ scan_id: MOCK_SCAN_ID, status: 'queued' as const }))
  }
  return request('/api/scans', { method: 'POST', body: JSON.stringify(body) })
}

const stageIdx = (stage: string) => STAGES.indexOf(stage as (typeof STAGES)[number])

/** While the scripted mock run is in progress the scan reports its live stage and partial stats. */
function withMockProgress(scan: Scan): Scan {
  const stage = mockRunStage()
  if (!stage) return scan
  const at = stageIdx(stage)
  const s = scan.stats
  return {
    ...scan,
    status: 'running',
    current_stage: stage,
    finished_at: null,
    stats: {
      total_alerts: at >= 1 ? s.total_alerts : 0,
      reachable: at >= 4 ? s.reachable : 0,
      unsure: at >= 4 ? s.unsure : 0,
      not_reachable: at >= 4 ? s.not_reachable : 0,
      p1: at >= 4 ? s.p1 : 0,
      p2: at >= 4 ? s.p2 : 0,
      fixed: at >= 6 ? s.fixed : 0,
      prs_opened: at >= 6 ? s.prs_opened : 0,
    },
  }
}

/** Mock only: restarts the scripted 25 s run (the "Replay" button). */
export function replayMockRun(): void {
  startMockRun()
}

/** GET /api/scans (newest first) */
export async function listScans(): Promise<Scan[]> {
  if (USE_MOCK) return delay().then(() => mockScans.map(withMockProgress))
  return request('/api/scans')
}

/** GET /api/scans/{scan_id} */
export async function getScan(scanId: string): Promise<Scan> {
  if (USE_MOCK) {
    await delay()
    const scan = mockScans.find((s) => s.scan_id === scanId)
    if (!scan) throw new ApiError(404, 'not_found', `Scan ${scanId} not found`)
    return withMockProgress(scan)
  }
  return request(`/api/scans/${encodeURIComponent(scanId)}`)
}

/**
 * GET /api/scans/{scan_id}/events (SSE). Talks to the backend URL directly, never through a proxy (RISKS N7).
 * Returns an unsubscribe function. `onError` fires when the stream drops (show "Reconnecting…"; EventSource retries
 * by itself, and the page should also re-fetch `getScan` on reconnect and on `done` — RISKS N8).
 */
export function subscribeScanEvents(
  scanId: string,
  onEvent: (event: ScanEvent) => void,
  onError?: () => void,
  onOpen?: () => void,
): () => void {
  if (USE_MOCK) {
    // Like the backend replay buffer: events already due fire at once, the rest on schedule.
    const elapsed = mockElapsed() ?? 0
    const timers = mockScanScript(scanId).map(({ at, event }) =>
      setTimeout(() => onEvent(event), Math.max(0, at - elapsed)),
    )
    return () => timers.forEach(clearTimeout)
  }
  const source = new EventSource(`${API_BASE_URL}/api/scans/${encodeURIComponent(scanId)}/events`)
  source.onmessage = (msg) => {
    try {
      const event = JSON.parse(msg.data) as ScanEvent
      onEvent(event)
      if (event.stage === 'done') source.close()
    } catch {
      /* ignore malformed frame (heartbeat comments never reach onmessage) */
    }
  }
  source.onopen = () => onOpen?.()
  source.onerror = () => onError?.()
  return () => source.close()
}

// ---- Findings ------------------------------------------------------------------------------

/** GET /api/findings?scan_id=&priority=&reachability= */
export async function listFindings(filters: FindingFilters = {}): Promise<FindingSummary[]> {
  if (USE_MOCK) {
    await delay()
    // During the scripted run findings exist only from the risk stage on; the P1 shows "fixing", then "fixed".
    const stage = mockRunStage()
    if (stage && stageIdx(stage) < 4) return []
    const base =
      stage && stageIdx(stage) < 6
        ? mockFindings.map((f) => ({ ...f, status: f.priority === 'P1' && stage === 'fix' ? ('fixing' as const) : ('open' as const) }))
        : mockFindings
    return base.filter(
      (f) =>
        (!filters.priority || f.priority === filters.priority) &&
        (!filters.reachability || f.reachability === filters.reachability),
    )
  }
  return request(`/api/findings${query({ ...filters })}`)
}

/** GET /api/findings/{finding_id} */
export async function getFinding(findingId: string): Promise<FindingDetail> {
  if (USE_MOCK) {
    await delay()
    const detail = mockFindingDetails[findingId]
    if (!detail) throw new ApiError(404, 'not_found', `Finding ${findingId} not found`)
    return detail
  }
  return request(`/api/findings/${encodeURIComponent(findingId)}`)
}

/** POST /api/findings/{finding_id}/fix — run or re-run the fix manually */
export async function runFix(findingId: string): Promise<FixStarted> {
  if (USE_MOCK) return delay().then(() => ({ finding_id: findingId, status: 'fixing' as const }))
  return request(`/api/findings/${encodeURIComponent(findingId)}/fix`, { method: 'POST' })
}

// ---- Integrations, compliance, health, demo -------------------------------------------------

/** GET /api/integrations/activity?limit= */
export async function listIntegrationActivity(limit = 50): Promise<IntegrationEvent[]> {
  if (USE_MOCK) return delay().then(() => mockIntegrationEvents.slice(0, limit))
  return request(`/api/integrations/activity${query({ limit })}`)
}

/** GET /api/compliance?client_name=&from= (backend proxy of Boomi B4) */
export async function getCompliance(clientName?: string, from?: string): Promise<ComplianceReport> {
  if (USE_MOCK) return delay().then(() => mockCompliance)
  return request(`/api/compliance${query({ client_name: clientName, from })}`)
}

/** GET /api/health */
export async function getHealth(): Promise<Health> {
  if (USE_MOCK) return delay(50).then(() => mockHealth)
  return request('/api/health')
}

/** POST /api/demo/reset — needs the admin key, typed by the user at call time (Shift+R). */
export async function resetDemo(apiKey: string): Promise<{ ok: boolean }> {
  if (USE_MOCK) return delay().then(() => ({ ok: true }))
  return request('/api/demo/reset', { method: 'POST', apiKey })
}
