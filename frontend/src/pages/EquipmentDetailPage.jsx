import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import DocumentsPanel from '../components/DocumentsPanel'
import {
  CommissionDialog, InstallDialog, MoveDialog, RejectDialog, StateDialog,
} from '../components/EquipmentActionDialogs'
import { StageBadge, StateBadge } from '../components/EquipmentBadges'
import SimplePager from '../components/SimplePager'
import { Button, Table, useToast } from '../components/ui'
import { EQUIPMENT_TABS } from '../config/equipmentTabs'
import { useFacility } from '../context/FacilityContext'
import useFetch from '../hooks/useFetch'
import { fmt, fmtDateTime, labelsRequest, openBlob } from '../utils/equipment'
import EquipmentMaintenanceTab from '../components/EquipmentMaintenanceTab'
import OperationalStateDialog from '../components/OperationalStateDialog'
const KV = ({ label, children }) => (
  <div className="eq-kv"><span className="muted">{label}</span><span>{children}</span></div>
)
const name = (o) => (o ? (o.code ? `${o.code} – ${o.name}` : o.name) : '—')

function Overview({ equipment: e }) {
  const m = e.equipment_model
  return (
    <div className="eq-grid">
      <KV label="Asset tag">{e.asset_tag}</KV>
      <KV label="Legacy asset ID">{fmt(e.legacy_asset_id)}</KV>
      <KV label="Serial number">{fmt(e.serial_number)}</KV>
      <KV label="Model">{m.model_name} ({m.model_number})</KV>
      <KV label="Manufacturer">{fmt(m.manufacturer?.name)}</KV>
      <KV label="Category">{name(m.category)}</KV>
      <KV label="Department">{name(e.owning_department)}</KV>
      <KV label="Location">{name(e.current_location)}</KV>
      <KV label="Criticality">{e.criticality}</KV>
      <KV label="Ownership">{e.ownership_type}</KV>
      <KV label="Owner vendor">{name(e.owner_vendor)}</KV>
      <KV label="Ownership end date">{fmt(e.ownership_end_date)}</KV>
      <KV label="Funding source">{name(e.funding_source)}</KV>
      <KV label="Supplier">{name(e.supplier_vendor)}</KV>
      <KV label="PO">{fmt(e.purchase_order_number)} {e.purchase_order_date ? `(${e.purchase_order_date})` : ''}</KV>
      <KV label="GRN">{fmt(e.grn_number)} {e.grn_date ? `(${e.grn_date})` : ''}</KV>
      <KV label="Invoice">{fmt(e.invoice_number)} {e.invoice_date ? `(${e.invoice_date})` : ''}</KV>
      <KV label="Purchase cost (INR)">{fmt(e.purchase_cost)}</KV>
      <KV label="Installation cost (INR)">{fmt(e.installation_cost)}</KV>
      <KV label="PM interval (days)">{fmt(e.effective_pm_interval_days)}</KV>
      <KV label="Calibration interval (days)">{fmt(e.effective_calibration_interval_days)}</KV>
      <KV label="Risk class">{fmt(e.effective_risk_class)}</KV>
      <KV label="Expected life (years)">{fmt(e.effective_expected_life_years)}</KV>
      <KV label="Legacy entry">{e.is_legacy_entry ? 'Yes' : 'No'}</KV>
      <KV label="Notes">{fmt(e.notes)}</KV>
      {Object.entries(e.custom_attributes || {}).map(([k, v]) => <KV key={k} label={k}>{String(v)}</KV>)}
    </div>
  )
}

function Installation({ equipment: e }) {
  const docs = useFetch('/documents/', { entity_type: 'equipment', entity: e.public_id, page_size: 100 }, e.lifecycle_stage === 'INSTALLED')
  const c = e.commissioning
  // Advisory only: heuristic on the document type code; not a gate.
  const hasReport = (docs.data?.results || []).some((d) => /install/i.test(d.document_type || ''))
  return (
    <div>
      {e.lifecycle_stage === 'INSTALLED' && !docs.loading && !hasReport && (
        <div className="alert alert-warning">No installation report document is attached yet. You can still commission, but attaching one is recommended (Documents tab).</div>
      )}
      {!c ? <p className="muted">Not installed yet.</p> : (
        <div className="eq-grid">
          <KV label="Installation date">{fmt(c.installation_date)}</KV>
          <KV label="Installation engineer">{fmt(c.installation_engineer_name)}</KV>
          <KV label="Installation vendor">{name(c.installation_vendor)}</KV>
          <KV label="Installation notes">{fmt(c.installation_notes)}</KV>
          <KV label="Acceptance result">{fmt(c.acceptance_test_result)}</KV>
          <KV label="Acceptance date">{fmt(c.acceptance_date)}</KV>
          <KV label="Accepted by">{fmt(c.accepted_by)}</KV>
          <KV label="Acceptance notes">{fmt(c.acceptance_test_notes)}</KV>
          <KV label="Handed over to">{name(c.handed_over_department)}</KV>
          <KV label="Received by">{fmt(c.handover_received_by_name)}</KV>
          <KV label="Training conducted">{c.training_conducted ? 'Yes' : 'No'}</KV>
          <KV label="Training notes">{fmt(c.training_notes)}</KV>
          <KV label="Commissioning date">{fmt(c.commissioning_date)}</KV>
        </div>
      )}
    </div>
  )
}

