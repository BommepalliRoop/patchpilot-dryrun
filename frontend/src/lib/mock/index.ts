// Fixtures copied from the contracts (docs/API_CONTRACTS.md, contracts/). Used when VITE_USE_MOCK=true.
import type {
  ComplianceReport,
  FindingDetail,
  FindingSummary,
  Health,
  IntegrationEvent,
  Scan,
  ScanEvent,
} from '../types'

export const MOCK_SCAN_ID = 'scn_01'

export const mockScans: Scan[] = [
  {
    scan_id: MOCK_SCAN_ID,
    client_name: 'Acme Retail',
    repo_url: 'https://github.com/BommepalliRoop/demo-target',
    branch: 'main',
    status: 'completed',
    current_stage: 'done',
    started_at: '2026-10-28T05:10:00Z',
    finished_at: '2026-10-28T05:11:42Z',
    languages: [
      { ecosystem: 'PyPI', manifests: ['requirements.txt'], analysis: 'deep' },
      { ecosystem: 'npm', manifests: ['tools/package-lock.json'], analysis: 'generic' },
    ],
    stats: { total_alerts: 12, reachable: 2, unsure: 1, not_reachable: 9, p1: 1, p2: 1, fixed: 2, prs_opened: 2 },
  },
]

export const mockFindings: FindingSummary[] = [
  {
    finding_id: 'fnd_07', cve_id: 'CVE-2020-14343', package: 'pyyaml', installed_version: '5.3.1',
    fixed_version: '5.4.1', cvss: 9.8, reachability: 'reachable', confidence: 0.93, score: 10.0, priority: 'P1',
    status: 'fixed', kev: false, epss: 0.0598, epss_percentile: 0.9326, ecosystem: 'PyPI', analysis: 'deep',
  },
  {
    finding_id: 'fnd_08', cve_id: 'CVE-2023-32681', package: 'requests', installed_version: '2.25.1',
    fixed_version: '2.31.0', cvss: 6.1, reachability: 'not_reachable', confidence: 0.9, score: 1.8, priority: 'P4',
    status: 'open', kev: false, epss: 0.0021, epss_percentile: 0.58, ecosystem: 'PyPI', analysis: 'deep',
  },
  {
    finding_id: 'fnd_09', cve_id: 'CVE-2024-22195', package: 'jinja2', installed_version: '2.11.3',
    fixed_version: '3.1.3', cvss: 5.4, reachability: 'unsure', confidence: 0.55, score: 3.2, priority: 'P4',
    status: 'open', kev: false, epss: 0.0035, epss_percentile: 0.67, ecosystem: 'PyPI', analysis: 'deep',
  },
  ...(
    [
      ['CVE-2021-33503', 'urllib3', '1.26.4', '1.26.5', 7.5, 'PyPI', false],
      ['CVE-2023-30861', 'flask', '1.1.2', '2.2.5', 7.5, 'PyPI', false],
      ['CVE-2023-25577', 'werkzeug', '1.0.1', '2.2.3', 7.5, 'PyPI', false],
      ['CVE-2022-23491', 'certifi', '2021.5.30', '2022.12.7', 6.8, 'PyPI', false],
      ['CVE-2021-23337', 'lodash', '4.17.20', '4.17.21', 7.2, 'npm', true],
      ['CVE-2020-8203', 'lodash', '4.17.20', '4.17.21', 7.4, 'npm', false],
      ['CVE-2020-28500', 'lodash', '4.17.20', '4.17.21', 5.3, 'npm', false],
      ['CVE-2021-3918', 'json-schema', '0.2.3', '0.4.0', 9.8, 'npm', false],
      ['CVE-2022-24785', 'moment', '2.29.1', '2.29.2', 7.5, 'npm', false],
    ] as const
  ).map(([cve, pkg, inst, fixed, cvss, eco, kev], i): FindingSummary => ({
    finding_id: `fnd_${String(10 + i).padStart(2, '0')}`, cve_id: cve, package: pkg, installed_version: inst,
    fixed_version: fixed, cvss, reachability: 'not_reachable', confidence: 0.9,
    score: Number((cvss * 0.3 * (kev ? 1.3 : 1)).toFixed(1)), priority: 'P4', status: 'open', kev,
    epss: kev ? 0.41 : 0.004, epss_percentile: kev ? 0.97 : 0.55, ecosystem: eco,
    analysis: eco === 'PyPI' ? 'deep' : 'generic',
  })),
]

