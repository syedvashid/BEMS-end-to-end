import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import DocumentsPanel from '../components/DocumentsPanel'
import DisposalFormModal from '../components/finance/DisposalFormModal'
import {
  BlockerList, DisposalChip, ErrorNote, RequestChip, fieldErr, fmtDay, fmtMoney, fmtStamp, lbl, nn, useAction,
} from '../components/finance/shared'
import { Button, FormField, Modal, useToast } from '../components/ui'
import { useFacility } from '../context/FacilityContext'
import useFetch from '../hooks/useFetch'

const KV = ({ label, children }) => <div className="eq-kv"><span className="muted">{label}</span><span>{children}</span></div>

// One small dialog for Approve / Reject / Cancel / Revoke (and cancelling a disposal).
function DecisionDialog({ kind, url, rowVersion, onClose, onDone }) {
  const cfg = {
    approve: { title: 'Approve condemnation', primary: 'Approve' },
    reject: { title: 'Reject condemnation', primary: 'Reject', danger: true },
    cancel: { title: 'Cancel request', primary: 'Cancel request', danger: true },
    revoke: { title: 'Revoke condemnation', primary: 'Revoke', danger: true },
    cancel_disposal: { title: 'Cancel disposal', primary: 'Cancel disposal', danger: true },
  }[kind]
  const [v, setV] = useState({ committee_reference: '', committee_decision_date: '', text: '' })
  const act = useAction()
  const set = (k) => (e) => setV((s) => ({ ...s, [k]: e.target.value }))
  const submit = () => act.run(async () => {
    let body = { row_version: rowVersion }
    if (kind === 'approve') body = { ...body, committee_reference: nn(v.committee_reference), committee_decision_date: nn(v.committee_decision_date), note: nn(v.text) }
    if (kind === 'reject') body = { ...body, note: v.text }
    if (['cancel', 'revoke', 'cancel_disposal'].includes(kind)) body = { ...body, reason: v.text }
    await api.post(url, body)
    onDone()
  })
  return (
    <Modal title={cfg.title} onClose={onClose}
      footer={<><Button variant="ghost" onClick={onClose}>Close</Button><Button variant={cfg.danger ? 'danger' : 'primary'} loading={act.busy} onClick={submit}>{cfg.primary}</Button></>}>
      {kind === 'approve' && (
        <>
          <p className="muted">Approving condemns the equipment: its open preventive work orders are cancelled and its maintenance plans and calibration schedule are switched off.</p>
          <FormField label="Committee reference" name="committee_reference" value={v.committee_reference}
            hint="Required when the book value is above the configured limit." error={fieldErr(act.error, 'committee_reference')} onChange={set('committee_reference')} />
          <FormField label="Committee decision date" name="committee_decision_date" type="date" value={v.committee_decision_date}
            error={fieldErr(act.error, 'committee_decision_date')} onChange={set('committee_decision_date')} />
        </>
      )}
      {kind === 'revoke' && <p className="muted">The equipment returns to commissioned. Maintenance plans and calibration schedules are not restored.</p>}
      <FormField label={kind === 'approve' ? 'Note (optional)' : kind === 'reject' ? 'Reason for rejection' : 'Reason'} name="text"
        as="textarea" required={kind !== 'approve'} value={v.text}
        error={fieldErr(act.error, 'note') || fieldErr(act.error, 'reason')} onChange={set('text')} />
      <ErrorNote error={act.error} />
    </Modal>
  )
}

function DisposalSection({ r, reload }) {
  const { can } = useFacility()
  const toast = useToast()
  const [dialog, setDialog] = useState(null)
  const summary = r.disposal
  const d = useFetch(summary ? `/disposals/${summary.public_id}/` : '/disposals/', undefined, !!summary && can('disposal.view'))
  const complete = useAction()
  const x = d.data
  const done = (msg) => () => { setDialog(null); toast.success(msg); d.reload(); reload() }
  const manage = can('disposal.manage')

  const finish = () => {
    if (!window.confirm('Complete this disposal? The equipment will become Disposed and this cannot be undone.')) return
    complete.run(async () => { await api.post(`/disposals/${x.public_id}/complete/`, { row_version: x.row_version }); done('Disposal completed.')() })
  }
  const expected = x && x.status === 'IN_PROGRESS' && r.current_book_value != null
    ? Number(x.proceeds_amount) - Number(r.current_book_value) : null

  return (
    <div className="fin-section">
      <h3>Disposal</h3>
      {!summary && r.status === 'APPROVED' && manage && <Button variant="primary" onClick={() => setDialog('create')}>Create disposal</Button>}
      {!summary && r.status !== 'APPROVED' && <p className="muted">A disposal can be created once the condemnation is approved.</p>}
      {x && (
        <>
          <p>{x.disposal_number} <DisposalChip value={x.status} /></p>
          <div className="eq-grid">
            <KV label="Method">{lbl(x.disposal_method)}</KV>
            <KV label="Date">{fmtDay(x.disposal_date)}</KV>
            <KV label="Recipient">{x.recipient_name || x.recipient_vendor_name || '—'}</KV>
            <KV label="Proceeds">{fmtMoney(x.proceeds_amount)}</KV>
            <KV label="Decontamination">{x.decontamination_done ? 'Done' : 'Not done'}</KV>
            <KV label="Data wipe">{x.data_wipe_required ? (x.data_wipe_done ? 'Done' : 'Required, not done') : 'Not required'}</KV>
            <KV label="E-waste recycler">{x.recycler_name || '—'}</KV>
            <KV label="E-waste certificate">{x.ewaste_certificate_number || '—'}</KV>
            <KV label="Book value at disposal">{x.status === 'COMPLETED' ? fmtMoney(x.book_value_at_disposal) : `${fmtMoney(r.current_book_value)} (current)`}</KV>
            <KV label="Gain / loss">
              {x.status === 'COMPLETED' ? fmtMoney(x.gain_loss) : expected == null ? '—' : `${fmtMoney(expected)} (expected)`}
            </KV>
            {x.cancel_reason && <KV label="Cancelled because">{x.cancel_reason}</KV>}
          </div>
          {x.status === 'IN_PROGRESS' && manage && (
            <div className="row">
              <Button onClick={() => setDialog('edit')}>Edit</Button>
              <Button variant="primary" loading={complete.busy} onClick={finish}>Complete disposal</Button>
              <Button variant="danger" onClick={() => setDialog('cancel_disposal')}>Cancel disposal</Button>
            </div>
          )}
          <ErrorNote error={complete.error} />
          <DocumentsPanel entityType="disposal" entityId={x.public_id} viewPermission="disposal.view" attachPermission="disposal.manage" />
        </>
      )}
      {dialog === 'create' && <DisposalFormModal requestId={r.public_id} onClose={() => setDialog(null)} onDone={done('Disposal created.')} />}
      {dialog === 'edit' && <DisposalFormModal disposal={x} onClose={() => setDialog(null)} onDone={done('Disposal saved.')} />}
      {dialog === 'cancel_disposal' && (
        <DecisionDialog kind="cancel_disposal" url={`/disposals/${x.public_id}/cancel/`} rowVersion={x.row_version}
          onClose={() => setDialog(null)} onDone={done('Disposal cancelled.')} />
      )}
    </div>
  )
}

