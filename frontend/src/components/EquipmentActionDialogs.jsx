import { useState } from 'react'
import { api } from '../api/client'
import { fieldError, parseApiError } from '../utils/errors'
import { STATE_OPTIONS, codeName, friendly, opt, useMasterOptions } from '../utils/equipment'
import { Button, FormField, Modal } from './ui'

const nul = (s) => (typeof s === 'string' && s.trim() === '' ? null : s)

function useAction(eq, path, onDone) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const run = async (body) => {
    setBusy(true); setErr(null)
    try {
      await api.post(`/equipment/${eq.public_id}/${path}/`, { ...body, row_version: eq.row_version })
      onDone()
    } catch (e) { setErr(parseApiError(e)); setBusy(false) }
  }
  return { busy, err, run }
}

function Shell({ title, onClose, busy, onSubmit, submitLabel, err, children }) {
  return (
    <Modal title={title} onClose={onClose}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} onClick={onSubmit}>{submitLabel}</Button></>}>
      {err && err.code !== 'validation_error' && <div className="alert alert-danger">{friendly(err)}</div>}
      {children}
    </Modal>
  )
}

export function InstallDialog({ eq, onClose, onDone }) {
  const [f, setF] = useState({ installation_date: '', installation_engineer_name: '', installation_vendor: '', installation_notes: '' })
  const { busy, err, run } = useAction(eq, 'install', onDone)
  const vendors = useMasterOptions('/vendors/', (v) => v.name)
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }))
  const E = (k) => fieldError(err, k)
  return (
    <Shell title="Record installation" onClose={onClose} busy={busy} err={err} submitLabel="Save"
      onSubmit={() => run({ installation_date: f.installation_date, installation_engineer_name: nul(f.installation_engineer_name),
        installation_vendor: nul(f.installation_vendor), installation_notes: nul(f.installation_notes) })}>
      <FormField label="Installation date" name="installation_date" type="date" required value={f.installation_date}
        onChange={set('installation_date')} error={E('installation_date')} />
      <FormField label="Installation engineer" name="installation_engineer_name" value={f.installation_engineer_name}
        onChange={set('installation_engineer_name')} error={E('installation_engineer_name')} />
      <FormField label="Installation vendor" name="installation_vendor" as="select" options={vendors.options}
        value={f.installation_vendor} onChange={set('installation_vendor')} error={E('installation_vendor')} />
      <FormField label="Notes" name="installation_notes" as="textarea" value={f.installation_notes}
        onChange={set('installation_notes')} error={E('installation_notes')} />
    </Shell>
  )
}

export function CommissionDialog({ eq, onClose, onDone }) {
  const [f, setF] = useState({
    acceptance_test_result: 'PASS', acceptance_date: '', department: '', location: '',
    handover_received_by_name: '', training_conducted: false, training_notes: '', acceptance_test_notes: '',
  })
  const { busy, err, run } = useAction(eq, 'commission', onDone)
  const depts = useMasterOptions('/departments/', codeName)
  const locs = useMasterOptions('/locations/', codeName)
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }))
  const E = (k) => fieldError(err, k)
  return (
    <Shell title="Accept & commission" onClose={onClose} busy={busy} err={err} submitLabel="Commission"
      onSubmit={() => run({
        acceptance_test_result: f.acceptance_test_result, acceptance_date: f.acceptance_date,
        department: f.department, location: f.location, handover_received_by_name: f.handover_received_by_name,
        training_conducted: f.training_conducted, training_notes: nul(f.training_notes),
        acceptance_test_notes: nul(f.acceptance_test_notes),
      })}>
      <FormField label="Acceptance test result" name="acceptance_test_result" as="select" required
        options={[opt('PASS', 'Pass'), opt('CONDITIONAL', 'Conditional'), opt('FAIL', 'Fail')]}
        value={f.acceptance_test_result} onChange={set('acceptance_test_result')} error={E('acceptance_test_result')} />
      <FormField label="Acceptance date" name="acceptance_date" type="date" required value={f.acceptance_date}
        onChange={set('acceptance_date')} error={E('acceptance_date')} />
      <FormField label="Department" name="department" as="select" required options={depts.options}
        value={f.department} onChange={set('department')} error={E('department')} />
      <FormField label="Location" name="location" as="select" required options={locs.options}
        value={f.location} onChange={set('location')} error={E('location')} />
      <FormField label="Handover received by" name="handover_received_by_name" required value={f.handover_received_by_name}
        onChange={set('handover_received_by_name')} error={E('handover_received_by_name')} />
      <label>
        <input type="checkbox" checked={f.training_conducted}
          onChange={(e) => setF((x) => ({ ...x, training_conducted: e.target.checked }))} /> Training conducted
      </label>
      <FormField label="Training notes" name="training_notes" as="textarea" value={f.training_notes}
        onChange={set('training_notes')} error={E('training_notes')} />
      <FormField label="Acceptance test notes" name="acceptance_test_notes" as="textarea" value={f.acceptance_test_notes}
        onChange={set('acceptance_test_notes')} error={E('acceptance_test_notes')} />
    </Shell>
  )
}

export function RejectDialog({ eq, onClose, onDone }) {
  const [reason, setReason] = useState('')
  const { busy, err, run } = useAction(eq, 'reject', onDone)
  return (
    <Shell title="Reject equipment" onClose={onClose} busy={busy} err={err} submitLabel="Reject" onSubmit={() => run({ reason })}>
      <FormField label="Reason" name="reason" as="textarea" required value={reason}
        onChange={(e) => setReason(e.target.value)} error={fieldError(err, 'reason')} />
    </Shell>
  )
}

export function StateDialog({ eq, onClose, onDone }) {
  const [f, setF] = useState({ operational_state: eq.operational_state || 'IN_SERVICE', reason: '' })
  const { busy, err, run } = useAction(eq, 'set-operational-state', onDone)
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }))
  return (
    <Shell title="Change operational state" onClose={onClose} busy={busy} err={err} submitLabel="Save" onSubmit={() => run(f)}>
      <FormField label="New state" name="operational_state" as="select" required options={STATE_OPTIONS}
        value={f.operational_state} onChange={set('operational_state')} error={fieldError(err, 'operational_state')} />
      <FormField label="Reason" name="reason" as="textarea" required value={f.reason}
        onChange={set('reason')} error={fieldError(err, 'reason')} />
    </Shell>
  )
}

export function MoveDialog({ eq, onClose, onDone }) {
  const [f, setF] = useState({ location: '', department: '', reason: '' })
  const { busy, err, run } = useAction(eq, 'move', onDone)
  const depts = useMasterOptions('/departments/', codeName)
  const locs = useMasterOptions('/locations/', codeName)
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }))
  const E = (k) => fieldError(err, k)
  return (
    <Shell title="Move equipment" onClose={onClose} busy={busy} err={err} submitLabel="Move"
      onSubmit={() => run({ location: f.location, department: nul(f.department), reason: f.reason })}>
      <FormField label="New location" name="location" as="select" required options={locs.options}
        value={f.location} onChange={set('location')} error={E('location')} />
      <FormField label="New department" name="department" as="select" options={depts.options}
        value={f.department} onChange={set('department')} error={E('department')} hint="Leave blank to keep the current department" />
      <FormField label="Reason" name="reason" as="textarea" required value={f.reason}
        onChange={set('reason')} error={E('reason')} />
    </Shell>
  )
}
