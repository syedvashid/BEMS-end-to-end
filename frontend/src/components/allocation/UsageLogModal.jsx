import { useState } from 'react'
import {
  ApiAlert, Button, EquipmentField, FormField, Modal, api, eqValue, fe, nn, toInput, toIso, useAction,
  useDepartmentOptions, useForm, withBlank,
} from './shared'

export default function UsageLogModal({ log, equipment, onClose, onDone }) {
  const [eq, setEq] = useState(log ? eqValue(log.equipment) : equipment || null)
  const { v, bind } = useForm({
    started_at: log ? toInput(log.started_at) : '', ended_at: log ? toInput(log.ended_at) : '',
    operator_name: log?.operator_name || '', patient_reference: log?.patient_reference || '',
    encounter_reference: log?.encounter_reference || '', procedure_text: log?.procedure_text || '',
    department: log?.department?.public_id || '', notes: log?.notes || '',
  })
  const depts = useDepartmentOptions()
  const { busy, error, run } = useAction()
  const submit = () => run(async () => {
    const body = {
      started_at: toIso(v.started_at), ended_at: toIso(v.ended_at), operator_name: nn(v.operator_name),
      patient_reference: nn(v.patient_reference), encounter_reference: nn(v.encounter_reference),
      procedure_text: nn(v.procedure_text), department: nn(v.department), notes: nn(v.notes),
    }
    if (log) await api.patch(`/usage-logs/${log.public_id}/`, { ...body, row_version: log.row_version })
    else await api.post('/usage-logs/', { ...body, equipment: eq?.public_id ?? null })
    onDone()
  })
  return (
    <Modal wide title={log ? 'Edit usage log' : 'Add usage log'} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Close</Button>
        <Button variant="primary" loading={busy} onClick={submit}>Save</Button></>}>
      <ApiAlert error={error} />
      <EquipmentField value={eq} onChange={setEq} locked={!!log || !!equipment} error={fe(error, 'equipment')} />
      <div className="mt-row">
        <FormField label="Started" type="datetime-local" required {...bind('started_at')} error={fe(error, 'started_at')} />
        <FormField label="Ended" type="datetime-local" required {...bind('ended_at')} error={fe(error, 'ended_at')} />
        <FormField label="Department" as="select" options={withBlank(depts, '— none —')} {...bind('department')} error={fe(error, 'department')} />
      </div>
      <div className="mt-row">
        <FormField label="Operator" {...bind('operator_name')} error={fe(error, 'operator_name')} />
        <FormField label="Patient reference" {...bind('patient_reference')} error={fe(error, 'patient_reference')} />
        <FormField label="Encounter reference" {...bind('encounter_reference')} error={fe(error, 'encounter_reference')} />
      </div>
      <FormField label="Procedure" {...bind('procedure_text')} error={fe(error, 'procedure_text')} />
      <FormField label="Notes" as="textarea" {...bind('notes')} error={fe(error, 'notes')} />
    </Modal>
  )
}