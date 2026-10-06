import { useState } from 'react'
import { api } from '../api/client'
import useFetch from '../hooks/useFetch'
import useSubmit from '../hooks/useSubmit'
import { fieldError } from '../utils/errors'
import { toForm, toPayload } from '../utils/formHelpers'
import { Button, FormError, FormField, Modal } from './ui'

const NUMERIC = ['default_pm_interval_days', 'default_calibration_interval_days', 'expected_life_years']
const EMPTY = {
  category: '', manufacturer: '', model_name: '', model_number: '', description: '', risk_class: '',
  default_pm_interval_days: '', default_calibration_interval_days: '', expected_life_years: '',
  cdsco_registration_number: '',
}
const RISKS = [{ value: '', label: 'Use category default' }, ...['LOW', 'MEDIUM', 'HIGH'].map((v) => ({ value: v, label: v }))]

export default function EquipmentModelFormModal({ model, onClose, onSaved, onStale }) {
  const isEdit = Boolean(model)
  const [form, setForm] = useState(() => toForm(EMPTY, model))
  const { busy, error, run } = useSubmit((e) => { if (e.code === 'stale_version' && onStale) onStale() })
  const cats = useFetch('/equipment-categories/', { page_size: 100 })
  const mfrs = useFetch('/vendors/', { is_manufacturer: true, page_size: 100 })
  const set = (name) => (e) => setForm((f) => ({ ...f, [name]: e.target.value }))
  const err = (name) => fieldError(error, name)

  const catList = cats.data?.results ?? []
  const groupIds = new Set(catList.map((c) => c.parent_category).filter(Boolean))   // groups cannot hold models
  const cat = catList.find((c) => c.public_id === form.category)

  const catOptions = [{ value: '', label: '— select —' }].concat(
    catList.filter((c) => !groupIds.has(c.public_id)).map((c) => ({ value: c.public_id, label: `${c.name} (${c.code})` })),
  )
  const mfrOptions = [{ value: '', label: '— select —' }].concat(
    (mfrs.data?.results ?? []).map((v) => ({ value: v.public_id, label: v.name })),
  )

  const submit = async (e) => {
    e.preventDefault()
    const body = toPayload(form, NUMERIC)
    const res = await run(() => (isEdit
      ? api.patch(`/equipment-models/${model.public_id}/`, { ...body, row_version: model.row_version })
      : api.post('/equipment-models/', body)))
    if (res) onSaved(res.data, !isEdit)
  }

  const eff = (own, key) => (own !== '' ? own : (cat?.[key] ?? 'none'))

  return (
    <Modal wide title={isEdit ? 'Edit equipment model' : 'New equipment model'} onClose={onClose}
      footer={<>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" type="submit" form="model-form" loading={busy}>Save</Button>
      </>}>
      <form id="model-form" onSubmit={submit}>
        <FormError error={error} />
        <div className="form-grid">
          <FormField label="Category" name="category" required as="select" options={catOptions} value={form.category} onChange={set('category')} error={err('category')} />
          <FormField label="Manufacturer" name="manufacturer" required as="select" options={mfrOptions} value={form.manufacturer} onChange={set('manufacturer')} error={err('manufacturer')} hint="Only vendors marked as manufacturers" />
          <FormField label="Model name" name="model_name" required value={form.model_name} onChange={set('model_name')} error={err('model_name')} maxLength={200} />
          <FormField label="Model number" name="model_number" required value={form.model_number} onChange={set('model_number')} error={err('model_number')} maxLength={100} />
          <FormField label="Risk class" name="risk_class" as="select" options={RISKS} value={form.risk_class} onChange={set('risk_class')} error={err('risk_class')}
            hint={`Effective: ${form.risk_class || cat?.risk_class || '—'}`} />
          <FormField label="PM interval (days)" name="default_pm_interval_days" type="number" min="1" value={form.default_pm_interval_days} onChange={set('default_pm_interval_days')} error={err('default_pm_interval_days')}
            hint={`Effective: ${eff(form.default_pm_interval_days, 'default_pm_interval_days')} (blank = category default)`} />
          <FormField label="Calibration interval (days)" name="default_calibration_interval_days" type="number" min="1" value={form.default_calibration_interval_days} onChange={set('default_calibration_interval_days')} error={err('default_calibration_interval_days')}
            hint={`Effective: ${eff(form.default_calibration_interval_days, 'default_calibration_interval_days')} (blank = category default)`} />
          <FormField label="Expected life (years)" name="expected_life_years" type="number" min="1" value={form.expected_life_years} onChange={set('expected_life_years')} error={err('expected_life_years')} />
          <FormField label="CDSCO registration no." name="cdsco_registration_number" value={form.cdsco_registration_number} onChange={set('cdsco_registration_number')} error={err('cdsco_registration_number')} maxLength={100} />
          <FormField label="Description" name="description" as="textarea" value={form.description} onChange={set('description')} error={err('description')} maxLength={500} />
        </div>
      </form>
    </Modal>
  )
}