import { DEV_AUTH } from '../api/client'
import { useActingUser } from '../context/ActingUserContext'
import { DEV_USERS } from '../utils/devUsers'

export default function DevUserSwitcher() {
  const { username, setUsername } = useActingUser()
  if (!DEV_AUTH) return null
  return (
    <div className="row">
      <span className="dev-badge">DEV MODE</span>
      <label htmlFor="dev-user">Acting as</label>
      <select id="dev-user" value={username ?? ''} onChange={(e) => setUsername(e.target.value)}>
        {DEV_USERS.map((u) => <option key={u.username} value={u.username}>{u.label}</option>)}
      </select>
    </div>
  )
}