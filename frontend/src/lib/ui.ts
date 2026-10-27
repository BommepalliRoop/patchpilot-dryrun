// Display lookups for enums. RISKS E15: an unknown or missing value always maps to a neutral entry, never throws.
import type { Priority, Reachability, FindingStatus, Stage } from './types'

export interface Tone {
  label: string
  cls: string
}

const NEUTRAL = 'border-border bg-white/5 text-muted'

const PRIORITY: Record<Priority, Tone> = {
  P1: { label: 'P1', cls: 'border-danger/50 bg-danger/15 text-danger' },
  P2: { label: 'P2', cls: 'border-warning/50 bg-warning/15 text-warning' },
  P3: { label: 'P3', cls: 'border-accent/40 bg-accent/10 text-accent' },
  P4: { label: 'P4', cls: NEUTRAL },
}

const REACHABILITY: Record<Reachability, Tone> = {
  reachable: { label: 'Reachable', cls: 'border-danger/50 bg-danger/15 text-danger' },
  unsure: { label: 'Unsure', cls: 'border-warning/50 bg-warning/15 text-warning' },
  not_reachable: { label: 'Not reachable', cls: 'border-success/40 bg-success/10 text-success' },
}

const STATUS: Record<FindingStatus, Tone> = {
  open: { label: 'Open', cls: 'border-warning/50 bg-warning/15 text-warning' },
  fixing: { label: 'Fixing', cls: 'border-accent/40 bg-accent/10 text-accent' },
  fixed: { label: 'Fixed', cls: 'border-success/40 bg-success/10 text-success' },
  needs_human: { label: 'Needs human', cls: 'border-danger/50 bg-danger/15 text-danger' },
  ignored: { label: 'Ignored', cls: NEUTRAL },
}

export function humanize(v: string): string {
  const s = v.replace(/_/g, ' ')
  return s.charAt(0).toUpperCase() + s.slice(1)
}

function pick<T extends string>(table: Record<T, Tone>, value: string | null | undefined): Tone {
  if (value && Object.prototype.hasOwnProperty.call(table, value)) return table[value as T]
  return { label: value ? humanize(value) : 'Unknown', cls: NEUTRAL }
}

export const priorityTone = (v?: string | null) => pick(PRIORITY, v)
export const reachabilityTone = (v?: string | null) => pick(REACHABILITY, v)
export const statusTone = (v?: string | null) => pick(STATUS, v)

export type StepState = 'done' | 'active' | 'pending' | 'failed'

/** State of each stage given the scan's current stage; an unknown stage leaves everything pending. */
export function stepStates(stages: readonly Stage[], current: string | undefined, failed = false): StepState[] {
  if (current === 'done') return stages.map(() => 'done')
  const idx = current ? stages.indexOf(current as Stage) : -1
  return stages.map((_, i) => {
    if (idx < 0) return 'pending'
    if (i < idx) return 'done'
    if (i === idx) return failed ? 'failed' : 'active'
    return 'pending'
  })
}

export type DiffKind = 'add' | 'del' | 'hunk' | 'meta' | 'ctx'

export function parseDiff(diff: string | null | undefined): { kind: DiffKind; text: string }[] {
  if (!diff) return []
  return diff.split('\n').map((text) => {
    let kind: DiffKind = 'ctx'
    if (text.startsWith('+++') || text.startsWith('---') || text.startsWith('diff ') || text.startsWith('index ')) kind = 'meta'
    else if (text.startsWith('@@')) kind = 'hunk'
    else if (text.startsWith('+')) kind = 'add'
    else if (text.startsWith('-')) kind = 'del'
    return { kind, text }
  })
}

const LANGS: Record<string, string> = {
  py: 'python', js: 'javascript', jsx: 'jsx', ts: 'typescript', tsx: 'tsx', json: 'json', yml: 'yaml', yaml: 'yaml',
  java: 'java', go: 'go', rs: 'rust', php: 'php', rb: 'ruby', cs: 'csharp', txt: 'text', md: 'markdown', toml: 'toml',
}

export function langFor(file: string | undefined): string {
  const ext = (file ?? '').split('.').pop()?.toLowerCase() ?? ''
  return LANGS[ext] ?? 'text'
}
