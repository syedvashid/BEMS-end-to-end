import { useFacility } from '../context/FacilityContext'

// <PermissionGate code="user.view"> or anyOf={['a','b']}
export default function PermissionGate({ code, anyOf, fallback = null, children }) {
  const { can } = useFacility()
  const allowed = anyOf ? anyOf.some(can) : can(code)
  return allowed ? children : fallback
}