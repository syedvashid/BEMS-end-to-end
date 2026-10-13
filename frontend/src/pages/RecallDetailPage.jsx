import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import DocumentsPanel from '../components/DocumentsPanel'
import EquipmentPicker from '../components/EquipmentPicker'
import RecallFormModal from '../components/safety/RecallFormModal'
import {
  ActionModal, Chip, FilterSelect, api, clean, fieldError, fmt, fmtDate, fmtDateTime, lbl, nn, opt, useAction,
  useFetch, ErrorBox,
} from '../components/safety/shared'
import SimplePager from '../components/SimplePager'
import { Button, FormField, Modal, Table, useToast } from '../components/ui'
import { useFacility } from '../context/FacilityContext'

const KV = ({ label, children }) => (
  <div className="eq-kv"><span className="muted">{label}</span><span>{children}</span></div>
)
const Section = ({ title, children, right }) => (
  <div className="mt-section"><div className="page-head"><h3>{title}</h3><span className="spacer" />{right}</div>{children}</div>
)

function IdentifyModal({ notice, onClose, onDone }) {
  const [mode, setMode] = useState('ALL_OF_MODELS')
  const [serials, setSerials] = useState('')
  const [result, setResult] = useState(null)
  const act = useAction()
  const submit = async () => {
    const body = { mode, row_version: notice.row_version }
    if (mode === 'SERIAL_LIST') body.serial_numbers = serials.split(/[\s,;]+/).map((s) => s.trim()).filter(Boolean)
    const r = await act.run(() => api.post(`/recall-notices/${notice.public_id}/identify-units/`, body))
    if (r.ok) setResult(r.data.data)
  }
  return (
    <Modal title="Identify affected units" wide onClose={() => onDone(!!result)}
      footer={result
        ? <Button variant="primary" onClick={() => onDone(true)}>Close</Button>
        : <><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={act.busy} onClick={submit}>Identify</Button></>}>
      {!result && (
        <>
          <ErrorBox error={act.error} />
          <FormField label="How" name="mode" as="select" options={[
            { value: 'ALL_OF_MODELS', label: 'Every unit of the listed models' },
            { value: 'SERIAL_LIST', label: 'Only the serial numbers I paste' }]}
            value={mode} onChange={(e) => setMode(e.target.value)} />
          {mode === 'SERIAL_LIST' && (
            <FormField label="Serial numbers" name="serials" as="textarea" hint="One per line, or separated by commas. Case does not matter."
              value={serials} onChange={(e) => setSerials(e.target.value)} error={fieldError(act.error, 'serial_numbers')} />
          )}
          {notice.stop_use && <div className="alert alert-warning">This is a stop-use notice: commissioned units will be taken out of service.</div>}
        </>
      )}
      {result && (
        <div>
          <p><strong>{result.created}</strong> unit(s) added, <strong>{result.skipped}</strong> already listed, <strong>{result.holds_placed}</strong> stop-use hold(s) placed.</p>
          {result.unmatched_serials.length > 0 && (
            <div className="alert alert-warning">No equipment found for these serials: {result.unmatched_serials.join(', ')}</div>
          )}
          {result.warnings.length > 0 && <div className="alert alert-warning"><ul>{result.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></div>}
        </div>
      )}
    </Modal>
  )
}

function AddUnitModal({ notice, onClose, onDone }) {
  const [eq, setEq] = useState(null)
  const act = useAction()
  const submit = async () => {
    const r = await act.run(() => api.post(`/recall-notices/${notice.public_id}/units/`, { equipment: eq?.public_id ?? null }))
    if (r.ok) onDone(r.data.data)
  }
  return (
    <Modal title="Add unit" onClose={onClose}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={act.busy} onClick={submit}>Add</Button></>}>
      <ErrorBox error={act.error} />
      <EquipmentPicker label="Equipment" value={eq} onChange={setEq} error={fieldError(act.error, 'equipment')} />
    </Modal>
  )
}

