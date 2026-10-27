import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Play } from 'lucide-react'
import { ApiError, createScan } from '../lib/api'
import type { ScanCreateRequest } from '../lib/types'
import Modal from './ui/Modal'
import { useToast } from './ui/Toast'

const input =
  'w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-fg placeholder:text-muted focus-visible:outline-2 focus-visible:outline-accent'
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const BRANCH = /^[\w./-]{1,100}$/

export function validateScanForm(f: { client_name: string; repo_url: string; branch: string; owner_email: string }): string | null {
  if (!f.client_name.trim()) return 'Enter a client name.'
  if (!/^https:\/\/[^\s/]+\/\S+/.test(f.repo_url.trim())) return 'Repository URL must be an https:// link.'
  if (!BRANCH.test(f.branch.trim() || 'main')) return 'Branch name has invalid characters.'
  if (f.owner_email.trim() && !EMAIL.test(f.owner_email.trim())) return 'Owner email looks invalid.'
  return null
}

export default function RunScanModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [form, setForm] = useState({
    client_name: 'Acme Retail',
    repo_url: 'https://github.com/BommepalliRoop/demo-target',
    branch: 'main',
    owner_email: '',
  })
  const [autoFix, setAutoFix] = useState(true)
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const navigate = useNavigate()
  const toast = useToast()
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }))

  async function submit(e?: FormEvent) {
    e?.preventDefault()
    const bad = validateScanForm(form)
    if (bad) return setProblem(bad)
    const body: ScanCreateRequest = {
      client_name: form.client_name.trim(),
      repo_url: form.repo_url.trim(),
      branch: form.branch.trim() || 'main',
      auto_fix: autoFix,
      ...(form.owner_email.trim() ? { owner_email: form.owner_email.trim() } : {}),
    }
    setBusy(true)
    setProblem(null)
    try {
      const { scan_id } = await createScan(body)
      toast.success('Scan started')
      onClose()
      navigate(`/scans/${encodeURIComponent(scan_id)}`)
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) setProblem(err.message) // repo_not_allowed, invalid_request
      else {
        setProblem(err instanceof ApiError ? err.message : 'Could not start the scan.')
        toast.error(err, () => void submit())
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Run scan">
      <form onSubmit={submit} className="flex flex-col gap-3" noValidate>
        <label className="flex flex-col gap-1 text-sm">
          Client
          <input className={input} value={form.client_name} onChange={set('client_name')} autoComplete="off" />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Repository URL
          <input className={input} value={form.repo_url} onChange={set('repo_url')} placeholder="https://github.com/org/repo" autoComplete="off" />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1 text-sm">
            Branch
            <input className={input} value={form.branch} onChange={set('branch')} autoComplete="off" />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Owner email <span className="sr-only">(optional)</span>
            <input className={input} type="email" value={form.owner_email} onChange={set('owner_email')} placeholder="optional" />
          </label>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={autoFix} onChange={(e) => setAutoFix(e.target.checked)} className="h-4 w-4 accent-[#2DD4BF]" />
          Auto-fix reachable vulnerabilities and open pull requests
        </label>
        {problem && <p role="alert" className="text-sm text-danger">{problem}</p>}
        <div className="mt-2 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-lg border border-border px-4 py-2 text-sm hover:bg-white/5 focus-visible:outline-2 focus-visible:outline-accent">
            Cancel
          </button>
          <button
            type="submit"
            disabled={busy}
            className="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg hover:brightness-110 disabled:opacity-60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            <Play size={14} aria-hidden /> {busy ? 'Starting…' : 'Start scan'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
