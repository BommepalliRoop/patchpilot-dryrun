import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, sep } from 'node:path'
import { describe, expect, it } from 'vitest'
import { STAGES } from './types'
import { langFor, parseDiff, priorityTone, reachabilityTone, statusTone, stepStates } from './ui'

describe('E15 unknown enums are neutral, never throw', () => {
  it('maps unknown and missing values', () => {
    for (const fn of [priorityTone, reachabilityTone, statusTone]) {
      expect(fn('brand_new').cls).toContain('text-muted')
      expect(fn('brand_new').label).toBe('Brand new')
      expect(fn(undefined).label).toBe('Unknown')
      expect(fn(null).label).toBe('Unknown')
      expect(fn('toString').label).toBe('ToString') // prototype keys are not enum values
    }
  })
  it('maps known values', () => {
    expect(priorityTone('P1').cls).toContain('danger')
    expect(statusTone('fixed').cls).toContain('success')
  })
  it('stepper tolerates unknown stage', () => {
    expect(stepStates(STAGES, 'martian').every((s) => s === 'pending')).toBe(true)
    expect(stepStates(STAGES, undefined).every((s) => s === 'pending')).toBe(true)
    expect(stepStates(STAGES, 'fix')[5]).toBe('active')
    expect(stepStates(STAGES, 'fix', true)[5]).toBe('failed')
    expect(stepStates(STAGES, 'done').every((s) => s === 'done')).toBe(true)
  })
  it('diff and language helpers tolerate missing input', () => {
    expect(parseDiff(undefined)).toEqual([])
    expect(parseDiff('-a\n+b').map((l) => l.kind)).toEqual(['del', 'add'])
    expect(langFor(undefined)).toBe('text')
    expect(langFor('app.py')).toBe('python')
  })
})

describe('S11 no raw HTML rendering', () => {
  const walk = (d: string): string[] =>
    readdirSync(d).flatMap((f) => (statSync(join(d, f)).isDirectory() ? walk(join(d, f)) : [join(d, f)]))
  it('dangerouslySetInnerHTML only appears in CodeViewer (Shiki output)', () => {
    const hits = walk('src')
      .filter((f) => /\.tsx?$/.test(f) && !f.endsWith('.test.ts'))
      .filter((f) => readFileSync(f, 'utf8').includes('dangerouslySetInnerHTML'))
      .map((f) => f.split(sep).join('/'))
    expect(hits).toEqual(['src/components/ui/CodeViewer.tsx'])
  })
})
