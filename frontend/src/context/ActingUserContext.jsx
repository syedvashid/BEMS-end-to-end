import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import { session } from '../api/session'
import { DEV_AUTH } from '../api/client'
import { DEV_USERS } from '../utils/devUsers'

const ActingUserContext = createContext(null)

// DEV ONLY: chosen username lives in memory and is sent as X-Dev-User.
export function ActingUserProvider({ children }) {
  const [username, setUsernameState] = useState(() => {
    const initial = DEV_AUTH ? DEV_USERS[0].username : null
    session.username = initial
    return initial
  })
  const setUsername = useCallback((u) => {
    session.username = u
    setUsernameState(u)
  }, [])
  const value = useMemo(() => ({ username, setUsername }), [username, setUsername])
  return <ActingUserContext.Provider value={value}>{children}</ActingUserContext.Provider>
}

export function useActingUser() {
  return useContext(ActingUserContext)
}