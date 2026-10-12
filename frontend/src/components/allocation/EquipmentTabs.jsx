import { useState } from 'react'
import { useFacility } from '../../context/FacilityContext'
import SimplePager from '../SimplePager'
import { Table, useToast } from '../ui'
import AllocateDialog from './AllocateDialog'
import ReleaseDialog from './ReleaseDialog'
import ReservationModal from './ReservationModal'
import UsageLogModal from './UsageLogModal'
import { Button, StatusBadge, eqValue, fmtDateTime, toInput, useFetch } from './shared'

const preset = (e) => eqValue(e)

export function AssignmentsTab({ equipment: e, reload }) {
  const { can } = useFacility()
  const toast = useToast()
  const [page, setPage] = useState(1)
  const [dlg, setDlg] = useState(null)
  const res = useFetch('/allocations/', { equipment: e.public_id, page, page_size: 20 }, can('allocation.view'))
  const rows = res.data?.results || []
  const active = rows.find((a) => !a.is_released)
  const done = (msg) => () => { setDlg(null); toast.success(msg); res.reload(); reload?.() }
  return (
    <div>
      <div className="page-head"><span className="spacer" />
        {can('allocation.assign') && e.lifecycle_stage === 'COMMISSIONED' && !active &&
          <Button variant="primary" onClick={() => setDlg('allocate')}>Allocate</Button>}
        {can('allocation.assign') && active && <Button onClick={() => setDlg(active)}>Release</Button>}
      </div>
      <Table rows={rows} loading={res.loading} empty="No allocations yet." columns={[
        { key: 'target', header: 'To', render: (a) => a.department?.name || a.location?.name || '—' },
        { key: 'src', header: 'Source', render: (a) => a.source_module },
        { key: 'pt', header: 'Patient', render: (a) => a.patient_reference || '—' },
        { key: 'from', header: 'Assigned', render: (a) => fmtDateTime(a.assigned_at) },
        { key: 'rel', header: 'Released', render: (a) => (a.released_at ? `${fmtDateTime(a.released_at)} · ${a.condition_on_release}` : <StatusBadge tone="info">Active</StatusBadge>) },
        { key: 'ov', header: '', render: (a) => (a.gate_override ? <StatusBadge tone="warning">Gate overridden</StatusBadge> : null) },
      ]} />
      <SimplePager page={page} count={res.data?.count} pageSize={20} onPage={setPage} />
      {dlg === 'allocate' && <AllocateDialog equipment={preset(e)} onClose={() => setDlg(null)} onDone={done('Equipment allocated.')} />}
      {dlg && dlg !== 'allocate' && <ReleaseDialog allocation={dlg} onClose={() => setDlg(null)} onDone={done('Equipment released.')} />}
    </div>
  )
}

export function ReservationsTab({ equipment: e }) {
  const { can } = useFacility()
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const res = useFetch('/reservations/', { equipment: e.public_id, ordering: '-start_at', page_size: 50 }, can('reservation.view'))
  const rows = res.data?.results || []
  const now = Date.now()
  const upcoming = rows.filter((r) => r.status === 'CONFIRMED' && new Date(r.end_at) > now).reverse()
  const past = rows.filter((r) => !upcoming.includes(r))
  const cols = [
    { key: 's', header: 'Start', render: (r) => fmtDateTime(r.start_at) },
    { key: 'e', header: 'End', render: (r) => fmtDateTime(r.end_at) },
    { key: 'd', header: 'Department', render: (r) => r.department.name },
    { key: 'p', header: 'Purpose', render: (r) => r.purpose },
    { key: 'st', header: 'Status', render: (r) => r.status },
  ]
  const start = new Date(); start.setMinutes(0, 0, 0); start.setHours(start.getHours() + 1)
  return (
    <div>
      <div className="page-head"><h3>Upcoming</h3><span className="spacer" />
        {can('reservation.add') && e.lifecycle_stage === 'COMMISSIONED' && <Button variant="primary" onClick={() => setOpen(true)}>Reserve</Button>}
      </div>
      <Table rows={upcoming} loading={res.loading} empty="No upcoming reservations." columns={cols} />
      <h3>Past</h3>
      <Table rows={past} loading={res.loading} empty="No past reservations." columns={cols} />
      {open && <ReservationModal equipment={preset(e)} start={toInput(start)} end={toInput(new Date(start.getTime() + 3600000))}
        onClose={() => setOpen(false)} onDone={() => { setOpen(false); toast.success('Reserved.'); res.reload() }} />}
    </div>
  )
}

export function UsageTab({ equipment: e }) {
  const { can } = useFacility()
  const toast = useToast()
  const [page, setPage] = useState(1)
  const [modal, setModal] = useState(null)
  const sum = useFetch(`/equipment/${e.public_id}/usage-summary/`, {}, can('usage.view'))
  const res = useFetch('/usage-logs/', { equipment: e.public_id, page, page_size: 20 }, can('usage.view'))
  const s = sum.data
  const reload = () => { sum.reload(); res.reload() }
  return (
    <div>
      {s && (
        <div className="eq-grid">
          <div className="eq-kv"><span className="muted">Total hours</span><span>{Number(s.total_hours).toFixed(2)}</span></div>
          <div className="eq-kv"><span className="muted">Last 30 days (h)</span><span>{s.hours_last_30_days}</span></div>
          <div className="eq-kv"><span className="muted">Sessions</span><span>{s.session_count}</span></div>
          <div className="eq-kv"><span className="muted">Last session</span><span>{s.last_session ? fmtDateTime(s.last_session.started_at) : '—'}</span></div>
        </div>
      )}
      <div className="page-head"><span className="spacer" />
        {can('usage.add') && e.lifecycle_stage === 'COMMISSIONED' && <Button variant="primary" onClick={() => setModal('new')}>Add usage</Button>}
      </div>
      <Table rows={res.data?.results} loading={res.loading} empty="No usage logged." columns={[
        { key: 's', header: 'Started', render: (u) => fmtDateTime(u.started_at) },
        { key: 'e', header: 'Ended', render: (u) => fmtDateTime(u.ended_at) },
        { key: 'm', header: 'Minutes', render: (u) => Number(u.duration_minutes).toFixed(0) },
        { key: 'o', header: 'Operator', render: (u) => u.operator_name || '—' },
        { key: 'pr', header: 'Procedure', render: (u) => u.procedure_text || '—' },
        { key: 'a', header: '', render: (u) => (can('usage.change') ? <Button size="sm" onClick={() => setModal(u)}>Edit</Button> : null) },
      ]} />
      <SimplePager page={page} count={res.data?.count} pageSize={20} onPage={setPage} />
      {modal && <UsageLogModal log={modal === 'new' ? null : modal} equipment={preset(e)} onClose={() => setModal(null)}
        onDone={() => { setModal(null); toast.success('Saved.'); reload() }} />}
    </div>
  )
}