export const mockFindingDetail: FindingDetail = {
  ...mockFindings[0],
  summary: 'Arbitrary code execution via full_load / FullLoader',
  kev_date_added: null,
  vulnerable_symbols: ['yaml.load', 'yaml.full_load'],
  evidence: [
    {
      file: 'app/routes.py', line: 42, in_route: true, start_line: 27,
      code_snippet:
        "@app.route('/import', methods=['POST'])\ndef import_config():\n" +
        '    data = yaml.load(request.data, Loader=yaml.FullLoader)\n    return jsonify(data)\n',
    },
  ],
  ai_explanation: 'User-supplied YAML from POST /import reaches yaml.load without SafeLoader.',
  fix: {
    new_version: '5.4.1', attempts: 1, tests_passed: true,
    patch_diff: '--- a/requirements.txt\n+++ b/requirements.txt\n@@ -1 +1 @@\n-PyYAML==5.3.1\n+PyYAML==5.4.1\n',
    pr_url: 'https://github.com/BommepalliRoop/demo-target/pull/3', status: 'fixed',
  },
  integration: {
    jira_key: 'SEC-101', jira_url: 'https://example.atlassian.net/browse/SEC-101', slack_sent: true,
    compliance_log_id: 'log_fnd_07',
  },
  timeline: [{ stage: 'scan', at: '2026-10-28T05:10:05Z', message: 'Detected via OSV' }],
}

/** Extra detail fixtures for the states the page must handle (needs_human, fixed_untested, not_reachable). */
const base = mockFindingDetail
const notReachable = mockFindings.find((f) => f.finding_id === 'fnd_08')!
const unsure = mockFindings.find((f) => f.finding_id === 'fnd_09')!
export const mockFindingDetails: Record<string, FindingDetail> = {
  [base.finding_id]: base,
  fnd_08: {
    ...notReachable,
    summary: 'Requests leaks Proxy-Authorization header on redirect to HTTPS',
    kev_date_added: null,
    vulnerable_symbols: ['requests.Session.rebuild_proxies'],
    evidence: [],
    ai_explanation: 'No call to the vulnerable proxy code path exists in this repository; requests is only used for plain GET calls.',
    fix: null,
    integration: null,
    timeline: [
      { stage: 'scan', at: '2026-10-28T05:10:05Z', message: 'Detected via OSV' },
      { stage: 'reachability', at: '2026-10-28T05:10:40Z', message: 'Vulnerable symbol never called: not reachable' },
    ],
  },
  fnd_09: {
    ...unsure,
    summary: 'Jinja2 xmlattr filter allows attribute injection',
    kev_date_added: null,
    vulnerable_symbols: ['jinja2.filters.do_xmlattr'],
    evidence: [],
    ai_explanation: 'Templates are loaded dynamically, so the AI could not prove whether xmlattr is used. A human should check.',
    fix: null,
    integration: null,
    timeline: [{ stage: 'reachability', at: '2026-10-28T05:10:41Z', message: 'Unsure (confidence 0.55)' }],
  },
  fnd_20: {
    ...base,
    finding_id: 'fnd_20', cve_id: 'CVE-2021-23337', package: 'lodash', installed_version: '4.17.20', fixed_version: '4.17.21',
    cvss: 7.2, score: 9.1, priority: 'P2', status: 'needs_human', kev: true, epss: 0.41, epss_percentile: 0.97,
    ecosystem: 'npm', analysis: 'generic',
    summary: 'Command injection via template',
    kev_date_added: '2026-09-02',
    vulnerable_symbols: ['_.template'],
    evidence: [
      {
        file: 'tools/render.js', line: 9, in_route: false, start_line: 5,
        code_snippet:
          "const _ = require('lodash')\nfunction render(tpl, data) {\n  // tpl comes from CLI args\n  return _.template(tpl)(data)\n}\n",
      },
    ],
    ai_explanation: 'tools/render.js passes an externally supplied template string to _.template.',
    fix: { new_version: '4.17.21', attempts: 2, tests_passed: false, patch_diff: '', pr_url: null, status: 'needs_human' },
    integration: { jira_key: 'SEC-102', jira_url: 'https://example.atlassian.net/browse/SEC-102', slack_sent: true, compliance_log_id: 'log_fnd_20' },
    timeline: [{ stage: 'fix', at: '2026-10-28T05:11:20Z', message: 'Tests still failing after 2 AI patch attempts' }],
  },
  fnd_21: {
    ...base,
    finding_id: 'fnd_21', cve_id: 'CVE-2023-30861', package: 'flask', installed_version: '1.1.2', fixed_version: '2.2.5',
    cvss: 7.5, score: 6.4, priority: 'P3', status: 'fixed', kev: false, epss: null, epss_percentile: null,
    ecosystem: 'Maven', analysis: 'generic',
    fix: { ...base.fix!, new_version: '2.2.5', tests_passed: false, status: 'fixed_untested', attempts: 0 },
    integration: { jira_key: null, jira_url: null, slack_sent: false, compliance_log_id: null },
  },
}

