import { describe, expect, it } from 'vitest'
import { initialLoad, loadReducer } from './loadState'
import { mockCompliance, mockIntegrationEvents } from './mock'
import { complianceCsv, csvCell, freshEventIds, PROCESSES, processHealth } from './integrations'
import type { IntegrationEvent } from './types'

const ev = (id: number, process: IntegrationEvent['process'], ok: boolean): IntegrationEvent => ({
  id,
  process,
  endpoint: `/x/${id}`,
  ok,
  summary: '',
  created_at: '2026-10-28T05:00:00Z',
})

describe('integration health dots', () => {
  it('lists the four Boomi processes', () => {
    expect(PROCESSES.map((p) => p.id)).toEqual(['B1', 'B2', 'B3', 'B4'])
  })

  it('uses the latest call per process by id', () => {
    const events = [ev(1, 'B2', true), ev(3, 'B2', false), ev(2, 'B3', true), ev(4, 'B3', true)]
    expect(processHealth(events, 'B2')).toBe('failed')
    expect(processHealth(events, 'B3')).toBe('ok')
  })

  it('is unknown when a process has never been called', () => {
    expect(processHealth([ev(1, 'B2', true)], 'B4')).toBe('unknown')
    expect(processHealth([], 'B1')).toBe('unknown')
  })

  it('mock feed: B2 ok, others unknown', () => {
    expect(processHealth(mockIntegrationEvents, 'B2')).toBe('ok')
    expect(processHealth(mockIntegrationEvents, 'B4')).toBe('unknown')
  })
})

describe('activity poll diff', () => {
  it('animates nothing on the first load', () => {
    expect(freshEventIds(null, [ev(1, 'B2', true)]).size).toBe(0)
  })

  it('returns only ids not seen in the previous poll', () => {
    const prev = [ev(1, 'B2', true), ev(2, 'B3', true)]
    const next = [ev(3, 'B4', false), ev(2, 'B3', true), ev(1, 'B2', true)]
    expect([...freshEventIds(prev, next)]).toEqual([3])
  })
})

describe('compliance CSV (E14 + export safety)', () => {
  it('writes header and one row per item', () => {
    const lines = complianceCsv(mockCompliance).trimEnd().split('\r\n')
    expect(lines[0]).toBe(
      'compliance_log_id,cve_id,package,priority,detected_at,fixed_at,time_to_fix_minutes,jira_key,pr_url,status',
    )
    expect(lines).toHaveLength(2)
    expect(lines[1]).toContain('log_fnd_07,CVE-2020-14343,pyyaml,P1,')
    expect(lines[1]).toContain(',SEC-101,')
  })

  it('quotes commas, quotes and newlines (RFC 4180)', () => {
    expect(csvCell('a,b')).toBe('"a,b"')
    expect(csvCell('say "hi"')).toBe('"say ""hi"""')
    expect(csvCell('line1\nline2')).toBe('"line1\nline2"')
  })

  it('neutralises spreadsheet formulas', () => {
    expect(csvCell('=HYPERLINK("x")')).toBe('"\'=HYPERLINK(""x"")"')
    expect(csvCell('+1')).toBe("'+1")
    expect(csvCell('@sum')).toBe("'@sum")
  })

  it('empty values become empty cells', () => {
    expect(csvCell(null)).toBe('')
    expect(csvCell(undefined)).toBe('')
    expect(csvCell(0)).toBe('0')
  })
})

describe('keep last good data on failed refresh (E14)', () => {
  it('a failed poll keeps the previous rows on screen', () => {
    const ok = loadReducer(initialLoad<IntegrationEvent[]>(), { type: 'ok', data: mockIntegrationEvents })
    const failed = loadReducer(ok, { type: 'fail', message: 'Cannot reach the PatchPilot backend.' })
    expect(failed.data).toBe(mockIntegrationEvents)
    expect(failed.error).toBe('Cannot reach the PatchPilot backend.')
    expect(failed.loading).toBe(false)
  })
})
