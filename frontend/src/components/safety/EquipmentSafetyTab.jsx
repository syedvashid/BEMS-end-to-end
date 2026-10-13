import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useFacility } from '../../context/FacilityContext'
import { Button, Table, useToast } from '../ui'
import ReportIncidentModal from './ReportIncidentModal'
import { Chip, eqLabel, fmtDateTime, useFetch } from './shared'

/** Equipment detail "Safety" tab. Receives { equipment, reload } from the tab config. */
export default function EquipmentSafetyTab({ equipment: e, reload }) {
  const { can } = useFacility()
  const toast = useToast()
  const res = useFetch(`/equipment/${e.public_id}/safety/`)
  const [reporting, setReporting] = useState(false)
  const canReport = can('incident.add') && !['DISPOSED', 'REJECTED'].includes(e.lifecycle_stage)
  const data = res.data || {}

  if (!can('incident.view') && !can('recall.view')) return <p className="muted">You do not have access to safety records.</p>
  return (
    <div>
      <div className="page-head">
        <h3>Incidents</h3><span className="spacer" />
        {canReport && <Button variant="primary" onClick={() => setReporting(true)}>Report incident</Button>}
      </div>
      {data.incidents !== null && (
        <Table rows={data.incidents} loading={res.loading} empty="No incidents reported for this equipment."
          columns={[
            { key: 'incident_number', header: 'Number', render: (r) => <Link to={`/incidents/${r.public_id}`}>{r.incident_number}</Link> },
            { key: 'occurred_at', header: 'Occurred', render: (r) => fmtDateTime(r.occurred_at) },
            { key: 'incident_type', header: 'Type', render: (r) => r.incident_type.replace('_', ' ').toLowerCase() },
            { key: 'severity', header: 'Severity', render: (r) => <Chip kind="severity" value={r.severity} /> },
            { key: 'status', header: 'Status', render: (r) => <Chip kind="incident" value={r.status} /> },
          ]} />
      )}
      <div className="page-head"><h3>Recall units</h3></div>
      {data.recall_units !== null && (
        <Table rows={data.recall_units} loading={res.loading} empty="This equipment is not on any recall notice."
          columns={[
            { key: 'notice', header: 'Notice', render: (r) => <Link to={`/recall-notices/${r.notice.public_id}`}>{r.notice.notice_number}</Link> },
            { key: 'title', header: 'Title', render: (r) => r.notice.title },
            { key: 'urgency', header: 'Urgency', render: (r) => <Chip kind="urgency" value={r.notice.urgency} /> },
            { key: 'stop_use', header: 'Stop use', render: (r) => (r.notice.stop_use ? 'Yes' : 'No') },
            { key: 'status', header: 'Unit', render: (r) => <Chip kind="unit" value={r.status} /> },
            { key: 'notice_status', header: 'Notice status', render: (r) => <Chip kind="notice" value={r.notice.status} /> },
          ]} />
      )}
      {reporting && (
        <ReportIncidentModal equipment={{ public_id: e.public_id, label: eqLabel(e) }} onClose={() => setReporting(false)}
          onDone={(inc) => {
            setReporting(false)
            toast.success(`Incident ${inc.incident_number} reported.`)
            if (inc.quarantine?.message) toast.error(inc.quarantine.message)
            res.reload(); reload?.()
          }} />
      )}
    </div>
  )
}
