import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import DocumentsPanel from '../components/DocumentsPanel'
import {
  ActionModal, Check, Chip, ErrorBox, INCIDENT_TYPES, SEVERITIES, api, fieldError, fmt, fmtDate, fmtDateTime, lbl, nn,
  opt, today, useAction, useFetch,
} from '../components/safety/shared'
import { Button, FormField, Table, useToast } from '../components/ui'
import { useFacility } from '../context/FacilityContext'

const KV = ({ label, children }) => (
  <div className="eq-kv"><span className="muted">{label}</span><span>{children}</span></div>
)
const Section = ({ title, children, right }) => (
  <div className="mt-section"><div className="page-head"><h3>{title}</h3><span className="spacer" />{right}</div>{children}</div>
)

function InvestigationForm({ inc, reload }) {
  const toast = useToast()
  const act = useAction()
  const [f, setF] = useState(null)
  useEffect(() => {
    setF({
      incident_type: inc.incident_type, severity: inc.severity, patient_affected: inc.patient_affected,
      staff_affected: inc.staff_affected, reportable_to_regulator: inc.reportable_to_regulator,
      root_cause: inc.root_cause || '', corrective_action: inc.corrective_action || '',
      preventive_action: inc.preventive_action || '', investigation_notes: inc.investigation_notes || '',
    })
  }, [inc.row_version, inc.public_id]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!f) return null
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }))
  const save = async () => {
    const r = await act.run(() => api.patch(`/incidents/${inc.public_id}/`, {
      incident_type: f.incident_type, severity: f.severity, patient_affected: f.patient_affected,
      staff_affected: f.staff_affected, reportable_to_regulator: f.reportable_to_regulator,
      root_cause: nn(f.root_cause.trim()), corrective_action: nn(f.corrective_action.trim()),
      preventive_action: nn(f.preventive_action.trim()), investigation_notes: nn(f.investigation_notes.trim()),
      row_version: inc.row_version,
    }))
    if (r.ok) { toast.success('Saved.'); reload() }
  }
  return (
    <div>
      <ErrorBox error={act.error} />
      <FormField label="Type" name="incident_type" as="select" options={opt(INCIDENT_TYPES)} value={f.incident_type} onChange={set('incident_type')} error={fieldError(act.error, 'incident_type')} />
      <FormField label="Severity" name="severity" as="select" options={opt(SEVERITIES)} value={f.severity} onChange={set('severity')} error={fieldError(act.error, 'severity')} />
      <Check label="Patient affected" checked={f.patient_affected} onChange={(e) => setF((s) => ({ ...s, patient_affected: e.target.checked }))} />
      <Check label="Staff affected" checked={f.staff_affected} onChange={(e) => setF((s) => ({ ...s, staff_affected: e.target.checked }))} />
      <Check label="Reportable to the regulator" checked={f.reportable_to_regulator}
        onChange={(e) => setF((s) => ({ ...s, reportable_to_regulator: e.target.checked }))} />
      <FormField label="Root cause" name="root_cause" as="textarea" value={f.root_cause} onChange={set('root_cause')} error={fieldError(act.error, 'root_cause')} />
      <FormField label="Corrective action" name="corrective_action" as="textarea" value={f.corrective_action} onChange={set('corrective_action')} error={fieldError(act.error, 'corrective_action')} />
      <FormField label="Preventive action" name="preventive_action" as="textarea" value={f.preventive_action} onChange={set('preventive_action')} error={fieldError(act.error, 'preventive_action')} />
      <FormField label="Investigation notes" name="investigation_notes" as="textarea" value={f.investigation_notes} onChange={set('investigation_notes')} error={fieldError(act.error, 'investigation_notes')} />
      <Button variant="primary" loading={act.busy} onClick={save}>Save investigation</Button>
    </div>
  )
}

