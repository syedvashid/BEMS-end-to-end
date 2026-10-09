import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import DocumentsPanel from '../components/DocumentsPanel'
import EquipmentPicker from '../components/EquipmentPicker'
import FormDialog from '../components/FormDialog'
import SimplePager from '../components/SimplePager'
import WorkOrderFormModal from '../components/WorkOrderFormModal'
import { OverdueBadge, PriorityPill, StatusPill } from '../components/WorkOrderBadges'
import { Button, FormField, Table, useToast } from '../components/ui'
import { useFacility } from '../context/FacilityContext'
import useFetch from '../hooks/useFetch'
import { fmt, fmtDateTime } from '../utils/equipment'
import {
  COVERAGE, COVERAGE_LABEL, PRIORITIES, PRIORITY_LABEL, TYPE_LABEL, apiError, errorText, fe, fromLocalInput, money,
  opts, outOfRange, toLocalInput, toNull,
} from '../utils/maintenance'
import '../styles/maintenance.css'

const KV = ({ label, children }) => (
  <div className="eq-kv"><span className="muted">{label}</span><span>{children}</span></div>
)
const Section = ({ title, children, right }) => (
  <div className="mt-section"><div className="page-head"><h3>{title}</h3><span className="spacer" />{right}</div>{children}</div>
)

