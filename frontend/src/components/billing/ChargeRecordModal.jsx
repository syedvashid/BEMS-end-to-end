import { useState } from 'react'
import { Button, Modal } from '../ui'
import { BASIS_LABEL, ErrBox, Field, RULE_LABEL, StatusPill, api, fmtD, fmtDT, inr, parseApiError, qty, useFetch } from './shared.jsx'

const line = (label, value) => (value === null || value === undefined || value === '' ? null : (
  <div style={{ display: 'flex', gap: 8, marginBottom: 4 }}>
    <span style={{ minWidth: 170, opacity: 0.7 }}>{label}</span><span>{value}</span>
  </div>
))

// Detail of one charge record with the calculation steps and the actions allowed by status and permission.
export default function ChargeRecordModal({ id, canApprove, onClose, onChanged }) {
  const { data: r, loading, reload } = useFetch(`/charge-records/${id}/`)
  const [ask, setAsk] = useState(null)        // 'cancel' | 'reverse'
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function act(action, body = {}) {
    setBusy(true)
    setError(null)
    try {
      await api.post(`/charge-records/${id}/${action}/`, body)
      setAsk(null)
      setReason('')
      reload()
      onChanged()
    } catch (err) {
      console.error(`[billing] ${action} failed`, err)
      setError(parseApiError(err))
    } finally {
      setBusy(false)
    }
  }

  const isCharge = r?.record_type === 'CHARGE'
  const footer = (
    <>
      <Button onClick={onClose}>Close</Button>
      {canApprove && r?.status === 'PENDING_REVIEW' && (<>
        <Button variant="danger" onClick={() => setAsk('cancel')}>Cancel record</Button>
        <Button variant="primary" loading={busy} onClick={() => act('approve')}>Approve</Button></>)}
      {canApprove && isCharge && r?.status === 'APPROVED' && <Button variant="danger" onClick={() => setAsk('reverse')}>Reverse</Button>}
      {canApprove && isCharge && r?.status === 'REVERSED' && <Button loading={busy} onClick={() => act('recalculate')}>Recalculate</Button>}
    </>
  )

  return (
    <Modal title={r ? `Charge record ${r.record_number}` : 'Charge record'} onClose={onClose} wide footer={footer}>
      <ErrBox error={error} />
      {loading && !r && <p>Loading...</p>}
      {r && (
        <>
          <p><StatusPill status={r.status} /> {r.record_type === 'REVERSAL' ? ' Reversal' : ''}</p>
          {line('Equipment', r.equipment && `${r.equipment.asset_tag} - ${r.equipment.name}`)}
          {line('Charge item', r.charge_item && `${r.charge_item.item_code} - ${r.charge_item.name}`)}
          {line('Rule', `${RULE_LABEL[r.billing_rule]} (from ${BASIS_LABEL[r.basis]?.toLowerCase()})`)}
          {line('Quantity', `${qty(r.quantity)} ${r.unit_label}`)}
          {line('Unit rate', inr(r.unit_rate))}
          {line('Amount', inr(r.amount))}
          {line('Charge date', fmtD(r.charge_date))}
          {line('Period', r.period_start && `${fmtDT(r.period_start)} to ${fmtDT(r.period_end)}`)}
          {line('Patient reference', r.patient_reference)}
          {line('Encounter reference', r.encounter_reference)}
          {line('Department', r.department?.name)}
          {line('Approved', r.approved_at && `${fmtDT(r.approved_at)} by ${r.approved_by}`)}
          {line('Cancelled', r.cancelled_at && `${fmtDT(r.cancelled_at)} by ${r.cancelled_by}: ${r.cancel_reason}`)}
          {line('Reversal reason', r.reversal_reason)}
          {line('Reverses', r.reverses_record?.record_number)}
          {line('Replaces', r.corrects_record?.record_number)}
          {line('Exported', r.exported_at && `${fmtDT(r.exported_at)} by ${r.exported_by} (${r.export_reference})`)}
          <h4>How this was calculated</h4>
          <ol>{(r.calculation?.steps || []).map((s, i) => <li key={i}>{s}</li>)}</ol>
          {ask && (
            <div>
              <Field label={ask === 'cancel' ? 'Reason for cancelling' : 'Reason for reversing'} name="reason" as="textarea"
                required value={reason} onChange={(e) => setReason(e.target.value)} />
              <Button onClick={() => { setAsk(null); setReason('') }}>Back</Button>
              <Button variant="danger" loading={busy} disabled={!reason.trim()} onClick={() => act(ask, { reason })}>
                {ask === 'cancel' ? 'Confirm cancel' : 'Confirm reverse'}
              </Button>
            </div>
          )}
        </>
      )}
    </Modal>
  )
}
