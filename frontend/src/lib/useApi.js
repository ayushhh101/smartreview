import { useEffect, useState } from 'react'
import { api } from './api.js'
export function useApi(path) {
  const [state, set] = useState({ data: null, error: null, loading: true })
  useEffect(() => {
    let live = true
    set({ data: null, error: null, loading: true })
    api(path).then(d => live && set({ data: d, error: null, loading: false }))
              .catch(e => live && set({ data: null, error: e, loading: false }))
    return () => { live = false }
  }, [path])
  return state
}
