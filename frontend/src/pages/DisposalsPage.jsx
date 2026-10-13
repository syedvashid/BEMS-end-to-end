import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  DISPOSAL_METHODS, DisposalChip, clean, fmtDay, fmtMoney, lbl, opts, withBlank,
} from '../components/finance/shared'
import SimplePager from '../components/SimplePager'
import { Button, FormField, Table } from '../components/ui'
import useFetch from '../hooks/useFetch'

export default function DisposalsPage() {
  const navigate = useNavigate()
  const [f, setF] = useState({ status: '', method: '', date_from: '', date_to: '' })
  const [q, setQ] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const set = (k) => (e) => { setF((s) => ({ ...s, [k]: e.target.value })); setPage(1) }
  const res = useFetch('/disposals/', clean({ ...f, search, page, page_size: 20 }))

  return (
    <section>
      <div className="page-head"><h2>Disposals</h2></div>
      <p className="muted">Disposals are created from an approved condemnation request.</p>
      <div className="row">
        <FormField label="Status" name="status" as="select" value={f.status} onChange={set('status')}
          options={withBlank(opts(['IN_PROGRESS', 'COMPLETED', 'CANCELLED']))} />
        <FormField label="Method" name="method" as="select" value={f.method} onChange={set('method')}
          options={withBlank(opts(DISPOSAL_METHODS))} />
        <FormField label="Disposed from" name="date_from" type="date" value={f.date_from} onChange={set('date_from')} />
        <FormField label="Disposed to" name="date_to" type="date" value={f.date_to} onChange={set('date_to')} />
        <FormField label="Search (number)" name="search" value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { setSearch(q.trim()); setPage(1) } }} />
        <Button size="sm" onClick={() => { setSearch(q.trim()); setPage(1) }}>Search</Button>
      </div>
      {res.error && <div className="alert alert-danger">{(res.error.message ?? res.error.error?.message) || 'Could not load disposals.'}</div>}
      <Table rows={res.data?.results} loading={res.loading} empty="No disposals found."
        onRowClick={(r) => navigate(`/condemnation/${r.condemnation_request}`)}
        columns={[
          { key: 'disposal_number', header: 'Number' },
          { key: 'equipment', header: 'Equipment', render: (r) => `${r.equipment.asset_tag} · ${r.equipment.name}` },
          { key: 'disposal_method', header: 'Method', render: (r) => lbl(r.disposal_method) },
          { key: 'disposal_date', header: 'Date', render: (r) => fmtDay(r.disposal_date) },
          { key: 'proceeds_amount', header: 'Proceeds', render: (r) => fmtMoney(r.proceeds_amount) },
          { key: 'gain_loss', header: 'Gain / loss', render: (r) => fmtMoney(r.gain_loss) },
          { key: 'status', header: 'Status', render: (r) => <DisposalChip value={r.status} /> },
        ]} />
      <SimplePager page={page} count={res.data?.count} pageSize={20} onPage={setPage} />
    </section>
  )
}
