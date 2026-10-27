import { useCallback, useEffect, useReducer, useRef, type DependencyList, type Reducer } from 'react'
import { errorMessage } from '../components/ui/Toast'
import { initialLoad, loadReducer, type LoadAction, type LoadState } from './loadState'

/** Fetch with loading / error / last-good-data semantics; `reload` is stable and ignores out-of-order responses. */
export function useLoad<T>(fn: () => Promise<T>, deps: DependencyList) {
  const [state, dispatch] = useReducer(loadReducer as Reducer<LoadState<T>, LoadAction<T>>, undefined, initialLoad<T>)
  const fnRef = useRef(fn)
  fnRef.current = fn
  const seq = useRef(0)

  const reload = useCallback(async () => {
    const mine = ++seq.current
    dispatch({ type: 'start' })
    try {
      const data = await fnRef.current()
      if (mine === seq.current) dispatch({ type: 'ok', data })
    } catch (e) {
      if (mine === seq.current) dispatch({ type: 'fail', message: errorMessage(e) })
    }
  }, [])

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => void reload(), deps)
  return { ...state, reload }
}
