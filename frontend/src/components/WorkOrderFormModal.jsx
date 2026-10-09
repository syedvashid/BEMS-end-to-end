import { useState } from 'react'
import { api } from '../api/client'
import { Button, FormField, Modal } from './ui'
import EquipmentPicker from './EquipmentPicker'
import useFetch from '../hooks/useFetch'
import { PRIORITIES, PRIORITY_LABEL, apiError, errorText, fe, opts, toNull } from '../utils/maintenance'

// New CORRECTIVE / manual PREVENTIVE work order.
// preset: { equipment:{public_id,label}, parent_work_order:'<public_id>', problem_description, work_order_type }
export default function WorkOrderFormModal({ preset = {}, onClose, onDone }) {
  const templates = useFetch('/checklist-templates/', { page_size: 100 }, true)
  const [equipment, setEquipment] = useState(preset.equipment || null)
  const [f, setF] = useState({
    work_order_type: preset.work_order_type || 'CORRECTIVE', priority: 'MEDIUM', due_date: '',
    problem_description: preset.problem_description || '', checklist_template: '',
  })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }))

  const submit = async () => {
    setBusy(true); setErr(null)
    try {
      const res = await api.post('/work-orders/', {
        work_order_type: f.work_order_type, equipment: equipment?.public_id ?? null, priority: f.priority,
        due_date: toNull(f.due_date), problem_description: toNull(f.problem_description),
        parent_work_order: preset.parent_work_order || null, checklist_template: toNull(f.checklist_template),
      })
      onDone(res.data)
    } catch (e) { setErr(apiError(e)) } finally { setBusy(false) }
  }
  const tpl = templates.data?.results || []
  return (
    <Modal title="New work order" onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Close</Button><Button variant="primary" loading={busy} onClick={submit}>Create</Button></>}>
      {err && !Object.keys(err.details || {}).length && <div className="alert alert-danger">{errorText(err)}</div>}
      <FormField label="Type" name="work_order_type" as="select" options={opts(['CORRECTIVE', 'PREVENTIVE'], { CORRECTIVE: 'Corrective', PREVENTIVE: 'Preventive' })}
        value={f.work_order_type} onChange={set('work_order_type')} error={fe(err, 'work_order_type')} />
      <EquipmentPicker value={equipment} onChange={setEquipment} required error={fe(err, 'equipment')} />
      <FormField label="Priority" name="priority" as="select" options={opts(PRIORITIES, PRIORITY_LABEL)}
        value={f.priority} onChange={set('priority')} error={fe(err, 'priority')} />
      <FormField label="Due date" name="due_date" type="date" required={f.work_order_type === 'PREVENTIVE'}
        value={f.due_date} onChange={set('due_date')} error={fe(err, 'due_date')} />
      <FormField label="Problem / scope" name="problem_description" as="textarea"
        value={f.problem_description} onChange={set('problem_description')} error={fe(err, 'problem_description')} />
      <FormField label="Checklist template" name="checklist_template" as="select"
        options={opts(tpl.map((t) => t.public_id), Object.fromEntries(tpl.map((t) => [t.public_id, t.name])), '— none —')}
        value={f.checklist_template} onChange={set('checklist_template')} error={fe(err, 'checklist_template')} />
    </Modal>
  )
}
