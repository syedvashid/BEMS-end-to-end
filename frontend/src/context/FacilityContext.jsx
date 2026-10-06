import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import { session } from '../api/session'
import { parseApiError } from '../utils/errors'
import { useActingUser } from './ActingUserContext'

const FacilityContext = createContext(null)

// Loads /me/ (facilities) then /me/ again with the chosen facility (roles + permissions).
export function FacilityProvider({ children }) {
  const { username } = useActingUser()
  const [state, setState] = useState({ status: 'loading', me: null, facilities: [], facilityId: null, error: null })
  const seq = useRef(0)
  const last = useRef(null)

  const load = useCallback(async (preferred) => {
    const mine = ++seq.current
    setState((s) => ({ ...s, status: 'loading', error: null }))
    try {
      session.facilityId = null
      const { data: base } = await api.get('/me/')
      if (mine !== seq.current) return
      const ids = base.facilities.map((f) => f.public_id)
      const target = ids.includes(preferred) ? preferred : (ids[0] ?? null)
      let me = base
      if (target) {
        session.facilityId = target
        me = (await api.get('/me/')).data
        if (mine !== seq.current) return
      }
      last.current = target
      setState({ status: 'ready', me, facilities: base.facilities, facilityId: target, error: null })
    } catch (e) {
      if (mine === seq.current) setState((s) => ({ ...s, status: 'error', error: parseApiError(e) }))
    }
  }, [])

  useEffect(() => { load(last.current) }, [username, load])

  const perms = useMemo(() => new Set(state.me?.permissions ?? []), [state.me])
  const value = useMemo(() => ({
    ...state,
    can: (code) => perms.has(code),
    selectFacility: (id) => load(id),
    refresh: () => load(last.current),
  }), [state, perms, load])

  return <FacilityContext.Provider value={value}>{children}</FacilityContext.Provider>
}

export function useFacility() {
  return useContext(FacilityContext)
}