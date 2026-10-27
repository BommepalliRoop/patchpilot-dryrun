import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { analysisLabel, fixState, formatAttempts, ringModel, safeUrl, threatChips } from './findingView'
import { initialLoad, loadReducer } from './loadState'
import { mockFindingDetail, mockFindingDetails } from './mock'
import { parseDiff } from './ui'

describe('threat chips', () => {
  it('contract example: no KEV chip, EPSS 6% · top 7%', () => {
    expect(threatChips(mockFindingDetail)).toEqual([{ key: 'epss', label: 'EPSS 6% · top 7%', tone: 'neutral' }])
  })
  it('KEV adds the red chip', () => {
    const chips = threatChips(mockFindingDetails.fnd_20)
    expect(chips[0]).toEqual({ key: 'kev', label: 'Actively exploited (CISA KEV)', tone: 'danger' })
    expect(chips[1].label).toBe('EPSS 41% · top 3%')
  })
  it('hides everything when there is no data', () => {
    expect(threatChips({ kev: false, epss: null, epss_percentile: null })).toEqual([])
    expect(threatChips({ kev: false })).toEqual([])
  })
})

describe('analysis chip', () => {
  it('labels deep and generic, nothing for unknown', () => {
    expect(analysisLabel('deep')).toBe('Deep analysis (code parser)')
    expect(analysisLabel('generic')).toBe('Text + AI analysis')
    expect(analysisLabel('mystery')).toBeNull()
    expect(analysisLabel(undefined)).toBeNull()
  })
})

describe('fix card state', () => {
  it('maps contract example and the other mock states', () => {
    expect(fixState(mockFindingDetail)).toBe('fixed')
    expect(fixState(mockFindingDetails.fnd_21)).toBe('untested') // fixed_untested: amber
    expect(fixState(mockFindingDetails.fnd_20)).toBe('needs_human')
    expect(fixState(mockFindingDetails.fnd_08)).toBe('none') // not_reachable, no fix
    expect(fixState({ status: 'fixing', fix: null })).toBe('fixing')
    expect(fixState({ status: 'open', fix: { ...mockFindingDetail.fix!, status: 'weird', tests_passed: false } })).toBe('failed')
  })
  it('handles missing fix and attempts', () => {
    expect(fixState({ status: 'open', fix: undefined })).toBe('none')
    expect(formatAttempts(1)).toBe('1 attempt')
    expect(formatAttempts(2)).toBe('2 attempts')
    expect(formatAttempts(undefined)).toBe('—')
  })
})

describe('mock states render data (acceptance)', () => {
  it('not_reachable has no evidence or fix; needs_human keeps its evidence', () => {
    expect(mockFindingDetails.fnd_08.reachability).toBe('not_reachable')
    expect(mockFindingDetails.fnd_08.evidence).toEqual([])
    expect(mockFindingDetails.fnd_20.status).toBe('needs_human')
    expect(mockFindingDetails.fnd_20.evidence.length).toBe(1)
  })
})

describe('score ring', () => {
  it('clamps and handles bad input', () => {
    expect(ringModel(10).offset).toBeCloseTo(0)
    expect(ringModel(0).offset).toBeCloseTo(ringModel(0).circumference)
    expect(ringModel(99).value).toBe(10)
    expect(ringModel(-3).value).toBe(0)
    expect(ringModel('x').value).toBe(0)
    expect(ringModel(NaN).value).toBe(0)
  })
})

describe('S11: no HTML from data', () => {
  it('only http(s) links are followed', () => {
    expect(safeUrl('https://github.com/a/b/pull/3')).toBe('https://github.com/a/b/pull/3')
    expect(safeUrl('javascript:alert(1)')).toBeNull()
    expect(safeUrl('data:text/html,<script>1</script>')).toBeNull()
    expect(safeUrl('not a url')).toBeNull()
    expect(safeUrl(null)).toBeNull()
  })
  it('diff lines stay raw text', () => {
    const lines = parseDiff('+<img src=x onerror=alert(1)>')
    expect(lines[0]).toEqual({ kind: 'add', text: '+<img src=x onerror=alert(1)>' })
  })
  it('dangerouslySetInnerHTML only appears in the Shiki CodeViewer', () => {
    const root = join(__dirname, '..')
    const hits: string[] = []
    const walk = (dir: string) => {
      for (const name of readdirSync(dir)) {
        const p = join(dir, name)
        if (statSync(p).isDirectory()) walk(p)
        else if (/\.tsx?$/.test(name) && !name.includes('.test.') && readFileSync(p, 'utf8').includes('dangerouslySetInnerHTML')) hits.push(name)
      }
    }
    walk(root)
    expect(hits).toEqual(['CodeViewer.tsx'])
  })
})

describe('E14: keeps last good data on error', () => {
  it('a failed reload leaves the finding on screen with the error', () => {
    const ok = loadReducer(initialLoad<typeof mockFindingDetail>(), { type: 'ok', data: mockFindingDetail })
    const failed = loadReducer(loadReducer(ok, { type: 'start' }), { type: 'fail', message: 'Cannot reach the PatchPilot backend.' })
    expect(failed.data).toBe(mockFindingDetail)
    expect(failed.error).toMatch(/Cannot reach/)
    expect(failed.loading).toBe(false)
  })
})
