import { Button, FormError, FormField, Modal } from '../ui'
import { api, equipmentOption, fieldError, nn, useForm, useOptions, useSubmit, withBlank } from './shared'

const FREQ = [{ value: 'DAYS', label: 'Days' }, { value: 'MONTHS', label: 'Months' }]

export default function CalibrationScheduleModal({ schedule, equipmentId, canDelete, onClose, onSaved }) {
  const editing = !!schedule
  const equipment = useOptions('/equipment/', equipmentOption, { lifecycle_stage: 'COMMISSIONED' })
  const { busy, error, run } = useSubmit()
  const { v, bind } = useForm({
    equipment: schedule?.equipment ?? equipmentId ?? '', frequency_type: schedule?.frequency_type ?? 'DAYS',
    frequency_value: schedule?.frequency_value ?? '', lead_days: schedule?.lead_days ?? 30,
    last_calibrated_date: schedule?.last_calibrated_date ?? '', next_due_date: schedule?.next_due_date ?? '',
    on_fail_hold_equipment: schedule?.on_fail_hold_equipment ?? true,
    on_fail_open_work_order: schedule?.on_fail_open_work_order ?? true, notes: schedule?.notes ?? '',
  })
  const fe = (n) => fieldError(error, n)

  const save = () => run(async () => {
    const body = {
      frequency_type: v.frequency_type, frequency_value: Number(v.frequency_value), lead_days: Number(v.lead_days),
      last_calibrated_date: nn(v.last_calibrated_date), next_due_date: nn(v.next_due_date) ?? undefined,
      on_fail_hold_equipment: v.on_fail_hold_equipment, on_fail_open_work_order: v.on_fail_open_work_order,
      notes: nn(v.notes),
    }
    if (editing) await api.patch(`/calibration-schedules/${schedule.public_id}/`, { ...body, row_version: schedule.row_version })
    else await api.post('/calibration-schedules/', { ...body, equipment: v.equipment })
    onSaved()
  })

  const remove = () => run(async () => {
    await api.delete(`/calibration-schedules/${schedule.public_id}/`, { params: { row_version: schedule.row_version } })
    onSaved()
  })

  return (
    <Modal title={editing ? `Edit schedule — ${schedule.equipment_asset_tag}` : 'New calibration schedule'} onClose={onClose}
      footer={<>
        {editing && canDelete && <Button variant="danger" onClick={remove} loading={busy}>Delete</Button>}
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button onClick={save} loading={busy}>Save</Button>
      </>}>
      <FormError error={error} />
      {!editing && !equipmentId && <FormField label="Equipment" as="select" required options={withBlank(equipment)} error={fe('equipment')} {...bind('equipment')} />}
      <FormField label="Frequency type" as="select" options={FREQ} error={fe('frequency_type')} {...bind('frequency_type')} />
      <FormField label="Every" type="number" min="1" required error={fe('frequency_value')} {...bind('frequency_value')} />
      <FormField label="Lead days (due-soon window)" type="number" min="0" error={fe('lead_days')} {...bind('lead_days')} />
      <FormField label="Last calibrated" type="date" error={fe('last_calibrated_date')} {...bind('last_calibrated_date')} />
      <FormField label="Next due" type="date" hint={editing ? '' : 'Leave empty to calculate it'} error={fe('next_due_date')} {...bind('next_due_date')} />
      <label><input type="checkbox" {...(({ value, ...r }) => ({ ...r, checked: !!v.on_fail_hold_equipment }))(bind('on_fail_hold_equipment'))} /> On failure: place equipment out of service</label>
      <br />
      <label><input type="checkbox" {...(({ value, ...r }) => ({ ...r, checked: !!v.on_fail_open_work_order }))(bind('on_fail_open_work_order'))} /> On failure: open a corrective work order</label>
      <FormField label="Notes" as="textarea" error={fe('notes')} {...bind('notes')} />
    </Modal>
  )
}