// ------------------------------------------------------------------ details and costs (PATCH)
function DetailsForm({ wo, reload }) {
  const { can } = useFacility()
  const toast = useToast()
  const editable = wo.available_actions.includes('edit')
  const vendors = useFetch('/vendors/', { page_size: 100 }, editable && can('vendor.view'))
  const [f, setF] = useState(null)
  const [standby, setStandby] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  useEffect(() => {
    setF({
      priority: wo.priority, coverage_source: wo.coverage_source || '',
      service_provider_vendor: wo.service_provider_vendor?.public_id || '',
      vendor_call_reference: wo.vendor_call_reference || '', vendor_engineer_name: wo.vendor_engineer_name || '',
      vendor_visit_at: toLocalInput(wo.vendor_visit_at), labour_cost: wo.labour_cost ?? '', vendor_cost: wo.vendor_cost ?? '',
      root_cause: wo.root_cause || '', action_taken: wo.action_taken || '', signoff_name: wo.signoff_name || '',
      downtime_start: toLocalInput(wo.downtime_start), downtime_end: toLocalInput(wo.downtime_end),
    })
    setStandby(wo.standby_equipment ? { public_id: wo.standby_equipment.public_id, label: `${wo.standby_equipment.asset_tag} · ${wo.standby_equipment.name}` } : null)
  }, [wo.row_version, wo.public_id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!f) return null
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }))
  const save = async () => {
    setBusy(true); setErr(null)
    try {
      await api.patch(`/work-orders/${wo.public_id}/`, {
        priority: f.priority, coverage_source: toNull(f.coverage_source),
        service_provider_vendor: toNull(f.service_provider_vendor),
        vendor_call_reference: toNull(f.vendor_call_reference), vendor_engineer_name: toNull(f.vendor_engineer_name),
        vendor_visit_at: fromLocalInput(f.vendor_visit_at),
        labour_cost: toNull(f.labour_cost), vendor_cost: toNull(f.vendor_cost),
        root_cause: toNull(f.root_cause), action_taken: toNull(f.action_taken), signoff_name: toNull(f.signoff_name),
        standby_equipment: standby?.public_id ?? null,
        downtime_start: fromLocalInput(f.downtime_start), downtime_end: fromLocalInput(f.downtime_end),
        row_version: wo.row_version,
      })
      toast.success('Saved.'); reload()
    } catch (e) { setErr(apiError(e)) } finally { setBusy(false) }
  }
  const vend = vendors.data?.results || []

  if (!editable) {
    return (
      <div className="mt-grid">
        <KV label="Coverage">{wo.coverage_source || '—'}</KV>
        <KV label="Service provider">{fmt(wo.service_provider_vendor?.name)}</KV>
        <KV label="Vendor call ref.">{fmt(wo.vendor_call_reference)}</KV>
        <KV label="Vendor engineer">{fmt(wo.vendor_engineer_name)}</KV>
        <KV label="Labour cost">{money(wo.labour_cost)}</KV>
        <KV label="Vendor cost">{money(wo.vendor_cost)}</KV>
        <KV label="Root cause">{fmt(wo.root_cause)}</KV>
        <KV label="Action taken">{fmt(wo.action_taken)}</KV>
        <KV label="Standby equipment">{wo.standby_equipment ? `${wo.standby_equipment.asset_tag} · ${wo.standby_equipment.name}` : '—'}</KV>
        <KV label="Sign-off">{fmt(wo.signoff_name)}</KV>
      </div>
    )
  }
  return (
    <div>
      {err && <div className="alert alert-danger">{errorText(err)}</div>}
      <div className="mt-grid">
        <FormField label="Priority" name="priority" as="select" options={opts(PRIORITIES, PRIORITY_LABEL)} value={f.priority} onChange={set('priority')} error={fe(err, 'priority')} />
        <FormField label="Coverage source" name="coverage_source" as="select" options={opts(COVERAGE, COVERAGE_LABEL, '— not set —')} value={f.coverage_source} onChange={set('coverage_source')} error={fe(err, 'coverage_source')} />
        {can('vendor.view') && (
          <FormField label="Service provider" name="service_provider_vendor" as="select"
            options={opts(vend.map((v) => v.public_id), Object.fromEntries(vend.map((v) => [v.public_id, v.name])), '— none —')}
            value={f.service_provider_vendor} onChange={set('service_provider_vendor')} error={fe(err, 'service_provider_vendor')} />
        )}
        <FormField label="Vendor call reference" name="vendor_call_reference" value={f.vendor_call_reference} onChange={set('vendor_call_reference')} error={fe(err, 'vendor_call_reference')} />
        <FormField label="Vendor engineer" name="vendor_engineer_name" value={f.vendor_engineer_name} onChange={set('vendor_engineer_name')} error={fe(err, 'vendor_engineer_name')} />
        <FormField label="Vendor visit" name="vendor_visit_at" type="datetime-local" value={f.vendor_visit_at} onChange={set('vendor_visit_at')} error={fe(err, 'vendor_visit_at')} />
        <FormField label="Labour cost (INR)" name="labour_cost" type="number" value={f.labour_cost} onChange={set('labour_cost')} error={fe(err, 'labour_cost')} />
        <FormField label="Vendor cost (INR)" name="vendor_cost" type="number" value={f.vendor_cost} onChange={set('vendor_cost')} error={fe(err, 'vendor_cost')} />
        <FormField label="Downtime start" name="downtime_start" type="datetime-local" value={f.downtime_start} onChange={set('downtime_start')} error={fe(err, 'downtime_start')} />
        <FormField label="Downtime end" name="downtime_end" type="datetime-local" value={f.downtime_end} onChange={set('downtime_end')} error={fe(err, 'downtime_end')} />
        <FormField label="Sign-off (accepted by)" name="signoff_name" value={f.signoff_name} onChange={set('signoff_name')} error={fe(err, 'signoff_name')} />
      </div>
      <FormField label="Root cause" name="root_cause" as="textarea" value={f.root_cause} onChange={set('root_cause')} error={fe(err, 'root_cause')} />
      <FormField label="Action taken" name="action_taken" as="textarea" value={f.action_taken} onChange={set('action_taken')} error={fe(err, 'action_taken')} />
      <EquipmentPicker label="Standby equipment (optional)" value={standby} onChange={setStandby} error={fe(err, 'standby_equipment')} excludeId={wo.equipment.public_id} />
      <Button variant="primary" loading={busy} onClick={save}>Save details</Button>
    </div>
  )
}

