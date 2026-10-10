import { useState } from 'react'
import { Button, StatusBadge, Table } from '../ui'
import ClaimModal from './ClaimModal'
import { fmtDate, useFetch, usePermission } from './shared'

const TONE = { RAISED: 'info', ACCEPTED: 'success', REJECTED: 'danger', RESOLVED: 'neutral' }

/** Claims of one warranty (warranty prop) or of one equipment (equipment prop, read + edit only). */
export default function ClaimsSection({ warranty, equipment }) {
  const canAdd = usePermission('warranty.add')
  const canChange = usePermission('warranty.change')
  const { data, loading, reload } = useFetch('/warranty-claims/', warranty ? { warranty: warranty.public_id } : { equipment })
  const [modal, setModal] = useState(null)
  const cols = [
    { key: 'claim_number', header: 'Claim', render: (r) => r.claim_number || '—' },
    { key: 'claim_date', header: 'Date', render: (r) => fmtDate(r.claim_date) },
    { key: 'description', header: 'Description' },
    { key: 'status', header: 'Status', render: (r) => <StatusBadge tone={TONE[r.status]}>{r.status.toLowerCase()}</StatusBadge> },
    { key: 'claim_amount', header: 'Amount', render: (r) => r.claim_amount ?? '—' },
  ]
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h4>Claims</h4>
        {warranty && canAdd && <Button size="sm" onClick={() => setModal({})}>Add claim</Button>}
      </div>
      <Table columns={cols} rows={data?.results || []} loading={loading} empty="No claims."
        onRowClick={canChange ? (r) => setModal({ claim: r, warranty: { public_id: r.warranty } }) : undefined} />
      {modal && <ClaimModal warranty={modal.warranty || warranty} claim={modal.claim} onClose={() => setModal(null)}
        onSaved={() => { setModal(null); reload() }} />}
    </div>
  )
}