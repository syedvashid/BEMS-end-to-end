import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ApiAlert, Button, Check, FormField, Modal, api, fe, nn, toOpts, useAction, useForm,
} from './shared'
import ChargePreview from '../billing/ChargePreview.jsx'
import ChargeResult from '../billing/ChargeResult.jsx'

const CONDITIONS = [['GOOD', 'Good'], ['NEEDS_CLEANING', 'Needs cleaning'], ['DAMAGED', 'Damaged']]

export default function ReleaseDialog({ allocation, onClose, onDone }) {
  const { v, setV, bind } = useForm({ condition_on_release: 'GOOD', release_notes: '', back: true })
  const { busy, error, run } = useAction()
  const [result, setResult] = useState(null)
  const submit = () => run(async () => {
    const r = await api.post(`/allocations/${allocation.public_id}/release/`, {
      condition_on_release: v.condition_on_release, release_notes: nn(v.release_notes),
      return_to_previous_location: v.back,
    })
    const c = r.data.charges
    const showCharges = c && (c.warning || (c.created || []).length || (c.not_billable || []).length)
    if (r.data.suggest_breakdown || showCharges) setResult(r.data); else onDone(r.data)
  })
  if (result) {
    return (
      <Modal title="Equipment released" onClose={() => onDone(result)}
        footer={<Button variant="primary" onClick={() => onDone(result)}>Close</Button>}>
        {result.suggest_breakdown && <div className="alert alert-warning">The equipment was released as damaged. No work order was created.</div>}
        <ChargeResult charges={result.charges} />
        {result.suggest_breakdown && <Link to={`/work-orders?breakdown=${allocation.equipment.public_id}`} onClick={() => onDone(result)}>Report breakdown</Link>}
      </Modal>
    )
  }
  return (
    <Modal title={`Release ${allocation.equipment.asset_tag}`} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Close</Button>
        <Button variant="primary" loading={busy} onClick={submit}>Release</Button></>}>
      <ApiAlert error={error} />
      <FormField label="Condition" as="select" required
        options={CONDITIONS.map(([value, label]) => ({ value, label }))} {...bind('condition_on_release')} error={fe(error, 'condition_on_release')} />
      <FormField label="Notes" as="textarea" {...bind('release_notes')} error={fe(error, 'release_notes')} />
      {allocation.previous_location && (
        <Check label={`Return to previous location (${allocation.previous_location.name})`} checked={v.back}
         onChange={(e) => setV((p) => ({ ...p, back: e.target.checked }))} />
      )}
      <ChargePreview allocationId={allocation.public_id} />
    </Modal>
  )
}