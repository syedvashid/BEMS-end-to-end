import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import CondemnationRequestModal from '../components/finance/CondemnationRequestModal'
import {
  REASONS, RequestChip, clean, fmtDay, fmtMoney, lbl, opts, withBlank,
} from '../components/finance/shared'
import SimplePager from '../components/SimplePager'
import { Button, FormField, Table, useToast } from '../components/ui'
import { useFacility } from '../context/FacilityContext'
import useFetch from '../hooks/useFetch'

export default function CondemnationPage() {
  const { can } = useFacility()
  const navigate = useNavigate()
  const toast = useToast()
  const [f, setF] = useState({ status: '', reason_category: '', mine: false, date_from: '', date_to: '' })
  const [q, setQ] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [creating, setCreating] = useState(false)
  const set = (k) => (e) => { setF((s) => ({ ...s, [k]: e.target.value })); setPage(1) }
  const res = useFetch('/condemnation-requests/', clean({ ...f, mine: f.mine ? 'true' : '', search, page, page_size: 20 }))

  return (
    <section>
      <div className="page-head">
        <h2>Condemnation</h2><span className="spacer" />
        {can('condemnation.add') && <Button variant="primary" onClick={() => setCreating(true)}>Request condemnation</Button>}
      </div>
      <div className="row">
        <FormField label="Status" name="status" as="select" value={f.status} onChange={set('status')}
          options={withBlank(opts(['REQUESTED', 'APPROVED', 'REJECTED', 'CANCELLED', 'COMPLETED']))} />
        <FormField label="Reason" name="reason_category" as="select" value={f.reason_category} onChange={set('reason_category')}
          options={withBlank(opts(REASONS))} />
        <FormField label="From" name="date_from" type="date" value={f.date_from} onChange={set('date_from')} />
        <FormField label="To" name="date_to" type="date" value={f.date_to} onChange={set('date_to')} />
        <FormField label="Search (request number)" name="search" value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { setSearch(q.trim()); setPage(1) } }} />
        <Button size="sm" onClick={() => { setSearch(q.trim()); setPage(1) }}>Search</Button>
        <label><input type="checkbox" checked={f.mine} onChange={(e) => { setF((s) => ({ ...s, mine: e.target.checked })); setPage(1) }} /> My requests</label>
      </div>
      {res.error && <div className="alert alert-danger">{(res.error.message ?? res.error.error?.message) || 'Could not load requests.'}</div>}
      <Table rows={res.data?.results} loading={res.loading} empty="No condemnation requests found."
        onRowClick={(r) => navigate(`/condemnation/${r.public_id}`)}
        columns={[
          { key: 'request_number', header: 'Number' },
          { key: 'equipment', header: 'Equipment', render: (r) => `${r.equipment.asset_tag} · ${r.equipment.name}` },
          { key: 'reason_category', header: 'Reason', render: (r) => lbl(r.reason_category) },
          { key: 'book_value_at_request', header: 'Book value', render: (r) => fmtMoney(r.book_value_at_request) },
          { key: 'status', header: 'Status', render: (r) => <RequestChip value={r.status} /> },
          { key: 'requested_by', header: 'Requested by', render: (r) => r.requested_by || '—' },
          { key: 'created_at', header: 'Requested', render: (r) => fmtDay(r.created_at) },
        ]} />
      <SimplePager page={page} count={res.data?.count} pageSize={20} onPage={setPage} />
      {creating && (
        <CondemnationRequestModal onClose={() => setCreating(false)}
          onDone={(r) => { setCreating(false); toast.success(`Request ${r.request_number} created.`); navigate(`/condemnation/${r.public_id}`) }} />
      )}
    </section>
  )
}
