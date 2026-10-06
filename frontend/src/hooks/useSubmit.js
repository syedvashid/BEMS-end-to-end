import { useCallback, useState } from 'react'
import { parseApiError } from '../utils/errors'

// run(fn) -> fn's result, or undefined when it failed (error state is then set).
export default function useSubmit(onError) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const run = useCallback(async (fn) => {
    setBusy(true)
    setError(null)
    try {
      return await fn()
    } catch (e) {
      const parsed = parseApiError(e)
      setError(parsed)
      if (onError) onError(parsed)
      return undefined
    } finally {
      setBusy(false)
    }
  }, [onError])
  return { busy, error, run }
}