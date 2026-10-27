import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { CheckCircle2, Info, XCircle } from 'lucide-react'
import { ApiError } from '../../lib/api'

type Kind = 'success' | 'error' | 'info'
interface Item {
  id: number
  kind: Kind
  message: string
  retry?: () => void
}
interface Api {
  success: (m: string) => void
  info: (m: string) => void
  /** Human message for any thrown value (E14); `retry` adds a Retry button. */
  error: (e: unknown, retry?: () => void) => void
}

const Ctx = createContext<Api | null>(null)
let nextId = 1

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message
  if (typeof e === 'string') return e
  return 'Something went wrong. Please retry.'
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Item[]>([])
  const dismiss = (id: number) => setItems((l) => l.filter((x) => x.id !== id))
  const push = useCallback((kind: Kind, message: string, retry?: () => void) => {
    const id = nextId++
    setItems((l) => [...l.slice(-3), { id, kind, message, retry }])
    setTimeout(() => setItems((l) => l.filter((x) => x.id !== id)), retry ? 10000 : 5000)
  }, [])
  const api = useMemo<Api>(
    () => ({
      success: (m) => push('success', m),
      info: (m) => push('info', m),
      error: (e, retry) => push('error', errorMessage(e), retry),
    }),
    [push],
  )
  const icon = {
    success: <CheckCircle2 size={18} className="text-success" />,
    error: <XCircle size={18} className="text-danger" />,
    info: <Info size={18} className="text-accent" />,
  }

  return (
    <Ctx.Provider value={api}>
      {children}
      <div aria-live="polite" className="fixed right-4 bottom-4 z-50 flex w-80 flex-col gap-2">
        <AnimatePresence>
          {items.map((t) => (
            <motion.div
              key={t.id}
              layout
              initial={{ opacity: 0, x: 24 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 24 }}
              className="flex items-start gap-2 rounded-xl border border-border bg-surface-2 p-3 text-sm shadow-lg"
            >
              {icon[t.kind]}
              <span className="flex-1">{t.message}</span>
              {t.retry && (
                <button
                  onClick={() => {
                    t.retry?.()
                    dismiss(t.id)
                  }}
                  className="text-accent underline"
                >
                  Retry
                </button>
              )}
              <button onClick={() => dismiss(t.id)} aria-label="Dismiss notification" className="text-muted hover:text-fg">
                ×
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </Ctx.Provider>
  )
}

export function useToast(): Api {
  const c = useContext(Ctx)
  if (!c) throw new Error('useToast needs <ToastProvider>')
  return c
}
