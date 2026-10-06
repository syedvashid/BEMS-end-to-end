import { NavLink, Outlet } from 'react-router-dom'
import DevUserSwitcher from '../components/DevUserSwitcher'
import FacilitySwitcher from '../components/FacilitySwitcher'
import { Button } from '../components/ui'
import { useFacility } from '../context/FacilityContext'
import { MENU } from '../menu'

export default function AppLayout() {
  const { status, error, facilityId, can, refresh } = useFacility()

  let content
  if (status === 'loading') content = <p className="muted">Loading…</p>
  else if (status === 'error') {
    content = (
      <div className="alert alert-danger">
        <p>{error?.status === 401 ? 'Unknown or inactive acting user.' : error?.message}</p>
        <Button onClick={refresh}>Retry</Button>
      </div>
    )
  } else if (!facilityId) {
    content = <div className="alert alert-warning">This account is not a member of any facility. Ask an administrator to assign a role.</div>
  } else content = <Outlet />

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">BEMS</span>
        <span className="spacer" />
        <DevUserSwitcher />
        <FacilitySwitcher />
      </header>
      <div className="body">
        <nav className="sidenav" aria-label="Main">
          {MENU.filter((m) => can(m.permission)).map((m) => (
            <NavLink key={m.to} to={m.to} className={({ isActive }) => (isActive ? 'active' : undefined)}>{m.label}</NavLink>
          ))}
        </nav>
        <main className="content">{content}</main>
      </div>
    </div>
  )
}