function History({ equipment: e, kind }) {
  const [page, setPage] = useState(1)
  const res = useFetch(`/equipment/${e.public_id}/${kind}/`, { page, page_size: 20 })
  const columns = kind === 'state-history' ? [
    { key: 'created_at', header: 'When', render: (r) => fmtDateTime(r.created_at) },
    { key: 'change_type', header: 'Type' },
    { key: 'from_value', header: 'From', render: (r) => fmt(r.from_value) },
    { key: 'to_value', header: 'To' },
    { key: 'reason', header: 'Reason' },
    { key: 'created_by', header: 'By', render: (r) => fmt(r.created_by) },
  ] : [
    { key: 'moved_at', header: 'When', render: (r) => fmtDateTime(r.moved_at) },
    { key: 'from', header: 'From', render: (r) => `${name(r.from_location)} / ${name(r.from_department)}` },
    { key: 'to', header: 'To', render: (r) => `${name(r.to_location)} / ${name(r.to_department)}` },
    { key: 'reason', header: 'Reason' },
    { key: 'created_by', header: 'By', render: (r) => fmt(r.created_by) },
  ]
  return (
    <>
      <Table columns={columns} rows={res.data?.results} loading={res.loading} empty="No history yet." />
      <SimplePager page={page} count={res.data?.count} pageSize={20} onPage={setPage} />
    </>
  )
}

function QrLabels({ equipment: e }) {
  const toast = useToast()
  const [urls, setUrls] = useState({})
  useEffect(() => {
    let alive = true
    const made = []
    ;(async () => {
      try {
        const [q, b] = await Promise.all([
          api.get(`/equipment/${e.public_id}/qr/`, { responseType: 'blob' }),
          api.get(`/equipment/${e.public_id}/barcode/`, { responseType: 'blob' }),
        ])
        const qr = URL.createObjectURL(q.data); const bar = URL.createObjectURL(b.data)
        made.push(qr, bar)
        if (alive) setUrls({ qr, bar })
      } catch { /* shown as empty */ }
    })()
    return () => { alive = false; made.forEach((u) => URL.revokeObjectURL(u)) }
  }, [e.public_id])
  const print = async () => {
    try { await openBlob(labelsRequest([e.public_id])) } catch { toast.error('Could not generate the label.') }
  }
  return (
    <div>
      <div className="row">
        {urls.qr && <img src={urls.qr} alt="QR code" width={180} height={180} />}
        {urls.bar && <img src={urls.bar} alt="Code 128 barcode of the asset tag" height={120} />}
      </div>
      <p className="muted">QR: {e.qr_code_value} · Barcode: {e.asset_tag}</p>
      <Button onClick={print}>Print label</Button>
    </div>
  )
}

export default function EquipmentDetailPage() {
  const { publicId } = useParams()
  const { can } = useFacility()
  const toast = useToast()
  const res = useFetch(`/equipment/${publicId}/`)
  const [tab, setTab] = useState('overview')
  const [dialog, setDialog] = useState(null)

  if (res.loading && !res.data) return <p className="muted">Loading…</p>
  if (res.error || !res.data) return <div className="alert alert-danger">Equipment not found. <Link to="/equipment">Back</Link></div>
  const e = res.data
  const close = () => setDialog(null)
  const done = (msg) => () => { close(); toast.success(msg); res.reload() }
  const t = can('equipment.transition')
  const stage = e.lifecycle_stage

  const builtIn = {
    overview: <Overview equipment={e} />,
    installation: <Installation equipment={e} />,
    status: <History equipment={e} kind="state-history" />,
    movements: <History equipment={e} kind="movements" />,
    documents: <DocumentsPanel entityType="equipment" entityId={e.public_id} viewPermission="equipment.view" attachPermission="equipment.change" />,
    qr: <QrLabels equipment={e} />,
    maintenance: <EquipmentMaintenanceTab equipment={e} reload={res.reload} />,
  }
  const current = EQUIPMENT_TABS.find((x) => x.key === tab)
  let body = builtIn[tab]
  if (!body && current?.component) { const C = current.component; body = <C equipment={e} reload={res.reload} /> }
  if (!body) body = <p className="muted">Available in Phase {current?.phase}.</p>

  return (
    <section>
      <div className="page-head">
        <h2>{e.asset_tag} · {e.name}</h2> <StageBadge value={stage} /> <StateBadge value={e.operational_state} />
        <span className="spacer" />
        {t && stage === 'RECEIVED' && <Button variant="primary" onClick={() => setDialog('install')}>Install</Button>}
        {t && stage === 'INSTALLED' && <Button variant="primary" onClick={() => setDialog('commission')}>Accept & Commission</Button>}
        {t && (stage === 'RECEIVED' || stage === 'INSTALLED') && <Button variant="danger" onClick={() => setDialog('reject')}>Reject</Button>}
        {t && stage === 'COMMISSIONED' && <Button onClick={() => setDialog('state')}>Change state</Button>}
        {t && ['RECEIVED', 'INSTALLED', 'COMMISSIONED'].includes(stage) && <Button onClick={() => setDialog('move')}>Move</Button>}
        <Link to="/equipment">Back to list</Link>
      </div>

      <div className="eq-tabs">
        {EQUIPMENT_TABS.map((x) => (
          <button key={x.key} type="button" className={`eq-tab${tab === x.key ? ' active' : ''}`} onClick={() => setTab(x.key)}>{x.label}</button>
        ))}
      </div>
      {body}

      {dialog === 'install' && <InstallDialog eq={e} onClose={close} onDone={done('Installation recorded.')} />}
      {dialog === 'commission' && <CommissionDialog eq={e} onClose={close} onDone={done('Equipment commissioned.')} />}
      {dialog === 'reject' && <RejectDialog eq={e} onClose={close} onDone={done('Equipment rejected.')} />}
      {dialog === 'state' && <OperationalStateDialog eq={e} onClose={close} onDone={done('State updated.')} />}
      {dialog === 'move' && <MoveDialog eq={e} onClose={close} onDone={done('Equipment moved.')} />}
    </section>
  )
}
