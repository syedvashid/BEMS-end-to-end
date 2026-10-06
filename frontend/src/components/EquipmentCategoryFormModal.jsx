import { useState } from 'react'
import { api } from '../api/client'
import useFetch from '../hooks/useFetch'
import useSubmit from '../hooks/useSubmit'
import { fieldError } from '../utils/errors'
import { opts, toForm, toPayload } from '../utils/formHelpers'
import { Button, FormError, FormField, Modal } from './ui'

const NUMERIC = ['default_pm_interval_days', 'default_calibration_interval_days']
const EMPTY = {
  parent_category: '', code: '', name: '', description: '',
  default_pm_interval_days: '', default_calibration_interval_days: '', risk_class: 'MEDIUM',
}

export default function EquipmentCategoryFormModal({ category, onClose, onSaved, onStale }) {
  const isEdit = Boolean(category)
  const [form, setForm] = useState(() => toForm(EMPTY, category))
  const { busy, error, run } = useSubmit((e) => { if (e.code === 'stale_version' && onStale) onStale() })
  const all = useFetch('/equipment-categories/', { page_size: 100 })
  const set = (name) => (e) => setForm((f) => ({ ...f, [name]: e.target.value }))
  const err = (name) => fieldError(error, name)

  // Only top-level categories can be groups (two levels maximum).
  const parents = [{ value: '', label: '— none (top level) —' }].concat(
    (all.data?.results ?? [])
      .filter((c) => !c.parent_category && c.public_id !== category?.public_id)
      .map((c) => ({ value: c.public_id, label: `${c.code} - ${c.name}` })),
  )

  const submit = async (e) => {
    e.preventDefault()
    const body = toPayload(form, NUMERIC)
    if (body.code) body.code = body.code.toUpperCase()
    const res = await run(() => (isEdit
      ? api.patch(`/equipment-categories/${category.public_id}/`, { ...body, row_version: category.row_version })
      : api.post('/equipment-categories/', body)))
    if (res) onSaved(res.data, !isEdit)
  }

  return (
    <Modal wide title={isEdit ? 'Edit category' : 'New category'} onClose={onClose}
      footer={<>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" type="submit" form="category-form" loading={busy}>Save</Button>
      </>}>
      <form id="category-form" onSubmit={submit}>
        <FormError error={error} />
        <div className="form-grid">
          <FormField label="Code" name="code" required value={form.code} onChange={set('code')} error={err('code')} maxLength={50} hint="Uppercase letters, digits and _" />
          <FormField label="Name" name="name" required value={form.name} onChange={set('name')} error={err('name')} maxLength={200} />
          <FormField label="Group (parent)" name="parent_category" as="select" options={parents} value={form.parent_category} onChange={set('parent_category')} error={err('parent_category')} />
          <FormField label="Risk class" name="risk_class" as="select" options={opts(['LOW', 'MEDIUM', 'HIGH'])} value={form.risk_class} onChange={set('risk_class')} error={err('risk_class')} />
          <FormField label="PM interval (days)" name="default_pm_interval_days" type="number" min="1" value={form.default_pm_interval_days} onChange={set('default_pm_interval_days')} error={err('default_pm_interval_days')} />
          <FormField label="Calibration interval (days)" name="default_calibration_interval_days" type="number" min="1" value={form.default_calibration_interval_days} onChange={set('default_calibration_interval_days')} error={err('default_calibration_interval_days')} />
          <FormField label="Description" name="description" as="textarea" value={form.description} onChange={set('description')} error={err('description')} maxLength={500} />
        </div>
      </form>
    </Modal>
  )
}