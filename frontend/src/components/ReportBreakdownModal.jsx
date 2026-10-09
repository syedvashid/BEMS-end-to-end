import { useState } from 'react'
import { api } from '../api/client'
import { Button, FormField, Modal } from './ui'
import EquipmentPicker from './EquipmentPicker'
import useFetch from '../hooks/useFetch'
import { PRIORITIES, PRIORITY_LABEL, apiError, errorText, fe, fromLocalInput, opts, toNull } from '../utils/maintenance'

// preset: { public_id, label } when launched from an equipment page.
export default function ReportBreakdownModal({ preset, onClose, onDone }) {
  const departments = useFetch('/departments/', { page_size: 100 }, true)
  const [equipment, setEquipment] = useState(preset || null)
  const [f, setF] = useState({ problem_description: '', priority: 'MEDIUM', reported_by_name: '', reported_by_department: '', reported_at: '', equipment_unusable: false })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }))

  const submit = async () => {
    setBusy(true); setErr(null)
    try {
      const res = await api.post('/work-orders/report-breakdown/', {
        equipment: equipment?.public_id ?? null,
        problem_description: f.problem_description,
        priority: f.priority,
        reported_by_name: toNull(f.reported_by_name),
        reported_by_department: toNull(f.reported_by_department),
        reported_at: fromLocalInput(f.reported_at),
        equipment_unusable: f.equipment_unusable,
      })
      onDone(res.data)
    } catch (e) { setErr(apiError(e)) } finally { setBusy(false) }
  }
  const deptOptions = opts((departments.data?.results || []).map((d) => d.public_id), Object.fromEntries((departments.data?.results || []).map((d) => [d.public_id, d.name])), '— none —')

  return (
    <Modal title="Report breakdown" onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Close</Button><Button variant="primary" loading={busy} onClick={submit}>Report</Button></>}>
      {err && !err.details?.problem_description && !err.details?.equipment && <div className="alert alert-danger">{errorText(err)}</div>}
      {preset
        ? <p><strong>{preset.label}</strong></p>
        : <EquipmentPicker value={equipment} onChange={setEquipment} required error={fe(err, 'equipment')} />}
      <FormField label="What is wrong?" name="problem_description" as="textarea" required
        value={f.problem_description} onChange={set('problem_description')} error={fe(err, 'problem_description')} />
      <FormField label="Priority" name="priority" as="select" options={opts(PRIORITIES, PRIORITY_LABEL)}
        value={f.priority} onChange={set('priority')} error={fe(err, 'priority')} />
      <FormField label="Reported by (name)" name="reported_by_name" value={f.reported_by_name}
        onChange={set('reported_by_name')} error={fe(err, 'reported_by_name')} />
      <FormField label="Reporting department" name="reported_by_department" as="select" options={deptOptions}
        value={f.reported_by_department} onChange={set('reported_by_department')} error={fe(err, 'reported_by_department')} />
      <FormField label="Reported at" name="reported_at" type="datetime-local" hint="Leave empty for now"
        value={f.reported_at} onChange={set('reported_at')} error={fe(err, 'reported_at')} />
      <label className="mt-row">
        <input type="checkbox" checked={f.equipment_unusable}
          onChange={(e) => setF((s) => ({ ...s, equipment_unusable: e.target.checked }))} />
        <span>Equipment cannot be used (puts it out of service until the work order is completed)</span>
      </label>
    </Modal>
  )
}
