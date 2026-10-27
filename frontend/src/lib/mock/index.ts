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
import { STAGES } from '../types'

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
    jira_key: 'SEC-101', jira_url: 'https://example.atlassian.net/browse/SEC-101', teams_sent: true,
    compliance_log_id: 'log_fnd_07',
  },
  timeline: [{ stage: 'scan', at: '2026-10-28T05:10:05Z', message: 'Detected via OSV' }],
}

export const mockIntegrationEvents: IntegrationEvent[] = [
  {
    id: 1, finding_id: 'fnd_07', process: 'B2', endpoint: '/patchpilot/findings', status_code: 200, ok: true,
    summary: 'Jira SEC-101 created, Teams sent', created_at: '2026-10-28T05:11:40Z',
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

/** Canned SSE stream: one event per stage, then `done`. */
export function mockScanEvents(scanId: string): ScanEvent[] {
  const events: ScanEvent[] = STAGES.map((stage, i) => ({
    scan_id: scanId, stage, status: 'running', message: `Stage ${stage} (mock)`,
    progress: Number(((i + 1) / (STAGES.length + 1)).toFixed(2)), data: {},
  }))
  events.push({ scan_id: scanId, stage: 'done', status: 'completed', message: 'Scan complete', progress: 1, data: {} })
  return events
}
