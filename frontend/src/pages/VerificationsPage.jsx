import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Chip, FilterSelect, SCOPE_TYPES, clean, fmtDate, lbl, opt, useFetch,
} from '../components/safety/shared'
import VerificationFormModal from '../components/safety/VerificationFormModal'
import SimplePager from '../components/SimplePager'
import { Button, FormField, Table, useToast } from '../components/ui'
import { useFacility } from '../context/FacilityContext'

export default function VerificationsPage() {
  const { can } = useFacility()
  const navigate = useNavigate()
  const toast = useToast()
  const [f, setF] = useState({ status: '', scope_type: '', planned_from: '', planned_to: '' })
  const [q, setQ] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [creating, setCreating] = useState(false)
  const set = (k) => (val) => { setF((s) => ({ ...s, [k]: val })); setPage(1) }
  const res = useFetch('/verifications/', clean({ ...f, search, page, page_size: 20 }))

  return (
    <section>
      <div className="page-head">
        <h2>Physical verification</h2><span className="spacer" />
        {can('verification.add') && <Button variant="primary" onClick={() => setCreating(true)}>New verification</Button>}
      </div>
      <div className="row">
        <FilterSelect label="Status" value={f.status} onChange={set('status')} options={opt(['PLANNED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED'])} />
        <FilterSelect label="Scope" value={f.scope_type} onChange={set('scope_type')} options={opt(SCOPE_TYPES)} />
        <FormField label="Planned from" name="pf" type="date" value={f.planned_from} onChange={(e) => set('planned_from')(e.target.value)} />
        <FormField label="Planned to" name="pt" type="date" value={f.planned_to} onChange={(e) => set('planned_to')(e.target.value)} />
        <FormField label="Search (number, title)" name="search" value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { setSearch(q.trim()); setPage(1) } }} />
        <Button size="sm" onClick={() => { setSearch(q.trim()); setPage(1) }}>Search</Button>
      </div>
      {res.error && <div className="alert alert-danger">{(res.error.message ?? res.error.error?.message) || 'Could not load verifications.'}</div>}
      <Table rows={res.data?.results} loading={res.loading} empty="No verifications found."
        onRowClick={(r) => navigate(`/verifications/${r.public_id}`)}
        columns={[
          { key: 'verification_number', header: 'Number' },
          { key: 'title', header: 'Title' },
          { key: 'scope', header: 'Scope', render: (r) => `${lbl(r.scope_type)}${r.department ? `: ${r.department.name}` : ''}${r.location ? `: ${r.location.name}` : ''}` },
          { key: 'planned_date', header: 'Planned', render: (r) => fmtDate(r.planned_date) },
          { key: 'status', header: 'Status', render: (r) => <Chip kind="verification" value={r.status} /> },
          { key: 'result', header: 'Result', render: (r) => (r.expected_count != null ? `${r.found_count} found of ${r.expected_count}, ${r.missing_count} missing` : '') },
        ]} />
      <SimplePager page={page} count={res.data?.count} pageSize={20} onPage={setPage} />
      {creating && (
        <VerificationFormModal onClose={() => setCreating(false)}
          onDone={(v) => { setCreating(false); toast.success(`Verification ${v.verification_number} created.`); navigate(`/verifications/${v.public_id}`) }} />
      )}
    </section>
  )
}
