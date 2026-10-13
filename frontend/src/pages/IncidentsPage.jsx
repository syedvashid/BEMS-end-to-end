import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ReportIncidentModal from '../components/safety/ReportIncidentModal'
import {
  Chip, FilterSelect, INCIDENT_STATUSES, INCIDENT_TYPES, SEVERITIES, clean, fmtDateTime, opt, useFetch,
} from '../components/safety/shared'
import SimplePager from '../components/SimplePager'
import { Button, FormField, Table, useToast } from '../components/ui'
import { useFacility } from '../context/FacilityContext'

const BLANK = { status: '', severity: '', incident_type: '', reportable: '', mine: false, occurred_from: '', occurred_to: '' }

export default function IncidentsPage() {
  const { can } = useFacility()
  const navigate = useNavigate()
  const toast = useToast()
  const [f, setF] = useState(BLANK)
  const [q, setQ] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [reporting, setReporting] = useState(false)
  const set = (k) => (val) => { setF((s) => ({ ...s, [k]: val })); setPage(1) }
  const res = useFetch('/incidents/', clean({ ...f, mine: f.mine ? 'true' : '', search, page, page_size: 20 }))

  return (
    <section>
      <div className="page-head">
        <h2>Incidents</h2><span className="spacer" />
        {can('incident.add') && <Button variant="primary" onClick={() => setReporting(true)}>Report incident</Button>}
      </div>
      <div className="row">
        <FilterSelect label="Status" value={f.status} onChange={set('status')} options={opt(INCIDENT_STATUSES)} />
        <FilterSelect label="Severity" value={f.severity} onChange={set('severity')} options={opt(SEVERITIES)} />
        <FilterSelect label="Type" value={f.incident_type} onChange={set('incident_type')} options={opt(INCIDENT_TYPES)} />
        <FilterSelect label="Reportable" value={f.reportable} onChange={set('reportable')}
          options={[{ value: 'true', label: 'Yes' }, { value: 'false', label: 'No' }]} />
        <FormField label="From" name="from" type="date" value={f.occurred_from} onChange={(e) => set('occurred_from')(e.target.value)} />
        <FormField label="To" name="to" type="date" value={f.occurred_to} onChange={(e) => set('occurred_to')(e.target.value)} />
        <FormField label="Search (number, description)" name="search" value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { setSearch(q.trim()); setPage(1) } }} />
        <label><input type="checkbox" checked={f.mine} onChange={(e) => set('mine')(e.target.checked)} /> Mine</label>
        <Button size="sm" onClick={() => { setSearch(q.trim()); setPage(1) }}>Search</Button>
        <Button size="sm" variant="ghost" onClick={() => { setF(BLANK); setQ(''); setSearch(''); setPage(1) }}>Clear</Button>
      </div>
      {res.error && <div className="alert alert-danger">{(res.error.message ?? res.error.error?.message) || 'Could not load incidents.'}</div>}
      <Table rows={res.data?.results} loading={res.loading} empty="No incidents found."
        onRowClick={(r) => navigate(`/incidents/${r.public_id}`)}
        columns={[
          { key: 'incident_number', header: 'Number' },
          { key: 'equipment', header: 'Equipment', render: (r) => `${r.equipment.asset_tag} · ${r.equipment.name}` },
          { key: 'incident_type', header: 'Type', render: (r) => r.incident_type.replace('_', ' ').toLowerCase() },
          { key: 'severity', header: 'Severity', render: (r) => <Chip kind="severity" value={r.severity} /> },
          { key: 'occurred_at', header: 'Occurred', render: (r) => fmtDateTime(r.occurred_at) },
          { key: 'status', header: 'Status', render: (r) => <Chip kind="incident" value={r.status} /> },
          { key: 'reportable', header: 'Reportable', render: (r) => (r.reportable_to_regulator ? (r.regulator_report_reference ? 'Reported' : 'Yes') : '') },
        ]} />
      <SimplePager page={page} count={res.data?.count} pageSize={20} onPage={setPage} />
      {reporting && (
        <ReportIncidentModal onClose={() => setReporting(false)}
          onDone={(inc) => {
            setReporting(false)
            toast.success(`Incident ${inc.incident_number} reported.`)
            if (inc.quarantine?.message) toast.error(inc.quarantine.message)
            navigate(`/incidents/${inc.public_id}`)
          }} />
      )}
    </section>
  )
}
