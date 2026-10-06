import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { useFacility } from '../context/FacilityContext'
import { cleanParams, parseApiError } from '../utils/errors'

export default function useFetch(path, params = {}, enabled = true) {
  const { facilityId } = useFacility()
  const [tick, setTick] = useState(0)
  const [state, setState] = useState({ data: null, loading: true, error: null })
  const key = JSON.stringify([path, params, facilityId])

  useEffect(() => {
    if (!enabled) return undefined
    let cancelled = false
    setState((s) => ({ ...s, loading: true, error: null }))
    api
      .get(path, { params: cleanParams(params) })
      .then((res) => { if (!cancelled) setState({ data: res.data, loading: false, error: null }) })
      .catch((err) => { if (!cancelled) setState({ data: null, loading: false, error: parseApiError(err) }) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, enabled, tick])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  return { ...state, reload }
}