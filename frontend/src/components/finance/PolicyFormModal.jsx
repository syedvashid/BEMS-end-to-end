import { useState } from 'react'
import { api } from '../../api/client'
import useFetch from '../../hooks/useFetch'
import { Button, FormField, Modal } from '../ui'
import { EquipmentPicker, ErrorNote, fieldErr, nn, useAction } from './shared'

const num = (v) => (v === '' || v === null || v === undefined ? null : Number(v))

export default function PolicyFormModal({ policy, onClose, onDone }) {
  const editing = !!policy
  const cats = useFetch('/equipment-categories/', { page_size: 100 }, !editing)
  const [v, setV] = useState({
    scope: policy?.scope || 'CATEGORY', category: '', equipment: '',
    method: policy?.method || 'STRAIGHT_LINE',
    useful_life_years: policy?.useful_life_years ?? '', rate_percent: policy?.rate_percent ?? '',
    salvage_percent: policy?.salvage_percent ?? '5', start_rule: policy?.start_rule || 'COMMISSIONING_DATE',
    notes: policy?.notes || '',
  })
  const set = (k) => (e) => setV((s) => ({ ...s, [k]: e.target ? e.target.value : e }))
  const act = useAction()

  const submit = () => act.run(async () => {
    const body = {
      method: v.method, salvage_percent: num(v.salvage_percent), start_rule: v.start_rule, notes: nn(v.notes),
      useful_life_years: v.method === 'STRAIGHT_LINE' ? num(v.useful_life_years) : null,
      rate_percent: v.method === 'WRITTEN_DOWN_VALUE' ? num(v.rate_percent) : null,
    }
    if (editing) {
      await api.patch(`/depreciation-policies/${policy.public_id}/`, { ...body, row_version: policy.row_version })
    } else {
      await api.post('/depreciation-policies/', {
        ...body, category: v.scope === 'CATEGORY' ? nn(v.category) : null, equipment: v.scope === 'EQUIPMENT' ? nn(v.equipment) : null,
      })
    }
    onDone()
  })

  const catOptions = [{ value: '', label: 'Select category…' },
    ...(cats.data?.results || []).map((c) => ({ value: c.public_id, label: `${c.code} – ${c.name}` }))]

  return (
    <Modal title={editing ? 'Edit depreciation policy' : 'New depreciation policy'} onClose={onClose}
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={act.busy} onClick={submit}>Save</Button></>}>
      {!editing && (
        <>
          <FormField label="Applies to" name="scope" as="select" value={v.scope} onChange={set('scope')}
            options={[{ value: 'CATEGORY', label: 'A category (or group)' }, { value: 'EQUIPMENT', label: 'One equipment (override)' }]} />
          {v.scope === 'CATEGORY'
            ? <FormField label="Category" name="category" as="select" required value={v.category} options={catOptions}
              error={fieldErr(act.error, 'category')} onChange={set('category')} />
            : <EquipmentPicker value={v.equipment} onChange={(id) => setV((s) => ({ ...s, equipment: id }))} required
              error={fieldErr(act.error, 'equipment')} />}
        </>
      )}
      <FormField label="Method" name="method" as="select" value={v.method} onChange={set('method')}
        options={[{ value: 'STRAIGHT_LINE', label: 'Straight line' }, { value: 'WRITTEN_DOWN_VALUE', label: 'Written-down value' }]} />
      {v.method === 'STRAIGHT_LINE'
        ? <FormField label="Useful life (years)" name="useful_life_years" type="number" step="0.01" required value={v.useful_life_years}
          error={fieldErr(act.error, 'useful_life_years')} onChange={set('useful_life_years')} />
        : <FormField label="Rate (% per year)" name="rate_percent" type="number" step="0.001" required value={v.rate_percent}
          error={fieldErr(act.error, 'rate_percent')} onChange={set('rate_percent')} />}
      <FormField label="Salvage (% of cost)" name="salvage_percent" type="number" step="0.01" value={v.salvage_percent}
        error={fieldErr(act.error, 'salvage_percent')} onChange={set('salvage_percent')} />
      <FormField label="Start counting from" name="start_rule" as="select" value={v.start_rule} onChange={set('start_rule')}
        options={[{ value: 'COMMISSIONING_DATE', label: 'Commissioning date' }, { value: 'INVOICE_DATE', label: 'Invoice date (falls back to commissioning)' }]} />
      <FormField label="Notes" name="notes" as="textarea" value={v.notes} onChange={set('notes')} />
      <p className="muted">A policy change affects future months only. Past entries are never restated.</p>
      <ErrorNote error={act.error} />
    </Modal>
  )
}