export default function IncidentDetailPage() {
  const { publicId } = useParams()
  const { can } = useFacility()
  const toast = useToast()
  const res = useFetch(`/incidents/${publicId}/`)
  const [dialog, setDialog] = useState(null)
  const [busy, setBusy] = useState(false)

  if (res.loading && !res.data) return <p className="muted">Loading…</p>
  if (res.error || !res.data) return <div className="alert alert-danger">Incident not found. <Link to="/incidents">Back</Link></div>
  const inc = res.data
  const manage = can('incident.manage')
  const open = inc.status !== 'CLOSED'
  const close = () => setDialog(null)
  const done = (msg) => () => { close(); toast.success(msg); res.reload() }
  const post = (a, body = {}) => api.post(`/incidents/${inc.public_id}/${a}/`, { ...body, row_version: inc.row_version })
  const simple = async (a, msg) => {
    setBusy(true)
    try { await post(a); toast.success(msg); res.reload() } catch (e) { toast.error(e?.response?.data?.error?.message || 'Action failed.') } finally { setBusy(false) }
  }
  const blockedByHold = inc.quarantine_open
  const blockedByRef = inc.reportable_to_regulator && !inc.regulator_report_reference

  return (
    <section>
      <div className="page-head">
        <h2>{inc.incident_number}</h2> <Chip kind="incident" value={inc.status} /> <Chip kind="severity" value={inc.severity} />
        <span className="spacer" />
        <div className="mt-actions">
          {manage && inc.status === 'REPORTED' && <Button variant="primary" loading={busy} onClick={() => simple('start-investigation', 'Investigation started.')}>Start investigation</Button>}
          {manage && inc.status === 'UNDER_INVESTIGATION' && <Button onClick={() => setDialog('actions')}>Actions taken</Button>}
          {manage && open && inc.quarantine_open && <Button onClick={() => setDialog('release')}>Release quarantine</Button>}
          {manage && open && !inc.has_work_order && <Button onClick={() => setDialog('wo')}>Create work order</Button>}
          {manage && open && <Button onClick={() => setDialog('reported')}>Mark reported to regulator</Button>}
          {manage && <Button onClick={() => setDialog('note')}>Add note</Button>}
          {manage && open && <Button variant="primary" onClick={() => setDialog('close')}>Close</Button>}
          <Link to="/incidents">Back to list</Link>
        </div>
      </div>

      {inc.quarantine_open && <div className="alert alert-warning">The equipment is quarantined (out of service) for this incident. Release the quarantine before closing.</div>}

      <Section title="Overview">
        <div className="mt-grid">
          <KV label="Equipment"><Link to={`/equipment/${inc.equipment.public_id}`}>{inc.equipment.asset_tag} · {inc.equipment.name}</Link></KV>
          <KV label="Type">{lbl(inc.incident_type)}</KV>
          <KV label="Occurred">{fmtDateTime(inc.occurred_at)}</KV>
          <KV label="Reported by">{fmt(inc.reported_by_name)}</KV>
          <KV label="Department">{fmt(inc.department?.name)}</KV>
          <KV label="Location">{fmt(inc.location?.name)}</KV>
          <KV label="Patient reference">{fmt(inc.patient_reference)}</KV>
          <KV label="Encounter reference">{fmt(inc.encounter_reference)}</KV>
          <KV label="Patient / staff affected">{inc.patient_affected ? 'Patient' : '—'} / {inc.staff_affected ? 'Staff' : '—'}</KV>
          <KV label="Investigator">{fmt(inc.investigated_by)}</KV>
          <KV label="Regulator report">{inc.reportable_to_regulator
            ? (inc.regulator_report_reference ? `${inc.regulator_report_reference} (${fmtDate(inc.regulator_reported_on)})` : 'Reportable, not yet recorded')
            : 'Not reportable'}</KV>
          <KV label="Work order">{inc.work_order
            ? <Link to={`/work-orders/${inc.work_order.public_id}`}>{inc.work_order.wo_number}</Link>
            : (inc.has_work_order ? 'Linked' : '—')}</KV>
          {inc.status === 'CLOSED' && <KV label="Closed">{fmtDateTime(inc.closed_at)} by {fmt(inc.closed_by)}</KV>}
        </div>
        <p><strong>What happened:</strong> {inc.description}</p>
        {inc.immediate_action && <p><strong>Immediate action:</strong> {inc.immediate_action}</p>}
        {inc.closure_notes && <p><strong>Closure notes:</strong> {inc.closure_notes}</p>}
      </Section>

      <Section title="Investigation">
        {manage && open
          ? <InvestigationForm inc={inc} reload={res.reload} />
          : (
            <div className="mt-grid">
              <KV label="Root cause">{fmt(inc.root_cause)}</KV>
              <KV label="Corrective action">{fmt(inc.corrective_action)}</KV>
              <KV label="Preventive action">{fmt(inc.preventive_action)}</KV>
              <KV label="Notes">{fmt(inc.investigation_notes)}</KV>
            </div>
          )}
      </Section>

      <Section title="Timeline">
        <Table rows={inc.events} empty="No events." rowKey="public_id"
          columns={[
            { key: 'created_at', header: 'When', render: (r) => fmtDateTime(r.created_at) },
            { key: 'event_type', header: 'Event', render: (r) => lbl(r.event_type) },
            { key: 'status', header: 'Status', render: (r) => (r.to_status && r.to_status !== r.from_status ? `${lbl(r.from_status)} → ${lbl(r.to_status)}` : '') },
            { key: 'note', header: 'Note', render: (r) => fmt(r.note) },
            { key: 'created_by', header: 'By', render: (r) => fmt(r.created_by) },
          ]} />
      </Section>

      <Section title="Documents">
        <DocumentsPanel entityType="equipment_incident" entityId={inc.public_id} viewPermission="incident.view" attachPermission="incident.add" />
      </Section>

      {dialog === 'actions' && (
        <ActionModal title="Record actions taken" submitLabel="Record" onClose={close} onDone={done('Actions recorded.')}
          fields={[{ name: 'corrective_action', label: 'Corrective action', as: 'textarea', required: true, initial: inc.corrective_action || '' }]}
          onSubmit={(v) => post('actions-taken', { corrective_action: nn(v.corrective_action.trim()) })} />
      )}
      {dialog === 'close' && (
        <ActionModal title="Close incident" submitLabel="Close incident" onClose={close} onDone={done('Incident closed.')}
          fields={[{ name: 'closure_notes', label: 'Closure notes', as: 'textarea', required: true }]}
          onSubmit={(v) => post('close', { closure_notes: v.closure_notes.trim() })}>
          {blockedByHold && <div className="alert alert-warning">The equipment is still quarantined. Release the quarantine first, or the server will refuse to close.</div>}
          {blockedByRef && <div className="alert alert-warning">This incident is reportable to the regulator. Use “Mark reported to regulator” to record the report reference first.</div>}
        </ActionModal>
      )}
      {dialog === 'reported' && (
        <ActionModal title="Mark reported to regulator" submitLabel="Record report" onClose={close} onDone={done('Report recorded.')}
          intro="This only records that a report was made. Nothing is sent to any regulator."
          fields={[
            { name: 'reference', label: 'Report reference', required: true, initial: inc.regulator_report_reference || '' },
            { name: 'reported_on', label: 'Reported on', type: 'date', required: true, initial: inc.regulator_reported_on || today() },
          ]}
          onSubmit={(v) => post('mark-reported', { reference: v.reference.trim(), reported_on: v.reported_on })} />
      )}
      {dialog === 'release' && (
        <ActionModal title="Release quarantine" submitLabel="Release" onClose={close} onDone={done('Quarantine released.')}
          intro="The equipment's state is recalculated; it returns to service only if no other hold is open."
          fields={[{ name: 'reason', label: 'Reason', as: 'textarea', required: true }]}
          onSubmit={(v) => post('release-quarantine', { reason: v.reason.trim() })} />
      )}
      {dialog === 'wo' && (
        <ActionModal title="Create work order" submitLabel="Create" onClose={close} onDone={done('Work order created.')}
          intro="Creates a corrective work order for this equipment (priority follows the severity). Only one can be linked."
          onSubmit={() => post('create-work-order')} />
      )}
      {dialog === 'note' && (
        <ActionModal title="Add note" submitLabel="Add" onClose={close} onDone={done('Note added.')}
          fields={[{ name: 'text', label: 'Note', as: 'textarea', required: true }]}
          onSubmit={(v) => api.post(`/incidents/${inc.public_id}/notes/`, { text: v.text.trim() })} />
      )}
    </section>
  )
}
