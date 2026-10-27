// Mirrors docs/API_CONTRACTS.md Part A. snake_case on purpose — these are the wire shapes.
// RISKS E15: optional fields are optional; UI code must treat unknown enum values as neutral, never crash.

export type ScanStatus = 'queued' | 'running' | 'completed' | 'failed'
export type Stage = 'clone' | 'scan' | 'symbols' | 'reachability' | 'risk' | 'fix' | 'pr' | 'notify' | 'done'
export type Reachability = 'reachable' | 'not_reachable' | 'unsure'
export type Priority = 'P1' | 'P2' | 'P3' | 'P4'
export type FindingStatus = 'open' | 'fixing' | 'fixed' | 'needs_human' | 'ignored'
export type Analysis = 'deep' | 'generic'
/** OSV names; others are passed through as OSV names them. */
export type Ecosystem = 'PyPI' | 'npm' | 'Maven' | 'Go' | 'crates.io' | 'Packagist' | 'NuGet' | 'RubyGems' | (string & {})
export type IntegrationProcess = 'B1' | 'B2' | 'B3' | 'B4'

export const STAGES: Stage[] = ['clone', 'scan', 'symbols', 'reachability', 'risk', 'fix', 'pr', 'notify']

export interface ScanCreateRequest {
  client_name: string
  repo_url: string
  branch?: string
  auto_fix?: boolean
  owner_email?: string
}

export interface ScanCreated {
  scan_id: string
  status: ScanStatus
}

export interface LanguageInfo {
  ecosystem: Ecosystem
  manifests: string[]
  analysis: Analysis
}

export interface ScanStats {
  total_alerts: number
  reachable: number
  unsure: number
  not_reachable: number
  p1: number
  p2: number
  fixed: number
  prs_opened: number
}

export interface Scan {
  scan_id: string
  client_name: string
  repo_url: string
  branch: string
  status: ScanStatus
  current_stage: Stage | string
  started_at?: string | null
  finished_at?: string | null
  languages: LanguageInfo[]
  stats: ScanStats
}

export interface ScanEvent {
  scan_id: string
  stage: Stage
  status: string
  message: string
  progress: number
  data: Record<string, unknown>
}

export interface FindingSummary {
  finding_id: string
  cve_id: string
  package: string
  installed_version: string
  fixed_version?: string | null
  cvss: number
  reachability: Reachability
  confidence: number
  score: number
  priority: Priority
  status: FindingStatus
  kev: boolean
  epss?: number | null
  epss_percentile?: number | null
  ecosystem: Ecosystem
  analysis: Analysis
}

export interface Evidence {
  file: string
  line: number
  in_route: boolean
  code_snippet: string
  start_line: number
}

export interface FixInfo {
  new_version: string
  attempts: number
  tests_passed: boolean
  patch_diff: string
  pr_url?: string | null
  status: string
}

export interface IntegrationInfo {
  jira_key?: string | null
  jira_url?: string | null
  slack_sent: boolean
  compliance_log_id?: string | null
}

export interface TimelineItem {
  stage: string
  at: string
  message: string
}

export interface FindingDetail extends FindingSummary {
  summary: string
  kev_date_added?: string | null
  vulnerable_symbols: string[]
  evidence: Evidence[]
  ai_explanation: string
  fix?: FixInfo | null
  integration?: IntegrationInfo | null
  timeline: TimelineItem[]
}

export interface FixStarted {
  finding_id: string
  status: FindingStatus
}

export interface IntegrationEvent {
  id: number
  finding_id?: string | null
  process: IntegrationProcess
  endpoint: string
  status_code?: number | null
  ok: boolean
  summary: string
  created_at: string
}

export interface ComplianceItem {
  compliance_log_id: string
  cve_id: string
  package: string
  priority: Priority
  detected_at: string
  fixed_at?: string | null
  time_to_fix_minutes?: number | null
  jira_key?: string | null
  pr_url?: string | null
  status: string
}

export interface ComplianceReport {
  client_name: string
  from: string
  items: ComplianceItem[]
}

export interface Health {
  status: 'ok'
  llm_mode: 'mock' | 'live' | string
  boomi_mode: 'mock' | 'live' | string
  github_mode: 'mock' | 'live' | string
}

export interface FindingFilters {
  scan_id?: string
  priority?: Priority
  reachability?: Reachability
}

export interface ApiErrorBody {
  error: { code: string; message: string }
}
