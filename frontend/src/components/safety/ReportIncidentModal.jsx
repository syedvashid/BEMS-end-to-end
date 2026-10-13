import { useState } from 'react'
import EquipmentPicker from '../EquipmentPicker'
import { FormField, Modal, Button } from '../ui'
import {
  Check, ErrorBox, INCIDENT_TYPES, LocationSelect, SEVERITIES, api, deptOption, fieldError, nn, nowLocal, opt, useAction,
  useForm, useOptions, withBlank,
} from './shared'

/** Report an incident. `equipment` ({public_id,label}) pre-fills and locks the picker. */
export default function ReportIncidentModal({ equipment, onClose, onDone }) {
  const { v, setV, bind } = useForm({
    incident_type: 'MALFUNCTION', severity: 'MINOR', occurred_at: nowLocal(), reported_by_name: '', department: '',
    location: '', description: '', immediate_action: '', patient_reference: '', encounter_reference: '',
    patient_affected: false, staff_affected: false, reportable_to_regulator: false, quarantine: false,
  })
  const [eq, setEq] = useState(equipment || null)
  const [touched, setTouched] = useState(false)   // the person changed the quarantine box themselves
  const depts = useOptions('/departments/', deptOption)
  const act = useAction()
  const chk = (name) => ({ checked: !!v[name], onChange: (e) => setV((p) => ({ ...p, [name]: e.target.checked })) })

  const onSeverity = (e) => {
    const severity = e.target.value
    setV((p) => ({ ...p, severity, quarantine: touched ? p.quarantine : ['SEVERE', 'DEATH'].includes(severity) }))
  }
  const submit = async () => {
    const r = await act.run(() => api.post('/incidents/', {
      equipment: eq?.public_id ?? null, incident_type: v.incident_type, severity: v.severity,
      occurred_at: v.occurred_at ? new Date(v.occurred_at).toISOString() : null,
      reported_by_name: nn(v.reported_by_name.trim()), department: nn(v.department), location: nn(v.location),
      description: v.description.trim(), immediate_action: nn(v.immediate_action.trim()),
      patient_reference: nn(v.patient_reference.trim()), encounter_reference: nn(v.encounter_reference.trim()),
      patient_affected: v.patient_affected, staff_affected: v.staff_affected,
      reportable_to_regulator: v.reportable_to_regulator, quarantine: v.quarantine,
    }))
    if (r.ok) onDone(r.data.data)
  }

  return (
    <Modal title="Report incident" wide onClose={onClose}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={act.busy} onClick={submit}>Report</Button></>}>
      <ErrorBox error={act.error} />
      {equipment
        ? <p><strong>Equipment:</strong> {equipment.label}</p>
        : <EquipmentPicker label="Equipment" value={eq} onChange={setEq} error={fieldError(act.error, 'equipment')} />}
      <FormField label="Type" as="select" required options={opt(INCIDENT_TYPES)} {...bind('incident_type')} error={fieldError(act.error, 'incident_type')} />
      <FormField label="Severity" as="select" required options={opt(SEVERITIES)} {...bind('severity')} onChange={onSeverity} error={fieldError(act.error, 'severity')} />
      <FormField label="Occurred at" type="datetime-local" required {...bind('occurred_at')} error={fieldError(act.error, 'occurred_at')} />
      <FormField label="Reported by (name)" hint="Defaults to you" {...bind('reported_by_name')} error={fieldError(act.error, 'reported_by_name')} />
      <FormField label="Department" as="select" options={withBlank(depts, '— none —')} {...bind('department')} error={fieldError(act.error, 'department')} />
      <LocationSelect label="Location" value={v.location} onChange={(x) => setV((p) => ({ ...p, location: x }))} error={fieldError(act.error, 'location')} />
      <FormField label="What happened" as="textarea" required {...bind('description')} error={fieldError(act.error, 'description')} />
      <FormField label="Immediate action taken" as="textarea" {...bind('immediate_action')} error={fieldError(act.error, 'immediate_action')} />
      <FormField label="Patient reference (UHID, optional)" hint="Letters, digits, / _ - only. No patient names." {...bind('patient_reference')} error={fieldError(act.error, 'patient_reference')} />
      <FormField label="Encounter reference (IP number, optional)" {...bind('encounter_reference')} error={fieldError(act.error, 'encounter_reference')} />
      <Check label="Patient affected" {...chk('patient_affected')} />
      <Check label="Staff affected" {...chk('staff_affected')} />
      <Check label="Reportable to the regulator (MvPI / CDSCO)" {...chk('reportable_to_regulator')}
        hint="The system only records the report; it does not submit anything." />
      <Check label="Quarantine equipment (take it out of service)" checked={v.quarantine}
        onChange={(e) => { setTouched(true); setV((p) => ({ ...p, quarantine: e.target.checked })) }}
        hint="Ticked by default for Severe and Death. Only commissioned equipment can be quarantined." />
    </Modal>
  )
}
