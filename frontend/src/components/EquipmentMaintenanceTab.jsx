import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Table, useToast } from './ui'
import ReportBreakdownModal from './ReportBreakdownModal'
import { OverdueBadge, PriorityPill, StatusPill } from './WorkOrderBadges'
import { useFacility } from '../context/FacilityContext'
import useFetch from '../hooks/useFetch'
import { fmt, fmtDateTime } from '../utils/equipment'
import { TYPE_LABEL } from '../utils/maintenance'
import '../styles/maintenance.css'

// Fills the placeholder "Maintenance" tab of the equipment detail page.
export default function EquipmentMaintenanceTab({ equipment: e, reload }) {
  const { can } = useFacility()
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const holds = useFetch(`/equipment/${e.public_id}/holds/`, { page_size: 50 })
  const plans = useFetch('/maintenance-plans/', { equipment: e.public_id, page_size: 50 }, can('maintenance_plan.view'))
  const wos = useFetch('/work-orders/', { equipment: e.public_id, page_size: 10 }, can('work_order.view'))
  const refresh = () => { holds.reload(); wos.reload(); reload?.() }
  const commissioned = e.lifecycle_stage === 'COMMISSIONED'

  return (
    <div>
      <div className="mt-actions">
        {commissioned && can('work_order.add') && <Button variant="danger" onClick={() => setOpen(true)}>Report breakdown</Button>}
      </div>

      <div className="mt-section">
        <h3>Holds</h3>
        <Table rows={holds.data?.results} loading={holds.loading} empty="No holds."
          columns={[
            { key: 'hold_type', header: 'Type', render: (h) => h.hold_type.replace('_', ' ') },
            { key: 'source', header: 'Source', render: (h) => (h.work_order ? <Link to={`/work-orders/${h.work_order.public_id}`}>{h.work_order.wo_number}</Link> : 'Manual') },
            { key: 'reason', header: 'Reason' },
            { key: 'started_at', header: 'Since', render: (h) => fmtDateTime(h.started_at) },
            { key: 'released_at', header: 'Released', render: (h) => (h.released_at ? fmtDateTime(h.released_at) : <strong>Open</strong>) },
          ]} />
      </div>

      {can('maintenance_plan.view') && (
        <div className="mt-section">
          <h3>Maintenance plans</h3>
          <Table rows={plans.data?.results} loading={plans.loading} empty="No plans for this equipment."
            columns={[
              { key: 'name', header: 'Plan' },
              { key: 'freq', header: 'Every', render: (p) => `${p.frequency_value} ${p.frequency_type.toLowerCase()}` },
              { key: 'last_performed_date', header: 'Last done', render: (p) => fmt(p.last_performed_date) },
              { key: 'next_due_date', header: 'Next due' },
            ]} />
        </div>
      )}

      {can('work_order.view') && (
        <div className="mt-section">
          <h3>Work orders</h3>
          <Table rows={wos.data?.results} loading={wos.loading} empty="No work orders."
            columns={[
              { key: 'wo_number', header: 'Number', render: (w) => <Link to={`/work-orders/${w.public_id}`}>{w.wo_number}</Link> },
              { key: 'type', header: 'Type', render: (w) => TYPE_LABEL[w.work_order_type] },
              { key: 'priority', header: 'Priority', render: (w) => <PriorityPill priority={w.priority} /> },
              { key: 'status', header: 'Status', render: (w) => <><StatusPill status={w.status} /> <OverdueBadge show={w.is_overdue} /></> },
              { key: 'due_date', header: 'Due', render: (w) => fmt(w.due_date) },
            ]} />
        </div>
      )}

      {open && (
        <ReportBreakdownModal preset={{ public_id: e.public_id, label: `${e.asset_tag} · ${e.name}` }}
          onClose={() => setOpen(false)}
          onDone={(wo) => { setOpen(false); toast.success(`Breakdown reported: ${wo.wo_number}`); refresh() }} />
      )}
    </div>
  )
}
