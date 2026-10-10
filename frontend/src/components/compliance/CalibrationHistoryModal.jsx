import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Modal, StatusBadge } from '../ui'
import DocumentsPanel from '../DocumentsPanel'
import { fmtDate, useFetch } from './shared'
import ImpactReviewModal from './ImpactReviewModal'

export default function CalibrationHistoryModal({ schedule, canReview, onClose }) {
  const { data, loading, reload } = useFetch('/calibration-records/', { equipment: schedule.equipment, page_size: 50 })
  const [open, setOpen] = useState(null)
  const [review, setReview] = useState(null)
  const rows = data?.results || []

  return (
    <Modal wide title={`Calibration history — ${schedule.equipment_asset_tag} ${schedule.equipment_name}`} onClose={onClose}
      footer={<Button variant="secondary" onClick={onClose}>Close</Button>}>
      {loading && <p>Loading…</p>}
      {!loading && rows.length === 0 && <p>No calibration has been recorded yet.</p>}
      {rows.map((r) => (
        <div key={r.public_id} style={{ borderBottom: '1px solid var(--border, #ddd)', padding: '8px 0' }}>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            <strong>{fmtDate(r.performed_date)}</strong>
            <StatusBadge tone={r.result === 'PASS' ? 'success' : 'danger'}>{r.result === 'PASS' ? 'Pass' : 'Fail'}</StatusBadge>
            {r.impact_review_required && <StatusBadge tone="warning">Impact review required</StatusBadge>}
            <span>Cert: {r.certificate_number || '—'}</span>
            <span>Next due: {fmtDate(r.next_due_date)}</span>
            <Button size="sm" variant="ghost" onClick={() => setOpen(open === r.public_id ? null : r.public_id)}>
              {open === r.public_id ? 'Hide' : 'Details'}
            </Button>
            {r.impact_review_required && canReview && <Button size="sm" onClick={() => setReview(r)}>Review impact</Button>}
          </div>
          {open === r.public_id && (
            <div style={{ marginTop: 8 }}>
              <p>Performed by: {r.performed_by_type.replace('_', ' ').toLowerCase()} {r.performer_name || ''}</p>
              {r.reference_standard_details && <p>Reference standard: {r.reference_standard_details}</p>}
              {r.deviation_summary && <p>Deviation: {r.deviation_summary}</p>}
              {r.notes && <p>Notes: {r.notes}</p>}
              {r.readings?.length > 0 && (
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%' }}>
                    <thead><tr><th>Parameter</th><th>Nominal</th><th>Measured</th><th>Unit</th><th>Tolerance</th></tr></thead>
                    <tbody>{r.readings.map((x, i) => (
                      <tr key={i}><td>{x.parameter}</td><td>{x.nominal ?? ''}</td><td>{x.measured ?? ''}</td><td>{x.unit ?? ''}</td><td>{x.tolerance ?? ''}</td></tr>
                    ))}</tbody>
                  </table>
                </div>
              )}
              {r.impact_review && (
                <p>Impact review: {r.impact_review.review_notes} — patient impact {r.impact_review.patient_impact_found ? 'found' : 'not found'}.</p>
              )}
              {r.corrective_work_order && (
                <p>Work order: <Link to={`/work-orders/${r.corrective_work_order.public_id}`}>{r.corrective_work_order.wo_number}</Link> ({r.corrective_work_order.status})</p>
              )}
              <h5>Certificate and documents</h5>
              <DocumentsPanel entityType="calibration_record" entityId={r.public_id} />
            </div>
          )}
        </div>
      ))}
      {review && <ImpactReviewModal record={review} onClose={() => setReview(null)} onSaved={() => { setReview(null); reload() }} />}
    </Modal>
  )
}