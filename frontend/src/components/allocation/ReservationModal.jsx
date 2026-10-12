import { useState } from 'react'
import {
  ApiAlert, Button, EquipmentField, FormField, Items, Modal, api, fe, nn, toIso, useAction,
  useDepartmentOptions, useForm, withBlank,
} from './shared'

export default function ReservationModal({ equipment, start, end, onClose, onDone }) {
  const [eq, setEq] = useState(equipment || null)
  const { v, bind } = useForm({ department: '', start_at: start || '', end_at: end || '', purpose: '', procedure_reference: '' })
  const depts = useDepartmentOptions('/my-departments/')
  const { busy, error, run } = useAction()
  const [warnings, setWarnings] = useState(null)
  const submit = () => run(async () => {
    const r = await api.post('/reservations/', {
      equipment: eq?.public_id ?? null, department: nn(v.department), start_at: toIso(v.start_at), end_at: toIso(v.end_at),
      purpose: v.purpose, procedure_reference: nn(v.procedure_reference),
    })
    if (r.data.warnings?.length) setWarnings(r.data.warnings); else onDone(r.data)
  })
  if (warnings) {
    return (
      <Modal title="Reservation saved" onClose={() => onDone()} footer={<Button variant="primary" onClick={() => onDone()}>Close</Button>}>
        <p>The booking is confirmed, with these warnings:</p>
        <Items items={warnings} />
      </Modal>
    )
  }
  return (
    <Modal wide title="Reserve equipment" onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Close</Button>
        <Button variant="primary" loading={busy} onClick={submit}>Reserve</Button></>}>
      <ApiAlert error={error} />
      <EquipmentField value={eq} onChange={setEq} locked={!!equipment} error={fe(error, 'equipment')} />
      <FormField label="Department" as="select" required options={withBlank(depts)} {...bind('department')} error={fe(error, 'department')} />
      <div className="mt-row">
        <FormField label="Start" type="datetime-local" required {...bind('start_at')} error={fe(error, 'start_at')} />
        <FormField label="End" type="datetime-local" required {...bind('end_at')} error={fe(error, 'end_at')} />
      </div>
      <FormField label="Purpose" required {...bind('purpose')} error={fe(error, 'purpose')} />
      <FormField label="Procedure reference" {...bind('procedure_reference')} error={fe(error, 'procedure_reference')} />
    </Modal>
  )
}