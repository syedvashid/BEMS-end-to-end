import { useState } from 'react'
import { api } from '../../api/client'
import { Button, FormField, Modal } from '../ui'
import { EquipmentPicker, ErrorNote, fieldErr, nn, opts, useAction } from './shared'

// plan: existing plan to edit. equipment: { public_id, asset_tag, name } to lock the equipment (from a candidate).
export default function ReplacementPlanModal({ plan, equipment, onClose, onDone }) {
  const editing = !!plan
  const [v, setV] = useState({
    equipment: equipment?.public_id || '', planned_year: plan?.planned_year || new Date().getFullYear() + 1,
    estimated_cost: plan?.estimated_cost ?? '', priority: plan?.priority || 'MEDIUM', status: plan?.status || 'CANDIDATE',
    justification: plan?.justification || '', notes: plan?.notes || '',
  })
  const set = (k) => (e) => setV((s) => ({ ...s, [k]: e.target.value }))
  const act = useAction()
  const locked = editing || !!equipment

  const submit = () => act.run(async () => {
    const body = {
      planned_year: Number(v.planned_year), estimated_cost: v.estimated_cost === '' ? null : Number(v.estimated_cost),
      priority: v.priority, status: v.status, justification: nn(v.justification), notes: nn(v.notes),
    }
    if (editing) await api.patch(`/replacement-plans/${plan.public_id}/`, { ...body, row_version: plan.row_version })
    else await api.post('/replacement-plans/', { ...body, equipment: v.equipment })
    onDone()
  })
  return (
    <Modal title={editing ? 'Edit replacement plan' : 'Add to replacement plan'} onClose={onClose}
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={act.busy} onClick={submit}>Save</Button></>}>
      {locked
        ? <p><strong>{equipment?.asset_tag || plan?.equipment_asset_tag}</strong> · {equipment?.name || plan?.equipment_name}</p>
        : <EquipmentPicker value={v.equipment} required error={fieldErr(act.error, 'equipment')}
          onChange={(id) => setV((s) => ({ ...s, equipment: id }))} />}
      <FormField label="Planned year" name="planned_year" type="number" required value={v.planned_year}
        error={fieldErr(act.error, 'planned_year')} onChange={set('planned_year')} />
      <FormField label="Estimated cost (INR)" name="estimated_cost" type="number" step="0.01" min="0" value={v.estimated_cost}
        error={fieldErr(act.error, 'estimated_cost')} onChange={set('estimated_cost')} />
      <FormField label="Priority" name="priority" as="select" value={v.priority} options={opts(['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'])}
        onChange={set('priority')} />
      <FormField label="Status" name="status" as="select" value={v.status}
        options={opts(['CANDIDATE', 'APPROVED_FOR_BUDGET', 'DEFERRED', 'COMPLETED', 'CANCELLED'])} onChange={set('status')} />
      <FormField label="Justification" name="justification" as="textarea" value={v.justification} onChange={set('justification')} />
      <FormField label="Notes" name="notes" as="textarea" value={v.notes} onChange={set('notes')} />
      <ErrorNote error={act.error} />
    </Modal>
  )
}