export default function CondemnationDetailPage() {
  const { publicId } = useParams()
  const { can } = useFacility()
  const toast = useToast()
  const res = useFetch(`/condemnation-requests/${publicId}/`)
  const [dialog, setDialog] = useState(null)

  if (res.loading && !res.data) return <p className="muted">Loading…</p>
  if (res.error || !res.data) return <div className="alert alert-danger">Request not found. <Link to="/condemnation">Back</Link></div>
  const r = res.data
  const close = () => setDialog(null)
  const done = (msg) => () => { close(); toast.success(msg); res.reload() }
  const liveDisposal = r.disposal && ['IN_PROGRESS', 'COMPLETED'].includes(r.disposal.status)

  return (
    <section>
      <div className="page-head">
        <h2>{r.request_number}</h2> <RequestChip value={r.status} />{r.revoked && <span className="muted"> (revoked)</span>}
        <span className="spacer" />
        {r.status === 'REQUESTED' && r.can_approve && <Button variant="primary" onClick={() => setDialog('approve')}>Approve</Button>}
        {r.status === 'REQUESTED' && can('condemnation.approve') && <Button variant="danger" onClick={() => setDialog('reject')}>Reject</Button>}
        {r.status === 'REQUESTED' && <Button onClick={() => setDialog('cancel')}>Cancel request</Button>}
        {r.status === 'APPROVED' && can('condemnation.approve') && !liveDisposal && <Button variant="danger" onClick={() => setDialog('revoke')}>Revoke</Button>}
        <Link to="/condemnation">Back to list</Link>
      </div>

      {r.status === 'REQUESTED' && !r.can_approve && can('condemnation.approve') && (
        <div className="alert alert-warning">You made this request, so someone else must approve it.</div>
      )}
      {r.blockers?.length > 0 && (
        <div className="alert alert-warning">
          Approval is blocked until these are resolved:
          <BlockerList blockers={r.blockers} />
        </div>
      )}

      <div className="eq-grid">
        <KV label="Equipment"><Link to={`/equipment/${r.equipment.public_id}`}>{r.equipment.asset_tag} · {r.equipment.name}</Link></KV>
        <KV label="Reason">{lbl(r.reason_category)}</KV>
        <KV label="Book value at request">{fmtMoney(r.book_value_at_request)}</KV>
        <KV label="Current book value">{fmtMoney(r.current_book_value)}</KV>
        <KV label="Requested by">{r.requested_by || '—'}</KV>
        <KV label="Justification">{r.justification}</KV>
        <KV label="Technical assessment">{r.technical_assessment || '—'}</KV>
        <KV label="Assessed by">{r.technical_assessment_by_name || '—'}</KV>
        <KV label="Committee reference">{r.committee_reference || '—'}</KV>
        <KV label="Committee decision date">{fmtDay(r.committee_decision_date)}</KV>
        <KV label="Decision note">{r.decision_note || '—'}</KV>
      </div>

      <div className="fin-section">
        <h3>Timeline</h3>
        <ul className="fin-timeline">
          {r.timeline.map((t, idx) => (
            <li key={`${t.event}-${idx}`}><strong>{lbl(t.event)}</strong> · {fmtStamp(t.at)}{t.by ? ` · ${t.by}` : ''}{t.note ? ` · ${t.note}` : ''}</li>
          ))}
        </ul>
      </div>

      <DisposalSection r={r} reload={res.reload} />

      <div className="fin-section">
        <h3>Documents</h3>
        <DocumentsPanel entityType="condemnation_request" entityId={r.public_id} viewPermission="condemnation.view" attachPermission="condemnation.add" />
      </div>

      {['approve', 'reject', 'cancel', 'revoke'].includes(dialog) && (
        <DecisionDialog kind={dialog} url={`/condemnation-requests/${r.public_id}/${dialog}/`} rowVersion={r.row_version}
          onClose={close} onDone={done({ approve: 'Condemnation approved.', reject: 'Request rejected.', cancel: 'Request cancelled.', revoke: 'Condemnation revoked.' }[dialog])} />
      )}
    </section>
  )
}
