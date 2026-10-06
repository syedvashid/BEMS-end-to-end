import { useState } from 'react'
import { Button, FormField, Modal, Pagination, StatusBadge, Table } from '../components/ui'
import useFetch from '../hooks/useFetch'
import { formatDateTime, PAGE_SIZE } from '../utils/format'

const EMPTY = { entity_type: '', entity_public_id: '', actor: '', action: '', from: '', to: '' }
const iso = (v) => (v ? new Date(v).toISOString() : '')

export default function AuditLogPage() {
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState(EMPTY)
  const [applied, setApplied] = useState(EMPTY)
  const [detail, setDetail] = useState(null)
  const list = useFetch('/audit-logs/', {
    page, page_size: PAGE_SIZE,
    entity_type: applied.entity_type, entity_public_id: applied.entity_public_id.trim(),
    actor: applied.actor, action: applied.action.trim().toUpperCase(),
    occurred_from: iso(applied.from), occurred_to: iso(applied.to),
  })
  const set = (name) => (e) => setFilters((f) => ({ ...f, [name]: e.target.value }))

  const columns = [
    { key: 'occurred_at', header: 'Time', render: (r) => formatDateTime(r.occurred_at) },
    { key: 'actor_username', header: 'Actor' },
    { key: 'action', header: 'Action', render: (r) => <StatusBadge tone={r.action === 'ACCESS_DENIED' ? 'danger' : 'info'}>{r.action}</StatusBadge> },
    { key: 'entity_type', header: 'Entity' },
    { key: 'entity_public_id', header: 'Entity ID', render: (r) => <span className="mono">{r.entity_public_id ?? '—'}</span> },
    { key: 'changed_fields', header: 'Changed', render: (r) => (r.changed_fields ?? []).join(', ') || '—' },
  ]

  return (
    <>
      <div className="page-head"><h1>Audit Log</h1><StatusBadge tone="warning">Basic view, read-only</StatusBadge></div>
      <form className="filters" onSubmit={(e) => { e.preventDefault(); setPage(1); setApplied(filters) }}>
        <FormField label="Entity type" name="a_entity" value={filters.entity_type} onChange={set('entity_type')} placeholder="User, Facility, Role" />
        <FormField label="Entity ID" name="a_entity_id" value={filters.entity_public_id} onChange={set('entity_public_id')} />
        <FormField label="Actor" name="a_actor" value={filters.actor} onChange={set('actor')} placeholder="username" />
        <FormField label="Action" name="a_action" value={filters.action} onChange={set('action')} placeholder="CREATE" />
        <FormField label="From" name="a_from" type="datetime-local" value={filters.from} onChange={set('from')} />
        <FormField label="To" name="a_to" type="datetime-local" value={filters.to} onChange={set('to')} />
        <Button type="submit" variant="primary">Filter</Button>
        <Button onClick={() => { setFilters(EMPTY); setApplied(EMPTY); setPage(1) }}>Reset</Button>
      </form>
      {list.error && <div className="alert alert-danger">{list.error.message}</div>}
      <Table columns={columns} rows={list.data?.results} rowKey="id" loading={list.loading} onRowClick={setDetail} />
      <Pagination page={page} pageSize={PAGE_SIZE} count={list.data?.count ?? 0} onPageChange={setPage} />
      {detail && (
        <Modal wide title={`Audit event #${detail.id}`} onClose={() => setDetail(null)} footer={<Button onClick={() => setDetail(null)}>Close</Button>}>
          <p className="muted">{formatDateTime(detail.occurred_at)} · {detail.actor_username ?? 'system'} · {detail.http_method} {detail.request_path} · request {detail.request_id}</p>
          <h2>Previous value</h2><pre className="json">{JSON.stringify(detail.previous_value, null, 2)}</pre>
          <h2 style={{ marginTop: 12 }}>New value</h2><pre className="json">{JSON.stringify(detail.new_value, null, 2)}</pre>
        </Modal>
      )}
    </>
  )
}