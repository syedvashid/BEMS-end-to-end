import { useState } from 'react'
import { api } from '../api/client'
import { useFacility } from '../context/FacilityContext'
import useFetch from '../hooks/useFetch'
import useSubmit from '../hooks/useSubmit'
import { fieldError } from '../utils/errors'
import { Button, FormError, FormField, Modal } from './ui'

export default function AssignRolesModal({ user, onClose, onSaved }) {
  const { can, facilities, facilityId } = useFacility()
  const roles = useFetch('/roles/', { page_size: 100 })
  const canOther = can('facility.add') && can('user.change')

  const [facSel, setFacSel] = useState(facilityId)          // facility id or '__other'
  const [otherId, setOtherId] = useState('')
  const [selected, setSelected] = useState(
    () => new Set((user.facility_roles ?? []).filter((r) => r.facility === facilityId).map((r) => r.role)),
  )
  const { busy, error, run } = useSubmit()

  const facilityOptions = canOther
    ? facilities.map((f) => ({ value: f.public_id, label: f.name })).concat([{ value: '__other', label: 'Other facility (paste its ID)…' }])
    : facilities.filter((f) => f.public_id === facilityId).map((f) => ({ value: f.public_id, label: f.name }))

  const changeFacility = (e) => { setFacSel(e.target.value); setSelected(new Set()) }
  const toggle = (id) => setSelected((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n })
  // The API refuses roles that carry permissions the acting user lacks.
  const exceeds = (r) => (r.permission_codes ?? []).some((c) => !can(c))

  const target = facSel === '__other' ? otherId.trim() : facSel

  const submit = async (e) => {
    e.preventDefault()
    const body = { roles: [...selected] }
    if (target !== facilityId) body.facility = target
    const res = await run(() => api.post(`/users/${user.public_id}/facility-roles/`, body))
    if (res) onSaved()
  }

  return (
    <Modal title={`Assign roles: ${user.username}`} onClose={onClose}
      footer={<>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" type="submit" form="assign-form" loading={busy}>Save assignments</Button>
      </>}>
      <form id="assign-form" onSubmit={submit}>
        <FormError error={error} />
        <FormField label="Facility" name="facility" as="select" options={facilityOptions} value={facSel} onChange={changeFacility} error={fieldError(error, 'facility')} />
        {facSel === '__other' && (
          <FormField label="Facility ID" name="other_facility" value={otherId} onChange={(e) => setOtherId(e.target.value)}
            hint="Replaces this user's roles in that facility. An empty selection removes membership." />
        )}
        <h2>Roles</h2>
        {roles.loading && <p className="muted">Loading roles…</p>}
        {roles.error && <div className="alert alert-danger">{roles.error.message}</div>}
        {(roles.data?.results ?? []).map((r) => (
          <label key={r.public_id} className="check" title={exceeds(r) ? 'Includes permissions you do not hold' : undefined}>
            <input type="checkbox" checked={selected.has(r.public_id)} disabled={exceeds(r)} onChange={() => toggle(r.public_id)} />
            {r.name} <span className="muted">({r.code})</span>
          </label>
        ))}
        {fieldError(error, 'roles') && <small className="error-text">{fieldError(error, 'roles')}</small>}
      </form>
    </Modal>
  )
}