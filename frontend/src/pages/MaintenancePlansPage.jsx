import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { Button, FormField, Modal, Table, useToast } from '../components/ui'
import EquipmentPicker from '../components/EquipmentPicker'
import SimplePager from '../components/SimplePager'
import { useFacility } from '../context/FacilityContext'
import useFetch from '../hooks/useFetch'
import { PRIORITIES, PRIORITY_LABEL, apiError, errorText, fe, opts, toNull } from '../utils/maintenance'
import '../styles/maintenance.css'

const FREQ = { DAYS: 'Days', MONTHS: 'Months' }

function PlanForm({ plan, onClose, onSaved }) {
  const { can } = useFacility()
  const templates = useFetch('/checklist-templates/', { page_size: 100 })
  const people = useFetch('/work-orders/assignees/', {}, can('work_order.assign'))
  const [equipment, setEquipment] = useState(plan ? { public_id: plan.equipment.public_id, label: `${plan.equipment.asset_tag} · ${plan.equipment.name}` } : null)
  const [f, setF] = useState({
    name: plan?.name || '', frequency_type: plan?.frequency_type || 'DAYS', frequency_value: plan?.frequency_value ?? '',
    lead_days: plan?.lead_days ?? 7, priority: plan?.priority || 'MEDIUM', checklist_template: plan?.checklist_template?.public_id || '',
    default_assignee: plan?.default_assignee?.public_id || '', start_date: plan?.start_date || '',
    last_performed_date: plan?.last_performed_date || '', next_due_date: plan?.next_due_date || '', notes: plan?.notes || '',
  })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }))
  const save = async () => {
    setBusy(true); setErr(null)
    const body = {
      name: f.name, equipment: equipment?.public_id ?? null, frequency_type: f.frequency_type, frequency_value: toNull(f.frequency_value),
      lead_days: toNull(f.lead_days), priority: f.priority, checklist_template: toNull(f.checklist_template),
      start_date: toNull(f.start_date), last_performed_date: toNull(f.last_performed_date), next_due_date: toNull(f.next_due_date), notes: toNull(f.notes),
    }
    if (can('work_order.assign')) body.default_assignee = toNull(f.default_assignee)
    try {
      if (plan) await api.patch(`/maintenance-plans/${plan.public_id}/`, { ...body, row_version: plan.row_version })
      else await api.post('/maintenance-plans/', body)
      onSaved()
    } catch (e) { setErr(apiError(e)) } finally { setBusy(false) }
  }
  const t = templates.data?.results || []
  const p = people.data?.results || []
  return (
    <Modal wide title={plan ? 'Edit maintenance plan' : 'New maintenance plan'} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Close</Button><Button variant="primary" loading={busy} onClick={save}>Save</Button></>}>
      {err && !Object.keys(err.details || {}).length && <div className="alert alert-danger">{errorText(err)}</div>}
      {plan ? <p><strong>{equipment.label}</strong></p> : <EquipmentPicker value={equipment} onChange={setEquipment} required error={fe(err, 'equipment')} />}
      <FormField label="Plan name" name="name" required value={f.name} onChange={set('name')} error={fe(err, 'name')} />
      <div className="mt-row">
        <FormField label="Every" name="frequency_value" type="number" required value={f.frequency_value} onChange={set('frequency_value')} error={fe(err, 'frequency_value')} />
        <FormField label="Unit" name="frequency_type" as="select" options={opts(Object.keys(FREQ), FREQ)} value={f.frequency_type} onChange={set('frequency_type')} error={fe(err, 'frequency_type')} />
        <FormField label="Create work order days ahead" name="lead_days" type="number" value={f.lead_days} onChange={set('lead_days')} error={fe(err, 'lead_days')} />
        <FormField label="Priority" name="priority" as="select" options={opts(PRIORITIES, PRIORITY_LABEL)} value={f.priority} onChange={set('priority')} error={fe(err, 'priority')} />
      </div>
      <div className="mt-row">
        <FormField label="Start date" name="start_date" type="date" value={f.start_date} onChange={set('start_date')} error={fe(err, 'start_date')} />
        <FormField label="Last performed" name="last_performed_date" type="date" value={f.last_performed_date} onChange={set('last_performed_date')} error={fe(err, 'last_performed_date')} />
        <FormField label="Next due" name="next_due_date" type="date" hint="Leave empty to calculate" value={f.next_due_date} onChange={set('next_due_date')} error={fe(err, 'next_due_date')} />
      </div>
      <FormField label="Checklist template" name="checklist_template" as="select" value={f.checklist_template} onChange={set('checklist_template')}
        options={opts(t.map((x) => x.public_id), Object.fromEntries(t.map((x) => [x.public_id, x.name])), '— none —')} error={fe(err, 'checklist_template')} />
      {can('work_order.assign') && (
        <FormField label="Default assignee" name="default_assignee" as="select" value={f.default_assignee} onChange={set('default_assignee')}
          options={opts(p.map((x) => x.public_id), Object.fromEntries(p.map((x) => [x.public_id, x.full_name])), '— none —')} error={fe(err, 'default_assignee')} />
      )}
      <FormField label="Notes" name="notes" as="textarea" value={f.notes} onChange={set('notes')} error={fe(err, 'notes')} />
    </Modal>
  )
}