// ------------------------------------------------------------------ checklist
function ChecklistSection({ wo, reload, onSuggest }) {
  const toast = useToast()
  const canEdit = wo.available_actions.includes('checklist')
  const [rows, setRows] = useState([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  useEffect(() => {
    setRows(wo.checklist_items.map((i) => ({ ...i, measured_value: i.measured_value ?? '', result: i.result || '', remarks: i.remarks || '' })))
  }, [wo.checklist_items])
  if (!rows.length) return <p className="muted">This work order has no checklist.</p>
  const upd = (seq, k, v) => setRows((rs) => rs.map((r) => (r.sequence === seq ? { ...r, [k]: v } : r)))
  const save = async () => {
    setBusy(true); setErr(null)
    try {
      await api.put(`/work-orders/${wo.public_id}/checklist/`, {
        items: rows.map((r) => ({ sequence: r.sequence, result: toNull(r.result), measured_value: toNull(r.measured_value), remarks: toNull(r.remarks) })),
      })
      toast.success('Checklist saved.'); reload()
    } catch (e) { setErr(apiError(e)) } finally { setBusy(false) }
  }
  const failed = wo.checklist_items.filter((i) => i.result === 'FAIL')
  return (
    <div>
      {err && <div className="alert alert-danger">{errorText(err)}{fe(err, 'items') ? ` ${fe(err, 'items')}` : ''}</div>}
      {failed.length > 0 && onSuggest && (
        <div className="alert alert-warning">
          {failed.length} checklist item(s) failed.{' '}
          <button type="button" className="link" onClick={() => onSuggest(failed)}>Create a corrective work order</button>
        </div>
      )}
      <table className="table">
        <thead><tr><th>#</th><th>Item</th><th>Result</th><th>Measured</th><th>Range</th><th>Remarks</th></tr></thead>
        <tbody>
          {rows.map((r) => {
            const bad = r.result === 'FAIL' || outOfRange(r)
            return (
              <tr key={r.sequence} className={bad ? 'mt-fail' : ''}>
                <td>{r.sequence}</td><td>{r.item_text}</td>
                <td>
                  {canEdit
                    ? <select value={r.result} onChange={(e) => upd(r.sequence, 'result', e.target.value)}>
                      <option value="">—</option><option value="PASS">Pass</option><option value="FAIL">Fail</option><option value="NA">N/A</option>
                    </select>
                    : (r.result || '—')}
                </td>
                <td>{r.item_type === 'MEASUREMENT'
                  ? (canEdit ? <input type="number" step="any" value={r.measured_value} onChange={(e) => upd(r.sequence, 'measured_value', e.target.value)} style={{ width: 90 }} /> : fmt(r.measured_value))
                  : '—'}{r.unit ? ` ${r.unit}` : ''}</td>
                <td>{r.item_type === 'MEASUREMENT' ? `${r.min_value ?? '…'} – ${r.max_value ?? '…'}` : ''}</td>
                <td>{canEdit ? <input value={r.remarks} onChange={(e) => upd(r.sequence, 'remarks', e.target.value)} /> : fmt(r.remarks)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="muted">A measurement outside its range is stored as Fail by the server.</p>
      {canEdit && <Button variant="primary" loading={busy} onClick={save}>Save checklist</Button>}
    </div>
  )
}

// ------------------------------------------------------------------ parts
function PartsSection({ wo, reload }) {
  const toast = useToast()
  const canIssue = wo.available_actions.includes('parts') && wo.available_actions.includes('note')
  const parts = useFetch(`/work-orders/${wo.public_id}/parts/`, { page_size: 100 })
  const catalog = useFetch('/spare-parts/', { page_size: 100 }, canIssue)
  const [sel, setSel] = useState('')
  const [qty, setQty] = useState('')
  const [cost, setCost] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const list = catalog.data?.results || []
  const picked = list.find((p) => p.public_id === sel)

  const refresh = () => { parts.reload(); catalog.reload(); reload() }
  const issue = async () => {
    setBusy(true); setErr(null)
    try {
      await api.post(`/work-orders/${wo.public_id}/parts/`, { spare_part: sel || null, quantity: qty, unit_cost: toNull(cost) })
      setQty(''); setCost(''); toast.success('Part issued.'); refresh()
    } catch (e) { const a = apiError(e); setErr(a); if (a.code === 'insufficient_stock') catalog.reload() } finally { setBusy(false) }
  }
  const ret = async (row) => {
    try { await api.post(`/work-orders/${wo.public_id}/parts/${row.public_id}/return/`, {}); toast.success('Part returned.'); refresh() }
    catch (e) { toast.error(errorText(apiError(e))) }
  }
  return (
    <div>
      {canIssue && (
        <div className="mt-row">
          <FormField label="Spare part" name="spare_part" as="select"
            options={opts(list.map((p) => p.public_id), Object.fromEntries(list.map((p) => [p.public_id, `${p.part_code} · ${p.name} (on hand ${p.on_hand_quantity})`])), '— select —')}
            value={sel} onChange={(e) => setSel(e.target.value)} error={fe(err, 'spare_part')} />
          <FormField label="Quantity" name="quantity" type="number" value={qty} onChange={(e) => setQty(e.target.value)} error={fe(err, 'quantity')}
            hint={picked ? `On hand: ${picked.on_hand_quantity} ${picked.unit}` : undefined} />
          <FormField label="Unit cost (optional)" name="unit_cost" type="number" value={cost} onChange={(e) => setCost(e.target.value)} error={fe(err, 'unit_cost')}
            hint={picked?.standard_unit_cost ? `Standard: ${picked.standard_unit_cost}` : undefined} />
          <Button variant="primary" loading={busy} onClick={issue}>Issue</Button>
        </div>
      )}
      {err && !Object.keys(err.details || {}).filter((k) => k !== 'available').length && <div className="alert alert-danger">{errorText(err)}{err.code === 'insufficient_stock' ? ' Set the work order to “Waiting for parts” until stock arrives.' : ''}</div>}
      <Table rows={parts.data?.results} loading={parts.loading} empty="No parts used."
        columns={[
          { key: 'created_at', header: 'When', render: (r) => fmtDateTime(r.created_at) },
          { key: 'part', header: 'Part', render: (r) => `${r.spare_part.part_code} · ${r.spare_part.name}` },
          { key: 'entry_type', header: 'Type' },
          { key: 'quantity', header: 'Qty' },
          { key: 'unit_cost', header: 'Unit cost', render: (r) => money(r.unit_cost) },
          { key: 'created_by', header: 'By', render: (r) => fmt(r.created_by) },
          { key: 'act', header: '', render: (r) => (canIssue && r.entry_type === 'CONSUMPTION' && Number(r.returnable) > 0
            ? <Button size="sm" onClick={() => ret(r)}>Return {r.returnable}</Button> : '') },
        ]} />
      <SimplePager page={1} count={parts.data?.count} pageSize={100} onPage={() => {}} />
    </div>
  )
}

// ------------------------------------------------------------------ timeline
function Timeline({ wo, reload }) {
  const [page, setPage] = useState(1)
  const ev = useFetch(`/work-orders/${wo.public_id}/events/`, { page, page_size: 20 })
  const [note, setNote] = useState('')
  const [err, setErr] = useState(null)
  const add = async () => {
    setErr(null)
    try { await api.post(`/work-orders/${wo.public_id}/notes/`, { note }); setNote(''); ev.reload(); reload() }
    catch (e) { setErr(apiError(e)) }
  }
  return (
    <div>
      {wo.available_actions.includes('note') && (
        <div className="mt-row">
          <FormField label="Add a note" name="note" value={note} onChange={(e) => setNote(e.target.value)} error={fe(err, 'note')} />
          <Button onClick={add}>Add note</Button>
        </div>
      )}
      <Table rows={ev.data?.results} loading={ev.loading} empty="No events."
        columns={[
          { key: 'created_at', header: 'When', render: (r) => fmtDateTime(r.created_at) },
          { key: 'event_type', header: 'Event', render: (r) => r.event_type.replace('_', ' ') },
          { key: 'status', header: 'Status', render: (r) => (r.to_status && r.to_status !== r.from_status ? `${r.from_status || '—'} → ${r.to_status}` : '') },
          { key: 'note', header: 'Note', render: (r) => fmt(r.note) },
          { key: 'created_by', header: 'By' },
        ]} />
      <SimplePager page={page} count={ev.data?.count} pageSize={20} onPage={setPage} />
    </div>
  )
}

// ------------------------------------------------------------------ page
export default function WorkOrderDetailPage() {
  const { publicId } = useParams()
  const toast = useToast()
  const res = useFetch(`/work-orders/${publicId}/`)
  const assignees = useFetch('/work-orders/assignees/', {}, !!res.data?.available_actions?.includes('assign'))
  const [dialog, setDialog] = useState(null)
  const [corrective, setCorrective] = useState(null)
  const [busy, setBusy] = useState(false)

  if (res.loading && !res.data) return <p className="muted">Loading…</p>
  if (res.error || !res.data) return <div className="alert alert-danger">Work order not found. <Link to="/work-orders">Back</Link></div>
  const wo = res.data
  const acts = wo.available_actions
  const close = () => setDialog(null)
  const url = (a) => `/work-orders/${wo.public_id}/${a}/`
  const post = (a, body = {}) => api.post(url(a), { ...body, row_version: wo.row_version })
  const done = (msg) => () => { close(); toast.success(msg); res.reload() }
  const simple = async (a, msg) => {
    setBusy(true)
    try { await post(a); toast.success(msg); res.reload() } catch (e) { toast.error(errorText(apiError(e))) } finally { setBusy(false) }
  }
  const people = assignees.data?.results || []

  const suggest = (failed) => setCorrective({
    equipment: { public_id: wo.equipment.public_id, label: `${wo.equipment.asset_tag} · ${wo.equipment.name}` },
    parent_work_order: wo.public_id, work_order_type: 'CORRECTIVE',
    problem_description: `Failed during ${wo.wo_number}: ${failed.map((i) => i.item_text).join('; ')}`,
  })
  const isPm = wo.work_order_type === 'PREVENTIVE' && wo.maintenance_plan

  return (
    <section>
      <div className="page-head">
        <h2>{wo.wo_number}</h2> <StatusPill status={wo.status} /> <PriorityPill priority={wo.priority} /> <OverdueBadge show={wo.is_overdue} />
        <span className="spacer" />
        <div className="mt-actions">
          {acts.includes('assign') && <Button onClick={() => setDialog('assign')}>{wo.status === 'ASSIGNED' ? 'Re-assign' : 'Assign'}</Button>}
          {acts.includes('start') && <Button variant="primary" loading={busy} onClick={() => simple('start', 'Work started.')}>Start</Button>}
          {acts.includes('waiting_parts') && <Button onClick={() => setDialog('waiting')}>Waiting for parts</Button>}
          {acts.includes('resume') && <Button variant="primary" loading={busy} onClick={() => simple('resume', 'Work resumed.')}>Resume</Button>}
          {acts.includes('complete') && <Button variant="primary" onClick={() => setDialog('complete')}>Complete</Button>}
          {acts.includes('close') && <Button variant="primary" onClick={() => setDialog('close')}>Close</Button>}
          {acts.includes('cancel') && <Button variant="danger" onClick={() => setDialog('cancel')}>Cancel</Button>}
          <Link to="/work-orders">Back to list</Link>
        </div>
      </div>

      <Section title="Overview">
        <div className="mt-grid">
          <KV label="Type">{TYPE_LABEL[wo.work_order_type]}</KV>
          <KV label="Equipment"><Link to={`/equipment/${wo.equipment.public_id}`}>{wo.equipment.asset_tag} · {wo.equipment.name}</Link></KV>
          <KV label="Equipment state">{fmt(wo.equipment.operational_state)}</KV>
          <KV label="Location">{fmt(wo.equipment.current_location?.name)}</KV>
          <KV label="Due">{fmt(wo.due_date)}</KV>
          <KV label="Assigned to">{fmt(wo.assigned_to?.full_name)}</KV>
          <KV label="Reported">{fmtDateTime(wo.reported_at)}{wo.reported_by_name ? ` by ${wo.reported_by_name}` : ''}</KV>
          <KV label="Reporting department">{fmt(wo.reported_by_department?.name)}</KV>
          <KV label="Equipment unusable">{wo.equipment_unusable ? 'Yes' : 'No'}</KV>
          <KV label="Plan">{fmt(wo.maintenance_plan?.name)}</KV>
          <KV label="Parent">{wo.parent_work_order ? <Link to="/work-orders">{wo.parent_work_order.wo_number}</Link> : '—'}</KV>
          <KV label="Started">{fmt(wo.started_at && fmtDateTime(wo.started_at))}</KV>
          <KV label="Completed">{fmt(wo.completed_at && fmtDateTime(wo.completed_at))}</KV>
          <KV label="Downtime">{wo.downtime_start ? `${fmtDateTime(wo.downtime_start)} → ${wo.downtime_end ? fmtDateTime(wo.downtime_end) : 'ongoing'}` : '—'}</KV>
          {wo.status === 'CLOSED' && <KV label="Closed">{fmtDateTime(wo.closed_at)} by {fmt(wo.closed_by)} · sign-off {fmt(wo.signoff_name)}</KV>}
          {wo.status === 'CANCELLED' && <KV label="Cancel reason">{fmt(wo.cancel_reason)}</KV>}
        </div>
        {wo.problem_description && <p><strong>Problem:</strong> {wo.problem_description}</p>}
        {wo.holds.some((h) => !h.released_at) && (
          <div className="alert alert-warning">Open holds: {wo.holds.filter((h) => !h.released_at).map((h) => h.hold_type.replace('_', ' ').toLowerCase()).join(', ')} — released when this work order is completed or cancelled.</div>
        )}
      </Section>

      <Section title="Details and costs"
        right={<span className="muted">Parts {money(wo.parts_cost)} · Total {money(wo.total_cost)} INR</span>}>
        <DetailsForm wo={wo} reload={res.reload} />
      </Section>
      <Section title="Checklist"><ChecklistSection wo={wo} reload={res.reload} onSuggest={acts.includes('note') || acts.includes('edit') ? suggest : null} /></Section>
      <Section title="Parts"><PartsSection wo={wo} reload={res.reload} /></Section>
      <Section title="Timeline"><Timeline wo={wo} reload={res.reload} /></Section>
      <Section title="Documents">
        <DocumentsPanel entityType="work_order" entityId={wo.public_id} viewPermission="work_order.view" attachPermission="work_order.change" />
      </Section>

      {dialog === 'assign' && (
        <FormDialog title="Assign work order" submitLabel="Assign" onClose={close}
          fields={[
            { name: 'assigned_to', label: 'Assign to', as: 'select', required: true, options: opts(people.map((p) => p.public_id), Object.fromEntries(people.map((p) => [p.public_id, p.full_name])), '— select —') },
            { name: 'note', label: 'Note' },
          ]}
          onSubmit={async (v) => { await post('assign', { assigned_to: toNull(v.assigned_to), note: toNull(v.note) }); done('Assigned.')() }} />
      )}
      {dialog === 'waiting' && (
        <FormDialog title="Waiting for parts" onClose={close}
          fields={[{ name: 'reason', label: 'What is needed?', as: 'textarea', required: true }]}
          onSubmit={async (v) => { await post('waiting-parts', { reason: v.reason }); done('Status updated.')() }} />
      )}
      {dialog === 'complete' && (
        <FormDialog title="Complete work order" submitLabel="Complete" onClose={close}
          intro="Every checklist item needs a result. Holds of this work order are released."
          fields={[
            { name: 'action_taken', label: 'Action taken', as: 'textarea', initial: wo.action_taken || '', required: wo.work_order_type !== 'PREVENTIVE' },
            { name: 'root_cause', label: 'Root cause', as: 'textarea', initial: wo.root_cause || '' },
            { name: 'labour_cost', label: 'Labour cost (INR)', type: 'number', initial: wo.labour_cost ?? '' },
            { name: 'vendor_cost', label: 'Vendor cost (INR)', type: 'number', initial: wo.vendor_cost ?? '' },
            { name: 'downtime_end', label: 'Downtime end', type: 'datetime-local', hint: 'Breakdowns default to now', initial: toLocalInput(wo.downtime_end) },
          ]}
          onSubmit={async (v) => {
            await post('complete', {
              action_taken: toNull(v.action_taken), root_cause: toNull(v.root_cause), labour_cost: toNull(v.labour_cost),
              vendor_cost: toNull(v.vendor_cost), downtime_end: fromLocalInput(v.downtime_end),
            })
            done('Work order completed.')()
          }} />
      )}
      {dialog === 'close' && (
        <FormDialog title="Close work order" submitLabel="Close" onClose={close}
          fields={[{ name: 'signoff_name', label: 'Accepted by (user department person)', required: true, initial: wo.signoff_name || '' }]}
          onSubmit={async (v) => { await post('close', { signoff_name: v.signoff_name }); done('Work order closed.')() }} />
      )}
      {dialog === 'cancel' && (
        <FormDialog title="Cancel work order" submitLabel="Cancel work order" danger onClose={close}
          intro={isPm ? 'This is a preventive work order: enter the new next due date for its plan.' : undefined}
          fields={[
            { name: 'reason', label: 'Reason', as: 'textarea', required: true },
            ...(isPm ? [{ name: 'next_due_date', label: 'New next due date', type: 'date', required: true }] : []),
          ]}
          onSubmit={async (v) => { await post('cancel', { reason: v.reason, next_due_date: toNull(v.next_due_date) }); done('Work order cancelled.')() }} />
      )}
      {corrective && (
        <WorkOrderFormModal preset={corrective} onClose={() => setCorrective(null)}
          onDone={(n) => { setCorrective(null); toast.success(`Created ${n.wo_number}`) }} />
      )}
    </section>
  )
}