export const mockIntegrationEvents: IntegrationEvent[] = [
  {
    id: 1, finding_id: 'fnd_07', process: 'B2', endpoint: '/patchpilot/findings', status_code: 200, ok: true,
    summary: 'Jira SEC-101 created, Slack sent', created_at: '2026-10-28T05:11:40Z',
  },
]

export const mockCompliance: ComplianceReport = {
  client_name: 'Acme Retail',
  from: '2026-10-01',
  items: [
    {
      compliance_log_id: 'log_fnd_07', cve_id: 'CVE-2020-14343', package: 'pyyaml', priority: 'P1',
      detected_at: '2026-10-28T05:10:05Z', fixed_at: '2026-10-28T05:11:40Z', time_to_fix_minutes: 2,
      jira_key: 'SEC-101', pr_url: 'https://github.com/BommepalliRoop/demo-target/pull/3', status: 'fixed',
    },
  ],
}

export const mockHealth: Health = { status: 'ok', llm_mode: 'mock', boomi_mode: 'mock', github_mode: 'mock' }

// ---- Scripted scan run (~25 s) -------------------------------------------------------------------
// One entry per SSE event: [offset ms, stage, status, message, progress]. Mock mode replays this from the moment
// startMockRun() is called, so the whole scan flow is watchable without the backend.
type Step = [number, ScanEvent['stage'], string, string, number]
const SCRIPT: Step[] = [
  [600, 'clone', 'running', 'Cloning BommepalliRoop/demo-target@main', 0.03],
  [2400, 'clone', 'completed', 'Cloned 41 files', 0.08],
  [3000, 'scan', 'running', 'Detected PyPI (requirements.txt) and npm (tools/package-lock.json)', 0.12],
  [5000, 'scan', 'running', 'OSV-Scanner found 12 vulnerable dependency versions', 0.2],
  [6200, 'scan', 'completed', 'Threat intel: 1 on CISA KEV, EPSS loaded for 12 CVEs', 0.25],
  [7000, 'symbols', 'running', 'Extracting vulnerable symbols for pyyaml, jinja2, lodash...', 0.3],
  [9000, 'symbols', 'completed', 'Vulnerable symbols ready (yaml.load, yaml.full_load, _.template)', 0.38],
  [9800, 'reachability', 'running', 'Checking yaml.load in app/routes.py', 0.45],
  [12000, 'reachability', 'running', 'yaml.load reachable from POST /import (in route)', 0.52],
  [14000, 'reachability', 'completed', '2 reachable, 1 unsure, 9 not reachable', 0.6],
  [14800, 'risk', 'running', 'Scoring risk: CVSS x reachability x exposure x threat', 0.65],
  [16200, 'risk', 'completed', '1 P1, 1 P2, 10 lower priority', 0.7],
  [17000, 'fix', 'running', 'Upgrading PyYAML 5.3.1 -> 5.4.1 in a temporary venv', 0.74],
  [19500, 'fix', 'running', 'pytest -q: all tests green (attempt 1)', 0.8],
  [20500, 'fix', 'completed', '2 packages fixed', 0.85],
  [21300, 'pr', 'running', 'Opening pull request for pyyaml', 0.88],
  [22800, 'pr', 'completed', 'Pull requests opened (2)', 0.92],
  [23500, 'notify', 'running', 'Notifying Boomi: Jira ticket, Slack alert, compliance log', 0.96],
  [24500, 'notify', 'completed', 'Jira SEC-101 created, Slack sent', 0.99],
  [25000, 'done', 'completed', 'Scan complete', 1],
]
export const MOCK_RUN_MS = SCRIPT[SCRIPT.length - 1][0]

export function mockScanScript(scanId: string): { at: number; event: ScanEvent }[] {
  return SCRIPT.map(([at, stage, status, message, progress]) => ({
    at, event: { scan_id: scanId, stage, status, message, progress, data: {} },
  }))
}

let runStartedAt: number | null = null
export const startMockRun = () => {
  runStartedAt = Date.now()
}
export const mockElapsed = () => (runStartedAt === null ? null : Date.now() - runStartedAt)

/** Stage reached by the scripted run right now; `null` when no run is in progress (completed fixtures apply). */
export function mockRunStage(): ScanEvent['stage'] | null {
  const elapsed = mockElapsed()
  if (elapsed === null || elapsed >= MOCK_RUN_MS - 100) return null
  const reached = SCRIPT.filter(([at]) => at <= elapsed)
  return reached.length ? reached[reached.length - 1][1] : 'clone'
}
