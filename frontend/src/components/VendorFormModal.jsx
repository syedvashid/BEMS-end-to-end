import { useState } from 'react'
import { api } from '../api/client'
import useSubmit from '../hooks/useSubmit'
import { fieldError } from '../utils/errors'
import { toForm, toPayload } from '../utils/formHelpers'
import { Button, FormError, FormField, Modal } from './ui'

const EMPTY = {
  name: '', is_manufacturer: false, is_supplier: false, is_service_provider: false, gstin: '', pan: '',
  address_line1: '', address_line2: '', city: '', state: '', pin_code: '', phone: '', email: '', rating: '', notes: '',
}
const RATINGS = [{ value: '', label: '— none —' }].concat([1, 2, 3, 4, 5].map((n) => ({ value: String(n), label: String(n) })))

export default function VendorFormModal({ vendor, onClose, onSaved, onStale }) {
  const isEdit = Boolean(vendor)
  const [form, setForm] = useState(() => {
    const f = toForm(EMPTY, vendor)
    f.rating = vendor?.rating ? String(vendor.rating) : ''
    return f
  })
  const { busy, error, run } = useSubmit((e) => { if (e.code === 'stale_version' && onStale) onStale() })
  const set = (name) => (e) => setForm((f) => ({ ...f, [name]: e.target.value }))
  const flag = (name) => (e) => setForm((f) => ({ ...f, [name]: e.target.checked }))
  const err = (name) => fieldError(error, name)

  const submit = async (e) => {
    e.preventDefault()
    const body = toPayload(form, ['rating'])
    const res = await run(() => (isEdit
      ? api.patch(`/vendors/${vendor.public_id}/`, { ...body, row_version: vendor.row_version })
      : api.post('/vendors/', body)))
    if (res) onSaved(res.data, !isEdit)
  }

  return (
    <Modal wide title={isEdit ? 'Edit vendor' : 'New vendor'} onClose={onClose}
      footer={<>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" type="submit" form="vendor-form" loading={busy}>Save</Button>
      </>}>
      <form id="vendor-form" onSubmit={submit}>
        <FormError error={error} />
        <div className="form-grid">
          <FormField label="Name" name="name" required value={form.name} onChange={set('name')} error={err('name')} maxLength={200} />
          <div className="checkbox-group">
            <label className="checkbox-row"><input type="checkbox" checked={form.is_manufacturer} onChange={flag('is_manufacturer')} /> Manufacturer</label>
            <label className="checkbox-row"><input type="checkbox" checked={form.is_supplier} onChange={flag('is_supplier')} /> Supplier</label>
            <label className="checkbox-row"><input type="checkbox" checked={form.is_service_provider} onChange={flag('is_service_provider')} /> Service provider</label>
            {err('is_manufacturer') && <div className="field-error">{err('is_manufacturer')}</div>}
          </div>
          <FormField label="GSTIN" name="gstin" value={form.gstin} onChange={set('gstin')} error={err('gstin')} maxLength={15} />
          <FormField label="PAN" name="pan" value={form.pan} onChange={set('pan')} error={err('pan')} maxLength={10} />
          <FormField label="Address line 1" name="address_line1" value={form.address_line1} onChange={set('address_line1')} error={err('address_line1')} />
          <FormField label="Address line 2" name="address_line2" value={form.address_line2} onChange={set('address_line2')} error={err('address_line2')} />
          <FormField label="City" name="city" value={form.city} onChange={set('city')} error={err('city')} />
          <FormField label="State" name="state" value={form.state} onChange={set('state')} error={err('state')} />
          <FormField label="PIN code" name="pin_code" value={form.pin_code} onChange={set('pin_code')} error={err('pin_code')} maxLength={6} />
          <FormField label="Phone" name="phone" value={form.phone} onChange={set('phone')} error={err('phone')} />
          <FormField label="Email" name="email" type="email" value={form.email} onChange={set('email')} error={err('email')} />
          <FormField label="Rating" name="rating" as="select" options={RATINGS} value={form.rating} onChange={set('rating')} error={err('rating')} />
          <FormField label="Notes" name="notes" as="textarea" value={form.notes} onChange={set('notes')} error={err('notes')} maxLength={1000} />
        </div>
      </form>
    </Modal>
  )
}