function GenerateForm({ onClose, onDone }) {
  const models = useFetch('/equipment-models/', { page_size: 100 })
  const cats = useFetch('/equipment-categories/', { page_size: 100 })
  const templates = useFetch('/checklist-templates/', { page_size: 100 })
  const [scope, setScope] = useState('equipment_model')
  const [f, setF] = useState({ target: '', name: '', frequency_type: '', frequency_value: '', lead_days: 7, priority: 'MEDIUM', checklist_template: '', last_performed_date: '', start_date: '' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [result, setResult] = useState(null)
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }))
  const run = async () => {
    setBusy(true); setErr(null)
    try {
      const r = await api.post('/maintenance-plans/generate/', {
        [scope]: toNull(f.target), name: f.name, frequency_type: toNull(f.frequency_type), frequency_value: toNull(f.frequency_value),
        lead_days: toNull(f.lead_days), priority: f.priority, checklist_template: toNull(f.checklist_template),
        last_performed_date: toNull(f.last_performed_date), start_date: toNull(f.start_date),
      })
      setResult(r.data); onDone()
    } catch (e) { setErr(apiError(e)) } finally { setBusy(false) }
  }
  const list = (scope === 'equipment_model' ? models : cats).data?.results || []
  const t = templates.data?.results || []
  return (
    <Modal title="Generate plans" onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Close</Button><Button variant="primary" loading={busy} onClick={run}>Generate</Button></>}>
      <p className="muted">Creates one plan for every commissioned unit of the model or category that has no active plan with this name. Without a frequency, the effective PM interval (days) of the unit is used; units without one are skipped.</p>
      {err && <div className="alert alert-danger">{errorText(err)}{fe(err, 'scope') ? ` ${fe(err, 'scope')}` : ''}</div>}
      {result && <div className="alert alert-success">Created {result.created}; skipped {result.skipped_existing} (already planned) and {result.skipped_no_interval} (no interval).</div>}
      <FormField label="Generate for" name="scope" as="select" options={[{ value: 'equipment_model', label: 'Equipment model' }, { value: 'category', label: 'Equipment category' }]}
        value={scope} onChange={(e) => { setScope(e.target.value); setF((s) => ({ ...s, target: '' })) }} />
      <FormField label={scope === 'category' ? 'Category' : 'Model'} name="target" as="select" required value={f.target} onChange={set('target')}
        options={opts(list.map((x) => x.public_id), Object.fromEntries(list.map((x) => [x.public_id, x.model_name || x.name])), '— select —')} />
      <FormField label="Plan name" name="name" required value={f.name} onChange={set('name')} error={fe(err, 'name')} />
      <div className="mt-row">
        <FormField label="Every (optional)" name="frequency_value" type="number" value={f.frequency_value} onChange={set('frequency_value')} error={fe(err, 'frequency_value')} />
        <FormField label="Unit" name="frequency_type" as="select" options={opts(Object.keys(FREQ), FREQ, '—')} value={f.frequency_type} onChange={set('frequency_type')} />
        <FormField label="Days ahead" name="lead_days" type="number" value={f.lead_days} onChange={set('lead_days')} />
        <FormField label="Priority" name="priority" as="select" options={opts(PRIORITIES, PRIORITY_LABEL)} value={f.priority} onChange={set('priority')} />
      </div>
      <div className="mt-row">
        <FormField label="Last performed" name="last_performed_date" type="date" value={f.last_performed_date} onChange={set('last_performed_date')} />
        <FormField label="Start date" name="start_date" type="date" value={f.start_date} onChange={set('start_date')} />
      </div>
      <FormField label="Checklist template" name="checklist_template" as="select" value={f.checklist_template} onChange={set('checklist_template')}
        options={opts(t.map((x) => x.public_id), Object.fromEntries(t.map((x) => [x.public_id, x.name])), '— none —')} />
    </Modal>
  )
}

