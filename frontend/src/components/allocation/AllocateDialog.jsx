import { useState } from 'react'
import { useFacility } from '../../context/FacilityContext'
import {
  ApiAlert, Button, Check, EquipmentField, FormField, Items, Modal, SOURCES, api, fe, nn, toIso, toOpts,
  useAction, useDepartmentOptions, useFetch, useForm, useLocationOptions, withBlank,
} from './shared'

export default function AllocateDialog({ equipment, onClose, onDone }) {
  const { can } = useFacility()
  const [eq, setEq] = useState(equipment || null)
  const { v, setV, bind } = useForm({
    department: '', location: '', source_module: 'MANUAL', patient_reference: '', encounter_reference: '',
    practitioner_name: '', purpose: '', expected_release_at: '', override: false, override_reason: '',
  })
  const depts = useDepartmentOptions()
  const locs = useLocationOptions()
  const { busy, error, run } = useAction()
  const av = useFetch(`/equipment/${eq?.public_id}/availability/`, { to: toIso(v.expected_release_at) || undefined }, !!eq)
  const blocking = av.data?.blocking || []
  const hard = blocking.filter((b) => !b.code.startsWith('CALIBRATION_'))
  const gate = blocking.filter((b) => b.code.startsWith('CALIBRATION_'))
  const useOverride = gate.length > 0 && v.override
  const blocked = !eq || hard.length > 0 || (gate.length > 0 && !(v.override && v.override_reason.trim()))

  const submit = () => run(async () => {
    const r = await api.post('/allocations/', {
      equipment: eq.public_id, department: nn(v.department), location: nn(v.location),
      source_module: v.source_module, patient_reference: nn(v.patient_reference),
      encounter_reference: nn(v.encounter_reference), practitioner_name: nn(v.practitioner_name),
      purpose: nn(v.purpose), expected_release_at: toIso(v.expected_release_at),
      override: useOverride, override_reason: useOverride ? nn(v.override_reason) : null,
    })
    onDone(r.data)
  })

  return (
    <Modal wide title="Allocate equipment" onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Close</Button>
        <Button variant="primary" loading={busy} disabled={blocked} onClick={submit}>Allocate</Button></>}>
      <ApiAlert error={error} />
      <EquipmentField value={eq} onChange={setEq} locked={!!equipment} error={fe(error, 'equipment')} />
      {eq && !av.loading && <Items items={hard} tone="danger" />}
      {eq && gate.length > 0 && (
        <div className="alert alert-warning">
          <strong>Calibration gate</strong>
          <Items items={gate} tone="danger" />
          {can('allocation.override') ? (
            <>
              <Check label="Override the calibration gate" checked={v.override}
                onChange={(e) => setV((p) => ({ ...p, override: e.target.checked }))} />
              {v.override && <FormField label="Override reason" name="override_reason" as="textarea" required
                {...bind('override_reason')} error={fe(error, 'override_reason')} />}
            </>
          ) : <p className="muted">Only a user with the override permission (Biomedical Admin) can allocate this equipment.</p>}
        </div>
      )}
      {eq && !av.loading && <Items items={av.data?.warnings} />}
      <div className="mt-row">
        <FormField label="Department" as="select" options={withBlank(depts, '— none —')} {...bind('department')} error={fe(error, 'department')} />
        <FormField label="Location (moves the equipment)" as="select" options={withBlank(locs, '— none —')} {...bind('location')} error={fe(error, 'location')} />
        <FormField label="Source" as="select" options={toOpts(SOURCES)} {...bind('source_module')} />
      </div>
      <div className="mt-row">
        <FormField label="Patient reference" hint="UHID / IP number" {...bind('patient_reference')} error={fe(error, 'patient_reference')} />
        <FormField label="Encounter reference" {...bind('encounter_reference')} error={fe(error, 'encounter_reference')} />
        <FormField label="Practitioner" {...bind('practitioner_name')} error={fe(error, 'practitioner_name')} />
      </div>
      <div className="mt-row">
        <FormField label="Expected release" type="datetime-local" {...bind('expected_release_at')} error={fe(error, 'expected_release_at')} />
        <FormField label="Purpose" {...bind('purpose')} error={fe(error, 'purpose')} />
      </div>
    </Modal>
  )
}