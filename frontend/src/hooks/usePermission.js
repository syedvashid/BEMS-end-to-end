import { useFacility } from '../context/FacilityContext'

export default function usePermission(code) {
  const { can } = useFacility()
  return can(code)
}