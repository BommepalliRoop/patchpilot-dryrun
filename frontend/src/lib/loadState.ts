// Load state that keeps the last good data when a refresh fails (RISKS E14).
export interface LoadState<T> {
  data: T | null
  error: string | null
  loading: boolean
}

export type LoadAction<T> = { type: 'start' } | { type: 'ok'; data: T } | { type: 'fail'; message: string }

export const initialLoad = <T,>(): LoadState<T> => ({ data: null, error: null, loading: true })

export function loadReducer<T>(state: LoadState<T>, action: LoadAction<T>): LoadState<T> {
  switch (action.type) {
    case 'start':
      return { ...state, loading: true }
    case 'ok':
      return { data: action.data, error: null, loading: false }
    case 'fail':
      return { ...state, error: action.message, loading: false } // data stays on screen
  }
}
