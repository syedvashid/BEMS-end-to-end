import { useState } from 'react'
import { Button, Modal } from '../ui'
import { ErrBox, Field, api, fieldError, parseApiError } from './shared.jsx'

export default function ChargeItemFormModal({ item, onClose, onSaved }) {
  const [f, setF] = useState({
    item_code: item?.item_code || '', name: item?.name || '', unit_label: item?.unit_label || 'hour',
    default_rate: item?.default_rate ?? '', description: item?.description || '',
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }))

  async function save() {
    setBusy(true)
    setError(null)
    const body = { ...f, default_rate: f.default_rate === '' ? null : f.default_rate, description: f.description || null }
    try {
      if (item) await api.put(`/charge-items/${item.public_id}/`, { ...body, row_version: item.row_version })
      else await api.post('/charge-items/', body)
      onSaved()
    } catch (err) {
      console.error('[billing] save charge item failed', err)
      setError(parseApiError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal title={item ? 'Edit charge item' : 'New charge item'} onClose={onClose}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} onClick={save}>Save</Button></>}>
      <ErrBox error={error} />
      <Field label="Item code" name="item_code" as="input" required value={f.item_code} onChange={set('item_code')}
        error={fieldError(error, 'item_code')} hint="Letters, digits, '.', '_' or '-'" />
      <Field label="Name" name="name" as="input" required value={f.name} onChange={set('name')} error={fieldError(error, 'name')} />
      <Field label="Unit" name="unit_label" as="input" required value={f.unit_label} onChange={set('unit_label')}
        error={fieldError(error, 'unit_label')} hint="For example hour, day, use" />
      <Field label="Default rate (INR)" name="default_rate" as="input" type="number" min="0" step="0.01" required
        value={f.default_rate} onChange={set('default_rate')} error={fieldError(error, 'default_rate')} />
      <Field label="Description" name="description" as="textarea" value={f.description} onChange={set('description')}
        error={fieldError(error, 'description')} />
    </Modal>
  )
}
