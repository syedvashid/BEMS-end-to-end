import { Button, FormField, Modal } from '../ui'
import {
  ErrorBox, LocationSelect, SCOPE_TYPES, api, deptOption, fieldError, nn, opt, useAction, useForm, useOptions, withBlank,
} from './shared'

/** Create (verification undefined) or edit a PLANNED verification (verification = detail payload). */
export default function VerificationFormModal({ verification, onClose, onDone }) {
  const edit = !!verification
  const depts = useOptions('/departments/', deptOption)
  const { v, setV, bind } = useForm({
    title: verification?.title || '', scope_type: verification?.scope_type || 'FACILITY',
    department: verification?.department?.public_id || '', location: verification?.location?.public_id || '',
    planned_date: verification?.planned_date || '', conducted_by_name: verification?.conducted_by_name || '',
    notes: verification?.notes || '',
  })
  const act = useAction()
  const submit = async () => {
    const body = {
      title: v.title.trim(), scope_type: v.scope_type,
      department: v.scope_type === 'DEPARTMENT' ? nn(v.department) : null,
      location: v.scope_type === 'LOCATION' ? nn(v.location) : null,
      planned_date: nn(v.planned_date), conducted_by_name: nn(v.conducted_by_name.trim()), notes: nn(v.notes.trim()),
    }
    const r = await act.run(() => (edit
      ? api.patch(`/verifications/${verification.public_id}/`, { ...body, row_version: verification.row_version })
      : api.post('/verifications/', body)))
    if (r.ok) onDone(r.data.data)
  }
  return (
    <Modal title={edit ? `Edit ${verification.verification_number}` : 'New physical verification'} onClose={onClose}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={act.busy} onClick={submit}>Save</Button></>}>
      <ErrorBox error={act.error} />
      <FormField label="Title" required {...bind('title')} error={fieldError(act.error, 'title')} />
      <FormField label="Scope" as="select" required options={opt(SCOPE_TYPES)} {...bind('scope_type')} error={fieldError(act.error, 'scope_type')} />
      {v.scope_type === 'DEPARTMENT' && (
        <FormField label="Department" as="select" required options={withBlank(depts, 'Select department…')} {...bind('department')} error={fieldError(act.error, 'department')} />
      )}
      {v.scope_type === 'LOCATION' && (
        <LocationSelect label="Location" required value={v.location} onChange={(x) => setV((p) => ({ ...p, location: x }))}
          error={fieldError(act.error, 'location')} hint="Includes everything inside this location." />
      )}
      <FormField label="Planned date" type="date" {...bind('planned_date')} error={fieldError(act.error, 'planned_date')} />
      <FormField label="Conducted by" {...bind('conducted_by_name')} error={fieldError(act.error, 'conducted_by_name')} />
      <FormField label="Notes" as="textarea" {...bind('notes')} error={fieldError(act.error, 'notes')} />
    </Modal>
  )
}
