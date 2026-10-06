import { useFacility } from '../context/FacilityContext'

export default function FacilitySwitcher() {
  const { facilities, facilityId, selectFacility, me } = useFacility()
  if (!facilities.length) return null
  const roles = (me?.roles ?? []).map((r) => r.name).join(', ')
  return (
    <div className="row">
      <label htmlFor="facility">Facility</label>
      <select id="facility" value={facilityId ?? ''} onChange={(e) => selectFacility(e.target.value)}>
        {facilities.map((f) => <option key={f.public_id} value={f.public_id}>{f.name}</option>)}
      </select>
      {roles && <span style={{ fontSize: 12 }}>({roles})</span>}
    </div>
  )
}