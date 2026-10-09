import { useState } from 'react'
import { api } from '../api/client'
import { Button, FormField, Modal } from './ui'
import { apiError, errorText, fe } from '../utils/maintenance'

// Replaces the Phase 4 StateDialog. Only In service / Out of service can be requested manually.
export default function OperationalStateDialog({ eq, onClose, onDone }) {
  const [state, setState] = useState(eq.operational_state === 'OUT_OF_SERVICE' ? 'IN_SERVICE' : 'OUT_OF_SERVICE')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const submit = async () => {
    setBusy(true); setErr(null)
    try {
      await api.post(`/equipment/${eq.public_id}/set-operational-state/`, { operational_state: state, reason, row_version: eq.row_version })
      onDone()
    } catch (e) { setErr(apiError(e)) } finally { setBusy(false) }
  }
  const blocking = err?.details?.blocking_holds || []
  return (
    <Modal title="Change operational state" onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Close</Button><Button variant="primary" loading={busy} onClick={submit}>Save</Button></>}>
      <p className="muted">
        Current state: <strong>{eq.operational_state}</strong>. “Under maintenance” is set automatically while a work order is in
        progress and cannot be chosen here. Out of service places a manual hold; In service releases manual holds only.
      </p>
      {err && <div className="alert alert-danger">{errorText(err)}</div>}
      {blocking.length > 0 && (
        <div className="alert alert-warning">
          Blocking holds (released when their work orders are completed or cancelled):
          <ul className="mt-list">
            {blocking.map((h) => (
              <li key={h.public_id}>{h.hold_type.replace('_', ' ').toLowerCase()} — {h.reason}{h.work_order ? ` (${h.work_order})` : ''}</li>
            ))}
          </ul>
        </div>
      )}
      <FormField label="New state" name="operational_state" as="select"
        options={[{ value: 'IN_SERVICE', label: 'In service' }, { value: 'OUT_OF_SERVICE', label: 'Out of service' }]}
        value={state} onChange={(e) => setState(e.target.value)} error={fe(err, 'operational_state')} />
      <FormField label="Reason" name="reason" as="textarea" required value={reason}
        onChange={(e) => setReason(e.target.value)} error={fe(err, 'reason')} />
    </Modal>
  )
}
