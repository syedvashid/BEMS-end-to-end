import { useState } from 'react'
import SimplePager from '../components/SimplePager'
import UsageLogModal from '../components/allocation/UsageLogModal'
import { Button, EqLink, FormField, Table, api, clean, fmtDateTime, useFetch } from '../components/allocation/shared'
import { useToast } from '../components/ui'
import { useFacility } from '../context/FacilityContext'
import '../styles/maintenance.css'
import '../styles/allocation.css'

export default function UsageLogsPage() {
  const { can } = useFacility()
  const toast = useToast()
  const [page, setPage] = useState(1)
  const [f, setF] = useState({ search: '', date_from: '', date_to: '' })
  const [modal, setModal] = useState(null)
  const set = (k) => (e) => { setPage(1); setF((s) => ({ ...s, [k]: e.target.value })) }
  const res = useFetch('/usage-logs/', clean({ ...f, page, page_size: 20 }))
  const remove = async (u) => {
    if (!window.confirm('Delete this usage log?')) return
    try { await api.delete(`/usage-logs/${u.public_id}/`, { params: { row_version: u.row_version } }); toast.success('Deleted.'); res.reload() }
    catch { toast.error('Could not delete the usage log.') }
  }
  return (
    <section>
      <div className="page-head"><h2>Usage logs</h2><span className="spacer" />
        {can('usage.add') && <Button variant="primary" onClick={() => setModal('new')}>Add usage</Button>}
      </div>
      <div className="mt-toolbar">
        <FormField label="Search" name="search" value={f.search} onChange={set('search')} />
        <FormField label="From" name="date_from" type="date" value={f.date_from} onChange={set('date_from')} />
        <FormField label="To" name="date_to" type="date" value={f.date_to} onChange={set('date_to')} />
      </div>
      <Table rows={res.data?.results} loading={res.loading} empty="No usage logged." columns={[
        { key: 'eq', header: 'Equipment', render: (u) => <EqLink e={u.equipment} /> },
        { key: 's', header: 'Started', render: (u) => fmtDateTime(u.started_at) },
        { key: 'e', header: 'Ended', render: (u) => fmtDateTime(u.ended_at) },
        { key: 'm', header: 'Minutes', render: (u) => Number(u.duration_minutes).toFixed(0) },
        { key: 'o', header: 'Operator', render: (u) => u.operator_name || '—' },
        { key: 'd', header: 'Department', render: (u) => u.department?.name || '—' },
        { key: 'pr', header: 'Procedure', render: (u) => u.procedure_text || '—' },
        { key: 'act', header: '', render: (u) => (
          <div className="mt-actions">
            {can('usage.change') && <Button size="sm" onClick={() => setModal(u)}>Edit</Button>}
            {can('usage.delete') && <Button size="sm" variant="danger" onClick={() => remove(u)}>Delete</Button>}
          </div>) },
      ]} />
      <SimplePager page={page} count={res.data?.count} pageSize={20} onPage={setPage} />
      {modal && <UsageLogModal log={modal === 'new' ? null : modal} onClose={() => setModal(null)}
        onDone={() => { setModal(null); toast.success('Saved.'); res.reload() }} />}
    </section>
  )
}