export default function MaintenancePlansPage() {
  const { can } = useFacility()
  const toast = useToast()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [overdue, setOverdue] = useState('')
  const [modal, setModal] = useState(null)   // 'new' | 'generate' | plan object
  const res = useFetch('/maintenance-plans/', { page, page_size: 20, ...(search ? { search } : {}), ...(overdue ? { overdue } : {}) })
  const open = (row) => setModal(row)
  const remove = async (row) => {
    if (!window.confirm(`Delete plan "${row.name}"?`)) return
    try { await api.delete(`/maintenance-plans/${row.public_id}/`, { params: { row_version: row.row_version } }); toast.success('Deleted.'); res.reload() }
    catch (e) { toast.error(errorText(apiError(e))) }
  }
  return (
    <section>
      <div className="page-head"><h2>Maintenance plans</h2><span className="spacer" />
        {can('maintenance_plan.add') && <Button onClick={() => setModal('generate')}>Generate plans</Button>}
        {can('maintenance_plan.add') && <Button variant="primary" onClick={() => setModal('new')}>New plan</Button>}
      </div>
      <div className="mt-toolbar">
        <FormField label="Search" name="search" value={search} onChange={(e) => { setPage(1); setSearch(e.target.value) }} />
        <FormField label="Overdue" name="overdue" as="select" options={[{ value: '', label: 'All' }, { value: 'true', label: 'Overdue only' }]} value={overdue} onChange={(e) => { setPage(1); setOverdue(e.target.value) }} />
      </div>
      <Table rows={res.data?.results} loading={res.loading} empty="No plans."
        columns={[
          { key: 'equipment', header: 'Equipment', render: (p) => <Link to={`/equipment/${p.equipment.public_id}`}>{p.equipment.asset_tag} · {p.equipment.name}</Link> },
          { key: 'name', header: 'Plan' },
          { key: 'freq', header: 'Every', render: (p) => `${p.frequency_value} ${FREQ[p.frequency_type].toLowerCase()}` },
          { key: 'next_due_date', header: 'Next due' },
          { key: 'last', header: 'Last done', render: (p) => p.last_performed_date || '—' },
          { key: 'template', header: 'Checklist', render: (p) => p.checklist_template?.name || '—' },
          { key: 'assignee', header: 'Default assignee', render: (p) => p.default_assignee?.full_name || '—' },
          { key: 'act', header: '', render: (p) => (
            <div className="mt-actions">
              {can('maintenance_plan.change') && <Button size="sm" onClick={() => open(p)}>Edit</Button>}
              {can('maintenance_plan.delete') && <Button size="sm" variant="danger" onClick={() => remove(p)}>Delete</Button>}
            </div>) },
        ]} />
      <SimplePager page={page} count={res.data?.count} pageSize={20} onPage={setPage} />
      {modal && modal !== 'generate' && (
        <PlanForm plan={modal === 'new' ? null : modal} onClose={() => setModal(null)}
          onSaved={() => { setModal(null); toast.success('Saved.'); res.reload() }} />
      )}
      {modal === 'generate' && <GenerateForm onClose={() => setModal(null)} onDone={() => res.reload()} />}
    </section>
  )
}
