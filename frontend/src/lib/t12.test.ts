import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { isResetShortcut } from '../components/DemoReset'
import { validateScanForm } from '../components/RunScanModal'
import { initialLoad, loadReducer } from './loadState'
import { mockFindings, mockScans, MOCK_RUN_MS, mockScanScript } from './mock'
import {
  aggregate, appendLog, epssLabel, filterFindings, funnelModel, languageLabel, MAX_LOG_LINES, NO_FILTERS, realIndices,
} from './scanView'
import type { ScanEvent } from './types'

const ev = (stage: ScanEvent['stage'], message: string, progress = 0.5): ScanEvent => ({
  scan_id: 's', stage, status: 'running', message, progress, data: {},
})

describe('overview aggregation and funnel', () => {
  it('sums stats and averages time to fix', () => {
    const t = aggregate(mockScans)
    expect(t).toMatchObject({ alerts: 12, realRisks: 2, fixed: 2 })
    expect(t.meanTimeToFixMin).toBeCloseTo(1.7, 1)
    expect(aggregate([]).meanTimeToFixMin).toBeNull()
  })
  it('caps dots at 40 and keeps real >= fixed', () => {
    expect(funnelModel({ alerts: 12, realRisks: 2, fixed: 1 })).toEqual({ dots: 12, real: 2, fixed: 1 })
    const big = funnelModel({ alerts: 400, realRisks: 20, fixed: 10 })
    expect(big.dots).toBe(40)
    expect(big.real).toBe(2)
    expect(big.fixed).toBe(1)
    expect(funnelModel({ alerts: 0, realRisks: 3, fixed: 3 })).toEqual({ dots: 0, real: 0, fixed: 0 })
    expect(funnelModel({ alerts: 5, realRisks: 9, fixed: 9 })).toEqual({ dots: 5, real: 5, fixed: 5 })
  })
  it('spreads real dots across the grid', () => {
    expect(realIndices(30, 2)).toEqual([7, 22])
    expect(realIndices(0, 2)).toEqual([])
    expect(new Set(realIndices(12, 12)).size).toBe(12)
  })
})

describe('languages, findings table and filters', () => {
  it('labels languages per task spec', () => {
    expect(languageLabel({ ecosystem: 'PyPI', analysis: 'deep' })).toBe('Python · deep')
    expect(languageLabel({ ecosystem: 'npm', analysis: 'generic' })).toBe('JavaScript · scan + AI')
    expect(languageLabel({ ecosystem: 'Hex', analysis: 'weird' as never })).toBe('Hex · scan + AI')
  })
  it('filters by priority, reachability and ecosystem', () => {
    expect(filterFindings(mockFindings, NO_FILTERS)).toHaveLength(mockFindings.length)
    expect(filterFindings(mockFindings, { ...NO_FILTERS, priority: 'P1' }).map((f) => f.cve_id)).toEqual(['CVE-2020-14343'])
    expect(filterFindings(mockFindings, { ...NO_FILTERS, ecosystem: 'npm' }).every((f) => f.ecosystem === 'npm')).toBe(true)
    expect(filterFindings(mockFindings, { ...NO_FILTERS, reachability: 'unsure' })).toHaveLength(1)
  })
  it('EPSS hover text', () => {
    expect(epssLabel(0.9326, 0.0598)).toBe('EPSS top 7% · 6.0% exploitation probability')
    expect(epssLabel(null, null)).toBe('EPSS unavailable')
    expect(epssLabel(undefined)).toBe('EPSS unavailable')
    expect(mockFindings.some((f) => f.kev)).toBe(true) // the flame has a fixture to render
  })
})

describe('N8 log replay after reconnect', () => {
  it('ignores replayed duplicates and caps size', () => {
    let log = appendLog([], ev('clone', 'a', 0.1), 1)
    log = appendLog(log, ev('scan', 'b', 0.2), 2)
    const replay = appendLog(appendLog(log, ev('clone', 'a', 0.1), 3), ev('scan', 'b', 0.2), 4)
    expect(replay.map((l) => l.message)).toEqual(['a', 'b'])
    let big = log
    for (let i = 0; i < MAX_LOG_LINES + 20; i++) big = appendLog(big, ev('scan', `m${i}`, 0.3), i)
    expect(big).toHaveLength(MAX_LOG_LINES)
    expect(big[big.length - 1].message).toBe(`m${MAX_LOG_LINES + 19}`)
  })
})