export default function RecallDetailPage() {
  const { publicId } = useParams()
  const { can } = useFacility()
  const toast = useToast()
  const res = useFetch(`/recall-notices/${publicId}/`)
  const [uf, setUf] = useState({ status: '' })
  const [q, setQ] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const units = useFetch(`/recall-notices/${publicId}/units/`, clean({ ...uf, search, page, page_size: 20 }))
  const [dialog, setDialog] = useState(null)
  const [target, setTarget] = useState(null)

  if (res.loading && !res.data) return <p className="muted">Loading…</p>
  if (res.error || !res.data) return <div className="alert alert-danger">Notice not found. <Link to="/recall-notices">Back</Link></div>
  const n = res.data
  const manage = can('recall.manage') && n.status === 'OPEN'
  const c = n.counts || { units: 0, pending: 0, completed: 0, not_applicable: 0 }
  const resolved = c.completed + c.not_applicable
  const close = () => { setDialog(null); setTarget(null) }
  const refresh = () => { res.reload(); units.reload() }
  const done = (msg) => () => { close(); toast.success(msg); refresh() }
  const base = `/recall-notices/${n.public_id}`
  const makeWo = async (u) => {
    try { await api.post(`${base}/units/${u.public_id}/create-work-order/`, {}); toast.success('Work order created.'); refresh() }
    catch (e) { toast.error(e?.response?.data?.error?.message || 'Could not create the work order.') }
  }

  return (
    <section>
      <div className="page-head">
        <h2>{n.notice_number}</h2> <Chip kind="notice" value={n.status} /> <Chip kind="urgency" value={n.urgency} />
        <span className="spacer" />
        <div className="mt-actions">
          {manage && <Button onClick={() => setDialog('edit')}>Edit</Button>}
          {manage && <Button onClick={() => setDialog('identify')}>Identify units</Button>}
          {manage && <Button onClick={() => setDialog('add')}>Add unit</Button>}
          {manage && <Button variant="primary" onClick={() => setDialog('close')}>Close notice</Button>}
          {manage && <Button variant="danger" onClick={() => setDialog('cancel')}>Cancel notice</Button>}
          <Link to="/recall-notices">Back to list</Link>
        </div>
      </div>

      <Section title="Overview">
        <div className="mt-grid">
          <KV label="Title">{n.title}</KV>
          <KV label="Type">{lbl(n.notice_type)}</KV>
          <KV label="Source">{lbl(n.source)}</KV>
          <KV label="Issued by">{fmt(n.issued_by_vendor?.name)}</KV>
          <KV label="Reference">{fmt(n.reference_number)}</KV>
          <KV label="Issued / received">{fmtDate(n.issued_date)} / {fmtDate(n.received_date)}</KV>
          <KV label="Action">{lbl(n.action_type)}{n.stop_use ? ' · stop use' : ''}</KV>
          <KV label="Models">{n.models.map((m) => `${m.model_name} (${m.model_number})`).join(', ') || '—'}</KV>
          {n.status === 'CLOSED' && <KV label="Closed">{fmtDateTime(n.closed_at)} by {fmt(n.closed_by)}</KV>}
          {n.status === 'CANCELLED' && <KV label="Cancel reason">{fmt(n.cancel_reason)}</KV>}
        </div>
        <p>{n.description}</p>
        {n.required_action && <p><strong>Required action:</strong> {n.required_action}</p>}
        {n.close_notes && <p><strong>Close notes:</strong> {n.close_notes}</p>}
        <p>
          <progress value={resolved} max={Math.max(c.units, 1)} /> {resolved} of {c.units} unit(s) resolved
          {c.pending > 0 && ` · ${c.pending} pending`}
        </p>
      </Section>

      <Section title="Affected units">
        <div className="row">
          <FilterSelect label="Status" value={uf.status} onChange={(x) => { setUf({ status: x }); setPage(1) }} options={opt(['PENDING', 'ACTION_COMPLETED', 'NOT_APPLICABLE'])} />
          <FormField label="Search (tag, name, serial)" name="usearch" value={q} onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { setSearch(q.trim()); setPage(1) } }} />
          <Button size="sm" onClick={() => { setSearch(q.trim()); setPage(1) }}>Search</Button>
        </div>
        <Table rows={units.data?.results} loading={units.loading} empty="No affected units yet. Use “Identify units”."
          columns={[
            { key: 'asset_tag', header: 'Asset', render: (u) => <Link to={`/equipment/${u.equipment.public_id}`}>{u.equipment.asset_tag} · {u.equipment.name}</Link> },
            { key: 'serial', header: 'Serial', render: (u) => fmt(u.equipment.serial_number) },
            { key: 'loc', header: 'Location', render: (u) => fmt(u.equipment.current_location?.name) },
            { key: 'state', header: 'Equipment state', render: (u) => lbl(u.equipment.operational_state) },
            { key: 'identified_by', header: 'Found by', render: (u) => lbl(u.identified_by) },
            { key: 'status', header: 'Status', render: (u) => <Chip kind="unit" value={u.status} /> },
            { key: 'notes', header: 'Resolution', render: (u) => [u.resolution_notes, u.vendor_reference && `Ref ${u.vendor_reference}`].filter(Boolean).join(' · ') || '—' },
            { key: 'wo', header: 'Work order', render: (u) => (u.work_order ? <Link to={`/work-orders/${u.work_order.public_id}`}>{u.work_order.wo_number}</Link> : '—') },
            {
              key: 'act', header: '', render: (u) => (manage && u.status === 'PENDING' ? (
                <div className="row">
                  <Button size="sm" onClick={() => { setTarget(u); setDialog('resolve') }}>Resolve</Button>
                  {!u.work_order && <Button size="sm" onClick={() => makeWo(u)}>Create work order</Button>}
                </div>
              ) : ''),
            },
          ]} />
        <SimplePager page={page} count={units.data?.count} pageSize={20} onPage={setPage} />
      </Section>

      <Section title="Documents">
        <DocumentsPanel entityType="recall_notice" entityId={n.public_id} viewPermission="recall.view" attachPermission="recall.add" />
      </Section>

      {dialog === 'edit' && <RecallFormModal notice={n} onClose={close} onDone={() => { close(); toast.success('Notice updated.'); refresh() }} />}
      {dialog === 'identify' && <IdentifyModal notice={n} onClose={close} onDone={(changed) => { close(); if (changed) refresh() }} />}
      {dialog === 'add' && (
        <AddUnitModal notice={n} onClose={close}
          onDone={(r) => {
            close(); toast.success('Unit added.')
            if (r.warnings?.length) toast.error(r.warnings.join(' '))
            refresh()
          }} />
      )}
      {dialog === 'resolve' && target && (
        <ActionModal title={`Resolve ${target.equipment.asset_tag}`} submitLabel="Resolve" onClose={close} onDone={done('Unit resolved.')}
          intro="A resolved unit is final. Its stop-use hold, if any, is released."
          fields={[
            { name: 'status', label: 'Outcome', as: 'select', required: true, initial: 'ACTION_COMPLETED', options: [
              { value: 'ACTION_COMPLETED', label: 'Action completed' }, { value: 'NOT_APPLICABLE', label: 'Not applicable' }] },
            { name: 'notes', label: 'Notes', as: 'textarea' },
            { name: 'vendor_reference', label: 'Vendor reference' },
          ]}
          onSubmit={(v) => api.post(`${base}/units/${target.public_id}/resolve/`, {
            status: v.status, notes: nn(v.notes.trim()), vendor_reference: nn(v.vendor_reference.trim()) })} />
      )}
      {dialog === 'close' && (
        <ActionModal title="Close notice" submitLabel="Close notice" onClose={close} onDone={done('Notice closed.')}
          intro={c.pending > 0 ? `${c.pending} unit(s) are still pending. Resolve them before closing.` : 'All units are resolved.'}
          fields={[{ name: 'close_notes', label: 'Close notes', as: 'textarea', required: true }]}
          onSubmit={(v) => api.post(`${base}/close/`, { close_notes: v.close_notes.trim(), row_version: n.row_version })} />
      )}
      {dialog === 'cancel' && (
        <ActionModal title="Cancel notice" submitLabel="Cancel notice" danger onClose={close} onDone={done('Notice cancelled.')}
          intro="Every open stop-use hold of this notice is released. Units keep their status."
          fields={[{ name: 'reason', label: 'Reason', as: 'textarea', required: true }]}
          onSubmit={(v) => api.post(`${base}/cancel/`, { reason: v.reason.trim(), row_version: n.row_version })} />
      )}
    </section>
  )
}
