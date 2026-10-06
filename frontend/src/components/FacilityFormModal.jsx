import { useState } from 'react'
import { api } from '../api/client'
import { useFacility } from '../context/FacilityContext'
import useSubmit from '../hooks/useSubmit'
import { fieldError } from '../utils/errors'
import { Button, FormError, FormField, Modal } from './ui'

const TYPES = ['HOSPITAL', 'CLINIC', 'CAMPUS', 'OTHER'].map((v) => ({ value: v, label: v }))
const EMPTY = {
  code: '', name: '', facility_type: 'HOSPITAL', parent_facility: '', address_line1: '', address_line2: '',
  city: '', state: '', pin_code: '', phone: '', email: '', registration_number: '', timezone: 'Asia/Kolkata',
}

function toForm(f) {
  const out = { ...EMPTY }
  if (f) for (const k of Object.keys(EMPTY)) out[k] = f[k] ?? ''
  return out
}

function toPayload(form) {
  const p = {}
  for (const [k, v] of Object.entries(form)) p[k] = v.trim() === '' ? null : v.trim()
  p.code = p.code ? p.code.toUpperCase() : p.code
  return p
}

export default function FacilityFormModal({ facility, onClose, onSaved, onStale }) {
  const { facilities } = useFacility()
  const isEdit = Boolean(facility)
  const [form, setForm] = useState(() => toForm(facility))
  const { busy, error, run } = useSubmit((e) => { if (e.code === 'stale_version' && onStale) onStale() })
  const set = (name) => (e) => setForm((f) => ({ ...f, [name]: e.target.value }))
  const err = (name) => fieldError(error, name)

  const parents = [{ value: '', label: '— none —' }].concat(
    facilities.filter((f) => f.public_id !== facility?.public_id).map((f) => ({ value: f.public_id, label: f.name })),
  )

  const submit = async (e) => {
    e.preventDefault()
    const res = await run(() => (isEdit
      ? api.patch(`/facilities/${facility.public_id}/`, { ...toPayload(form), row_version: facility.row_version })
      : api.post('/facilities/', toPayload(form))))
    if (res) onSaved(res.data, !isEdit)
  }

  return (
    <Modal wide title={isEdit ? 'Edit facility' : 'New facility'} onClose={onClose}
      footer={<>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" type="submit" form="facility-form" loading={busy}>Save</Button>
      </>}>
      <form id="facility-form" onSubmit={submit}>
        <FormError error={error} />
        <div className="form-grid">
          <FormField label="Code" name="code" required value={form.code} onChange={set('code')} error={err('code')} maxLength={30} />
          <FormField label="Name" name="name" required value={form.name} onChange={set('name')} error={err('name')} maxLength={200} />
          <FormField label="Type" name="facility_type" as="select" options={TYPES} value={form.facility_type} onChange={set('facility_type')} error={err('facility_type')} />
          <FormField label="Parent facility" name="parent_facility" as="select" options={parents} value={form.parent_facility} onChange={set('parent_facility')} error={err('parent_facility')} />
          <FormField label="Address line 1" name="address_line1" value={form.address_line1} onChange={set('address_line1')} error={err('address_line1')} />
          <FormField label="Address line 2" name="address_line2" value={form.address_line2} onChange={set('address_line2')} error={err('address_line2')} />
          <FormField label="City" name="city" value={form.city} onChange={set('city')} error={err('city')} />
          <FormField label="State" name="state" value={form.state} onChange={set('state')} error={err('state')} />
          <FormField label="PIN code" name="pin_code" value={form.pin_code} onChange={set('pin_code')} error={err('pin_code')} maxLength={6} />
          <FormField label="Phone" name="phone" value={form.phone} onChange={set('phone')} error={err('phone')} />
          <FormField label="Email" name="email" type="email" value={form.email} onChange={set('email')} error={err('email')} />
          <FormField label="Registration number" name="registration_number" value={form.registration_number} onChange={set('registration_number')} error={err('registration_number')} />
          <FormField label="Time zone" name="timezone" required value={form.timezone} onChange={set('timezone')} error={err('timezone')} />
        </div>
      </form>
    </Modal>
  )
}