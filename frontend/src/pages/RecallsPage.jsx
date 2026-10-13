import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import RecallFormModal from '../components/safety/RecallFormModal'
import {
  Chip, FilterSelect, NOTICE_TYPES, URGENCIES, clean, fmtDate, lbl, opt, useFetch,
} from '../components/safety/shared'
import SimplePager from '../components/SimplePager'
import { Button, FormField, Table, useToast } from '../components/ui'
import { useFacility } from '../context/FacilityContext'

export default function RecallsPage() {
  const { can } = useFacility()
  const navigate = useNavigate()
  const toast = useToast()
  const [f, setF] = useState({ status: '', urgency: '', notice_type: '' })
  const [q, setQ] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [creating, setCreating] = useState(false)
  const set = (k) => (val) => { setF((s) => ({ ...s, [k]: val })); setPage(1) }
  const res = useFetch('/recall-notices/', clean({ ...f, search, page, page_size: 20 }))

  return (
    <section>
      <div className="page-head">
        <h2>Recalls &amp; field safety notices</h2><span className="spacer" />
        {can('recall.add') && <Button variant="primary" onClick={() => setCreating(true)}>New notice</Button>}
      </div>
      <div className="row">
        <FilterSelect label="Status" value={f.status} onChange={set('status')} options={opt(['OPEN', 'CLOSED', 'CANCELLED'])} />
        <FilterSelect label="Urgency" value={f.urgency} onChange={set('urgency')} options={opt(URGENCIES)} />
        <FilterSelect label="Type" value={f.notice_type} onChange={set('notice_type')} options={opt(NOTICE_TYPES)} />
        <FormField label="Search (number, title, reference)" name="search" value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { setSearch(q.trim()); setPage(1) } }} />
        <Button size="sm" onClick={() => { setSearch(q.trim()); setPage(1) }}>Search</Button>
      </div>
      {res.error && <div className="alert alert-danger">{(res.error.message ?? res.error.error?.message) || 'Could not load notices.'}</div>}
      <Table rows={res.data?.results} loading={res.loading} empty="No notices found."
        onRowClick={(r) => navigate(`/recall-notices/${r.public_id}`)}
        columns={[
          { key: 'notice_number', header: 'Number' },
          { key: 'title', header: 'Title' },
          { key: 'notice_type', header: 'Type', render: (r) => lbl(r.notice_type) },
          { key: 'urgency', header: 'Urgency', render: (r) => <Chip kind="urgency" value={r.urgency} /> },
          { key: 'stop_use', header: 'Stop use', render: (r) => (r.stop_use ? 'Yes' : 'No') },
          { key: 'issued_date', header: 'Issued', render: (r) => fmtDate(r.issued_date) },
          { key: 'counts', header: 'Resolved', render: (r) => (r.counts ? `${r.counts.completed + r.counts.not_applicable} / ${r.counts.units}` : '') },
          { key: 'status', header: 'Status', render: (r) => <Chip kind="notice" value={r.status} /> },
        ]} />
      <SimplePager page={page} count={res.data?.count} pageSize={20} onPage={setPage} />
      {creating && (
        <RecallFormModal onClose={() => setCreating(false)}
          onDone={(n) => { setCreating(false); toast.success(`Notice ${n.notice_number} created.`); navigate(`/recall-notices/${n.public_id}`) }} />
      )}
    </section>
  )
}