describe('mock replays the scripted scan in about 25 s', () => {
  it('covers every stage and ends with done', () => {
    const script = mockScanScript('scn_01')
    expect(MOCK_RUN_MS).toBeGreaterThanOrEqual(24000)
    expect(MOCK_RUN_MS).toBeLessThanOrEqual(26000)
    expect(script[script.length - 1].event.stage).toBe('done')
    expect(new Set(script.map((s) => s.event.stage))).toEqual(
      new Set(['clone', 'scan', 'symbols', 'reachability', 'risk', 'fix', 'pr', 'notify', 'done']),
    )
    const times = script.map((s) => s.at)
    expect(times).toEqual([...times].sort((a, b) => a - b))
  })
})

describe('E14 errors keep the last good data', () => {
  it('keeps data on a failed refresh and clears the error on success', () => {
    let s = loadReducer(initialLoad<string[]>(), { type: 'ok', data: ['a'] })
    s = loadReducer(s, { type: 'start' })
    s = loadReducer(s, { type: 'fail', message: 'Cannot reach the backend' })
    expect(s).toEqual({ data: ['a'], error: 'Cannot reach the backend', loading: false })
    s = loadReducer(s, { type: 'ok', data: ['b'] })
    expect(s).toEqual({ data: ['b'], error: null, loading: false })
  })
  it('validates the Run scan form before calling the API', () => {
    const ok = { client_name: 'Acme', repo_url: 'https://github.com/o/r', branch: 'main', owner_email: '' }
    expect(validateScanForm(ok)).toBeNull()
    expect(validateScanForm({ ...ok, repo_url: 'http://github.com/o/r' })).toMatch(/https/)
    expect(validateScanForm({ ...ok, client_name: ' ' })).toMatch(/client/i)
    expect(validateScanForm({ ...ok, branch: 'a b;rm' })).toMatch(/Branch/)
    expect(validateScanForm({ ...ok, owner_email: 'nope' })).toMatch(/email/i)
  })
})

describe('S8 demo reset asks for the key', () => {
  const key = (o: Partial<Parameters<typeof isResetShortcut>[0]> = {}) =>
    isResetShortcut({ key: 'R', shiftKey: true, ctrlKey: false, metaKey: false, altKey: false, target: null, ...o })
  it('Shift+R triggers, typing in a field or other modifiers do not', () => {
    expect(key()).toBe(true)
    expect(key({ shiftKey: false, key: 'r' })).toBe(false)
    expect(key({ ctrlKey: true })).toBe(false)
    expect(key({ target: { tagName: 'INPUT', isContentEditable: false } as unknown as EventTarget })).toBe(false)
  })
  it('no key in env files or bundle sources, nothing persisted by the reset flow', () => {
    const env = ['.env.example', '.env'].map((f) => { try { return readFileSync(f, 'utf8') } catch { return '' } }).join('\n')
    expect(env).not.toMatch(/VITE_[A-Z_]*(KEY|TOKEN|SECRET)\s*=\s*\S/)
    const src = readFileSync('src/components/DemoReset.tsx', 'utf8')
    expect(src).not.toMatch(/localStorage|sessionStorage|import\.meta\.env/)
    const walk = (d: string): string[] => readdirSync(d).flatMap((f) => (statSync(join(d, f)).isDirectory() ? walk(join(d, f)) : [join(d, f)]))
    for (const f of walk('src').filter((x) => /\.tsx?$/.test(x) && !x.endsWith('.test.ts'))) {
      expect(readFileSync(f, 'utf8'), f).not.toMatch(/VITE_[A-Z_]*(API_KEY|ADMIN)/)
    }
  })
})

describe('api: S8 header and N7 direct SSE URL', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
    vi.resetModules()
  })
  async function liveApi() {
    vi.stubEnv('VITE_USE_MOCK', 'false')
    vi.stubEnv('VITE_API_BASE_URL', 'https://api.example.test')
    vi.resetModules()
    return import('./api')
  }
  it('resetDemo sends the key typed by the user as X-API-Key', async () => {
    const api = await liveApi()
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await api.resetDemo('typed-key')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('https://api.example.test/api/demo/reset')
    expect(init.method).toBe('POST')
    expect(init.headers['X-API-Key']).toBe('typed-key')
  })
  it('SSE connects straight to the backend URL, not a relative proxy path', async () => {
    const api = await liveApi()
    const urls: string[] = []
    class FakeSource {
      onmessage: unknown; onerror: unknown; onopen: unknown
      constructor(u: string) { urls.push(u) }
      close() {}
    }
    vi.stubGlobal('EventSource', FakeSource)
    const off = api.subscribeScanEvents('scn_1', () => {})
    expect(urls).toEqual(['https://api.example.test/api/scans/scn_1/events'])
    off()
  })
  it('a network failure becomes a human ApiError', async () => {
    const api = await liveApi()
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('boom')))
    await expect(api.listScans()).rejects.toMatchObject({ code: 'network_error' })
  })
})
