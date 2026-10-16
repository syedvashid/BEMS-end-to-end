import { useState } from 'react'
import AuditDetailModal from '../audit/AuditDetailModal.jsx'
import { Pagination, StatusBadge, Table } from '../ui'
import { FetchError, fmtStamp, useFetch } from '../reports/shared.jsx'

const PAGE = 15

export default function EquipmentAuditTab({ equipmentId }) {
  const [page, setPage] = useState(1)
  const [detailId, setDetailId] = useState(null)
  const res = useFetch(`/equipment/${equipmentId}/audit/`, { page, page_size: PAGE })
  const columns = [
    { key: 'occurred_at', header: 'When', render: (r) => fmtStamp(r.occurred_at) },
    { key: 'actor_username', header: 'Who', render: (r) => r.actor_username || 'system' },
    { key: 'action', header: 'Action', render: (r) => <StatusBadge tone="info">{r.action}</StatusBadge> },
    { key: 'changed_fields', header: 'Changed', render: (r) => (r.changed_fields || []).join(', ') || '—' },
  ]
  return (
    <>
      <FetchError error={res.error} />
      <Table columns={columns} rows={res.data?.results} rowKey="id" loading={res.loading} onRowClick={(r) => setDetailId(r.id)} empty="No audit events for this equipment." />
      <Pagination page={page} pageSize={PAGE} count={res.data?.count ?? 0} onPageChange={setPage} />
      {detailId && <AuditDetailModal id={detailId} onClose={() => setDetailId(null)} />}
    </>
  )
}
