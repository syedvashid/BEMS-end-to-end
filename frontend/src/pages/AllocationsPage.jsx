import { useState } from 'react'
import SimplePager from '../components/SimplePager'
import ReleaseDialog from '../components/allocation/ReleaseDialog'
import {
  Button, EqLink, FormField, SOURCES, StatusBadge, Table, clean, fmtDateTime, toOpts, useFetch, withBlank,
} from '../components/allocation/shared'
import { useToast } from '../components/ui'
import { useFacility } from '../context/FacilityContext'
import '../styles/maintenance.css'
import '../styles/allocation.css'

export default function AllocationsPage() {
  const { can } = useFacility()
  const toast = useToast()
  const [tab, setTab] = useState('active')
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [source, setSource] = useState('')
  const [rel, setRel] = useState(null)
  const res = useFetch('/allocations/', clean({
    active: tab === 'active', search, source_module: source, page, page_size: 20,
  }))
  const history = tab === 'history'
  return (
    <section>
      <div className="page-head"><h2>Allocations</h2></div>
      <div className="eq-tabs">
        {[['active', 'Active'], ['history', 'History']].map(([k, l]) => (
          <button key={k} type="button" className={`eq-tab${tab === k ? ' active' : ''}`} onClick={() => { setTab(k); setPage(1) }}>{l}</button>
        ))}
      </div>
      <div className="mt-toolbar">
        <FormField label="Search" name="search" value={search} onChange={(e) => { setPage(1); setSearch(e.target.value) }} />
        <FormField label="Source" name="source" as="select" options={withBlank(toOpts(SOURCES), 'All')} value={source} onChange={(e) => { setPage(1); setSource(e.target.value) }} />
      </div>
      <Table rows={res.data?.results} loading={res.loading} empty="No allocations." columns={[
        { key: 'eq', header: 'Equipment', render: (a) => <EqLink e={a.equipment} /> },
        { key: 't', header: 'To', render: (a) => [a.department?.name, a.location?.name].filter(Boolean).join(' / ') || '—' },
        { key: 'src', header: 'Source', render: (a) => a.source_module },
        { key: 'pt', header: 'Patient', render: (a) => a.patient_reference || '—' },
        { key: 'since', header: 'Since', render: (a) => fmtDateTime(a.assigned_at) },
        { key: 'exp', header: 'Expected release', render: (a) => (a.expected_release_at ? fmtDateTime(a.expected_release_at) : '—') },
        ...(history ? [
          { key: 'ra', header: 'Released', render: (a) => fmtDateTime(a.released_at) },
          { key: 'c', header: 'Condition', render: (a) => a.condition_on_release },
        ] : []),
        { key: 'ov', header: '', render: (a) => (a.gate_override ? <StatusBadge tone="warning">Gate overridden</StatusBadge> : null) },
        { key: 'act', header: '', render: (a) => (!a.is_released && can('allocation.assign') ? <Button size="sm" onClick={() => setRel(a)}>Release</Button> : null) },
      ]} />
      <SimplePager page={page} count={res.data?.count} pageSize={20} onPage={setPage} />
      {rel && <ReleaseDialog allocation={rel} onClose={() => setRel(null)}
        onDone={() => { setRel(null); toast.success('Equipment released.'); res.reload() }} />}
    </section>
  )
}