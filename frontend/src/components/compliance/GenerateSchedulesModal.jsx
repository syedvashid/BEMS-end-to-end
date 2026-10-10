import { useState } from 'react'
import { Button, FormError, FormField, Modal } from '../ui'
import { api, fieldError, nn, useForm, useOptions, useSubmit, withBlank } from './shared'

export default function GenerateSchedulesModal({ onClose, onDone }) {
  const models = useOptions('/equipment-models/', (m) => ({ value: m.public_id, label: `${m.model_name} ${m.model_number || ''}` }))
  const cats = useOptions('/equipment-categories/', (c) => ({ value: c.public_id, label: `${c.code} — ${c.name}` }))
  const { busy, error, run } = useSubmit()
  const [result, setResult] = useState(null)
  const { v, bind } = useForm({
    scope: 'category', target: '', frequency_type: '', frequency_value: '', last_calibrated_date: '', lead_days: 30,
    on_fail_hold_equipment: true, on_fail_open_work_order: true,
  })
  const fe = (n) => fieldError(error, n)
  const check = (name) => ({ type: 'checkbox', checked: !!v[name], onChange: bind(name).onChange })

  const go = () => run(async () => {
    const body = {
      [v.scope === 'model' ? 'equipment_model' : 'category']: v.target,
      lead_days: Number(v.lead_days), last_calibrated_date: nn(v.last_calibrated_date),
      on_fail_hold_equipment: v.on_fail_hold_equipment, on_fail_open_work_order: v.on_fail_open_work_order,
    }
    if (v.frequency_type && v.frequency_value) { body.frequency_type = v.frequency_type; body.frequency_value = Number(v.frequency_value) }
    const r = await api.post('/calibration-schedules/generate/', body)
    setResult(r.data)
  })

  return (
    <Modal title="Generate calibration schedules" onClose={result ? onDone : onClose}
      footer={result ? <Button onClick={onDone}>Close</Button> : <>
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button onClick={go} loading={busy} disabled={!v.target}>Generate</Button></>}>
      {result ? (
        <p>Created {result.created}. Skipped {result.skipped_existing} (already scheduled) and {result.skipped_no_interval} (no interval set).</p>
      ) : (<>
        <FormError error={error} />
        <p>Creates a schedule for every commissioned equipment of the chosen model or category that has none yet.</p>
        <FormField label="Scope" as="select" options={[{ value: 'category', label: 'Category' }, { value: 'model', label: 'Equipment model' }]} {...bind('scope')} />
        <FormField label={v.scope === 'model' ? 'Equipment model' : 'Category'} as="select" required
          options={withBlank(v.scope === 'model' ? models : cats)} error={fe('scope') || fe('category') || fe('equipment_model')} {...bind('target')} />
        <FormField label="Frequency type (optional)" as="select" hint="Leave empty to use each equipment's default interval (in days)"
          options={[{ value: '', label: 'Use default interval' }, { value: 'DAYS', label: 'Days' }, { value: 'MONTHS', label: 'Months' }]} {...bind('frequency_type')} />
        {v.frequency_type && <FormField label="Every" type="number" min="1" error={fe('frequency_value')} {...bind('frequency_value')} />}
        <FormField label="Last calibrated (optional)" type="date" error={fe('last_calibrated_date')} {...bind('last_calibrated_date')} />
        <FormField label="Lead days" type="number" min="0" {...bind('lead_days')} />
        <label><input {...check('on_fail_hold_equipment')} /> On failure: place equipment out of service</label><br />
        <label><input {...check('on_fail_open_work_order')} /> On failure: open a corrective work order</label>
      </>)}
    </Modal>
  )
}