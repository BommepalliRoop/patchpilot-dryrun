import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, resetDemo } from '../lib/api'
import Modal from './ui/Modal'
import { useToast } from './ui/Toast'

export const RESET_EVENT = 'patchpilot:reset'

/** True for a bare Shift+R outside text fields (RISKS S8). */
export function isResetShortcut(e: Pick<KeyboardEvent, 'key' | 'shiftKey' | 'ctrlKey' | 'metaKey' | 'altKey' | 'target'>): boolean {
  const t = e.target as HTMLElement | null
  const typing = !!t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable)
  return e.key === 'R' && e.shiftKey && !e.ctrlKey && !e.metaKey && !e.altKey && !typing
}

/**
 * Hidden demo reset: Shift+R asks for the admin key and calls POST /api/demo/reset with it (RISKS S8).
 * The key lives only in this component state while the dialog is open; it is never bundled, persisted
 * in browser storage, or put in the URL.
 */
export default function DemoReset() {
  const [open, setOpen] = useState(false)
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const navigate = useNavigate()
  const toast = useToast()

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isResetShortcut(e)) {
        e.preventDefault()
        setOpen(true)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  const close = () => {
    setOpen(false)
    setKey('')
    setProblem(null)
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!key.trim()) return setProblem('Enter the admin key.')
    setBusy(true)
    setProblem(null)
    try {
      await resetDemo(key.trim())
      close()
      toast.success('Demo data reset')
      navigate('/')
      window.dispatchEvent(new Event(RESET_EVENT))
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setProblem('That key was rejected.')
      else if (err instanceof ApiError && err.status === 404) setProblem('Demo reset is disabled on this server.')
      else setProblem(err instanceof ApiError ? err.message : 'Reset failed. Please retry.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open={open} onClose={close} title="Reset demo data">
      <form onSubmit={submit} className="flex flex-col gap-3">
        <p className="text-sm text-muted">This clears all scans and findings. Enter the admin key to continue.</p>
        <label className="flex flex-col gap-1 text-sm">
          Admin key
          <input
            type="password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            autoComplete="off"
            autoFocus
            className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-fg focus-visible:outline-2 focus-visible:outline-accent"
          />
        </label>
        {problem && <p role="alert" className="text-sm text-danger">{problem}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={close} className="rounded-lg border border-border px-4 py-2 text-sm hover:bg-white/5 focus-visible:outline-2 focus-visible:outline-accent">
            Cancel
          </button>
          <button type="submit" disabled={busy} className="rounded-lg bg-danger px-4 py-2 text-sm font-semibold text-white hover:brightness-110 disabled:opacity-60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-danger">
            {busy ? 'Resetting…' : 'Reset'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
