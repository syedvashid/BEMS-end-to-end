import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AuditDetailModal from '../components/audit/AuditDetailModal.jsx'
import { Button, FormField, Pagination, StatusBadge, Table } from '../components/ui'
import {
  api, apiError, ErrorNote, FetchError, fmtStamp, useFetch, usePermission,
} from '../components/reports/shared.jsx'
import { PAGE_SIZE } from '../utils/format'

const EMPTY = { entity_type: '', entity_public_id: '', actor: '', action: '', occurred_from: '', occurred_to: '', request_id: '' }

export default function AuditTrailPage() {
  const navigate = useNavigate()
  const canVerify = usePermission('audit.verify')
  const canReport = usePermission('report.view')
  const [page, setPage] = useState(1)
  const [draft, setDraft] = useState(EMPTY)
  const [applied, setApplied] = useState(EMPTY)
  const [detailId, setDetailId] = useState(null)
  const [verify, setVerify] = useState(null)
  const [verifyError, setVerifyError] = useState(null)
  const [verifying, setVerifying] = useState(false)

  const facets = useFetch('/audit-logs/facets/')
  const list = useFetch('/audit-logs/', { ...applied, entity_public_id: applied.entity_public_id.trim(), page, page_size: PAGE_SIZE })
  const set = (k) => (e) => setDraft((d) => ({ ...d, [k]: e.target.value }))
  const dropdown = (values, blank) => [{ value: '', label: blank }, ...(values || []).map((v) => ({ value: v, label: v }))]

  const runVerify = async () => {
    setVerifying(true); setVerify(null); setVerifyError(null)
    try { setVerify((await api.post('/audit-logs/verify-chain/')).data) } catch (e) { setVerifyError(apiError(e)) } finally { setVerifying(false) }
  }
  const exportTrail = () => {
    const q = new URLSearchParams({ report: 'AUDIT_TRAIL' })
    const map = { entity_type: 'entity_type', entity_public_id: 'entity_public_id', actor: 'actor', action: 'action', occurred_from: 'from', occurred_to: 'to' }
    Object.entries(map).forEach(([k, name]) => { if (applied[k]) q.set(name, applied[k].trim()) })
    navigate(`/reports?${q.toString()}`)
  }

  const columns = [
    { key: 'occurred_at', header: 'Time', render: (r) => fmtStamp(r.occurred_at) },
    { key: 'actor_username', header: 'Actor', render: (r) => r.actor_username || 'system' },
    { key: 'action', header: 'Action', render: (r) => <StatusBadge tone={r.action === 'ACCESS_DENIED' ? 'danger' : 'info'}>{r.action}</StatusBadge> },
    { key: 'entity_type', header: 'Entity', render: (r) => r.entity_type || '—' },
    { key: 'entity_public_id', header: 'Entity ID', render: (r) => <span className="mono">{r.entity_public_id ?? '—'}</span> },
    { key: 'changed_fields', header: 'Changed', render: (r) => (r.changed_fields || []).join(', ') || '—' },
  ]

  return (
    <>
      <div className="page-head">
        <h1>Audit Trail</h1>
        <div className="rp-actions">
          {canReport && <Button onClick={exportTrail}>Export</Button>}
          {canVerify && <Button onClick={runVerify} loading={verifying}>Verify integrity</Button>}
        </div>
      </div>
      {verify && (
        <div className={`alert ${verify.ok ? 'alert-success' : 'alert-danger'}`}>
          {verify.ok ? 'The audit chain is intact.' : `The audit chain is broken. First broken entry: #${verify.first_broken_id}.`}
        </div>
      )}
      <ErrorNote error={verifyError} />
      <form className="rp-toolbar" onSubmit={(e) => { e.preventDefault(); setPage(1); setApplied(draft) }}>
        <FormField label="Entity type" name="at_type" as="select" value={draft.entity_type} onChange={set('entity_type')} options={dropdown(facets.data?.entity_types, 'All')} />
        <FormField label="Entity ID" name="at_eid" value={draft.entity_public_id} onChange={set('entity_public_id')} />
        <FormField label="Actor" name="at_actor" value={draft.actor} onChange={set('actor')} placeholder="username contains" />
        <FormField label="Action" name="at_action" as="select" value={draft.action} onChange={set('action')} options={dropdown(facets.data?.actions, 'All')} />
        <FormField label="From" name="at_from" type="date" value={draft.occurred_from} onChange={set('occurred_from')} />
        <FormField label="To" name="at_to" type="date" value={draft.occurred_to} onChange={set('occurred_to')} />
        <FormField label="Request ID" name="at_req" value={draft.request_id} onChange={set('request_id')} />
        <Button type="submit" variant="primary">Filter</Button>
        <Button onClick={() => { setDraft(EMPTY); setApplied(EMPTY); setPage(1) }}>Reset</Button>
      </form>
      <FetchError error={list.error} />
      <Table columns={columns} rows={list.data?.results} rowKey="id" loading={list.loading} onRowClick={(r) => setDetailId(r.id)} empty="No audit events match." />
      <Pagination page={page} pageSize={PAGE_SIZE} count={list.data?.count ?? 0} onPageChange={setPage} />
      {detailId && <AuditDetailModal id={detailId} onClose={() => setDetailId(null)} />}
    </>
  )
}
