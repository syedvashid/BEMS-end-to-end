import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button, FormField, Table, useToast } from '../components/ui'
import SimplePager from '../components/SimplePager'
import ReportBreakdownModal from '../components/ReportBreakdownModal'
import WorkOrderFormModal from '../components/WorkOrderFormModal'
import { OverdueBadge, PriorityPill, StatusPill } from '../components/WorkOrderBadges'
import { useFacility } from '../context/FacilityContext'
import useFetch from '../hooks/useFetch'
import { fmt, fmtDateTime } from '../utils/equipment'
import { PRIORITIES, PRIORITY_LABEL, STATUS_LABEL, TYPE_LABEL, WO_STATUSES, WO_TYPES, opts, ymd } from '../utils/maintenance'
import '../styles/maintenance.css'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function Board({ rows }) {
  return (
    <div className="mt-board">
      {WO_STATUSES.map((s) => {
        const items = rows.filter((w) => w.status === s)
        return (
          <div className="mt-col" key={s}>
            <h4>{STATUS_LABEL[s]} ({items.length})</h4>
            {items.map((w) => (
              <Link key={w.public_id} to={`/work-orders/${w.public_id}`} className={`mt-card${w.is_overdue ? ' is-overdue' : ''}`}>
                <strong>{w.wo_number}</strong> <PriorityPill priority={w.priority} /> <OverdueBadge show={w.is_overdue} />
                <div>{w.equipment.asset_tag} · {w.equipment.name}</div>
                <div className="muted">{TYPE_LABEL[w.work_order_type]}{w.due_date ? ` · due ${w.due_date}` : ''}</div>
              </Link>
            ))}
          </div>
        )
      })}
    </div>
  )
}

function Calendar({ rows, month }) {
  const first = new Date(month.getFullYear(), month.getMonth(), 1)
  const lead = (first.getDay() + 6) % 7                       // Monday first
  const days = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate()
  const cells = []
  for (let i = 0; i < lead; i += 1) cells.push(null)
  for (let d = 1; d <= days; d += 1) cells.push(new Date(month.getFullYear(), month.getMonth(), d))
  while (cells.length % 7) cells.push(null)
  const byDay = useMemo(() => {
    const m = {}
    rows.forEach((w) => { if (w.due_date) (m[w.due_date] = m[w.due_date] || []).push(w) })
    return m
  }, [rows])
  const today = ymd(new Date())
  return (
    <div className="mt-cal">
      {DAYS.map((d) => <div key={d} className="mt-cal-h">{d}</div>)}
      {cells.map((c, i) => {
        if (!c) return <div key={i} className="mt-cal-day is-dim" />
        const key = ymd(c)
        return (
          <div key={i} className={`mt-cal-day${key === today ? ' is-today' : ''}`}>
            <strong>{c.getDate()}</strong>
            {(byDay[key] || []).map((w) => (
              <Link key={w.public_id} to={`/work-orders/${w.public_id}`}
                className={`mt-cal-item mt-s-${w.status}${w.is_overdue ? ' mt-overdue' : ''}`}
                title={`${w.wo_number} · ${w.equipment.name}`}>{w.wo_number.slice(-6)} {w.equipment.name}</Link>
            ))}
          </div>
        )
      })}
    </div>
  )
}

export default function WorkOrdersPage() {
  const { can } = useFacility()
  const nav = useNavigate()
  const toast = useToast()
  const [scope, setScope] = useState('all')
  const [view, setView] = useState('list')
  const [page, setPage] = useState(1)
  const [month, setMonth] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1) })
  const [f, setF] = useState({ status: '', work_order_type: '', priority: '', overdue: '', search: '' })
  const [modal, setModal] = useState(null)
  const set = (k) => (e) => { setPage(1); setF((s) => ({ ...s, [k]: e.target.value })) }

  const params = { ...Object.fromEntries(Object.entries(f).filter(([, v]) => v !== '')) }
  if (scope === 'mine') params.assigned_to = 'me'
  if (view === 'list') { params.page = page; params.page_size = 20 } else params.page_size = 100
  if (view === 'calendar') {
    params.due_from = ymd(month)
    params.due_to = ymd(new Date(month.getFullYear(), month.getMonth() + 1, 0))
  }
  const res = useFetch('/work-orders/', params)
  const rows = res.data?.results || []
  const shift = (n) => setMonth((m) => new Date(m.getFullYear(), m.getMonth() + n, 1))

  return (
    <section>
      <div className="page-head">
        <h2>Work orders</h2><span className="spacer" />
        {can('work_order.add') && <Button variant="danger" onClick={() => setModal('breakdown')}>Report breakdown</Button>}
        {can('work_order.change') && <Button variant="primary" onClick={() => setModal('new')}>New work order</Button>}
      </div>

      <div className="eq-tabs">
        <button type="button" className={`eq-tab${scope === 'all' ? ' active' : ''}`} onClick={() => { setScope('all'); setPage(1) }}>All work orders</button>
        <button type="button" className={`eq-tab${scope === 'mine' ? ' active' : ''}`} onClick={() => { setScope('mine'); setPage(1) }}>My work orders</button>
        <span className="spacer" />
        {['list', 'board', 'calendar'].map((v) => (
          <button key={v} type="button" className={`eq-tab${view === v ? ' active' : ''}`} onClick={() => setView(v)}>{v[0].toUpperCase() + v.slice(1)}</button>
        ))}
      </div>

      <div className="mt-toolbar">
        <FormField label="Search" name="search" value={f.search} onChange={set('search')} />
        <FormField label="Status" name="status" as="select" options={opts(WO_STATUSES, STATUS_LABEL, 'All')} value={f.status} onChange={set('status')} />
        <FormField label="Type" name="work_order_type" as="select" options={opts(WO_TYPES, TYPE_LABEL, 'All')} value={f.work_order_type} onChange={set('work_order_type')} />
        <FormField label="Priority" name="priority" as="select" options={opts(PRIORITIES, PRIORITY_LABEL, 'All')} value={f.priority} onChange={set('priority')} />
        <FormField label="Overdue" name="overdue" as="select" options={[{ value: '', label: 'All' }, { value: 'true', label: 'Overdue only' }]} value={f.overdue} onChange={set('overdue')} />
      </div>

      {view === 'calendar' && (
        <div className="mt-actions">
          <Button size="sm" onClick={() => shift(-1)}>‹</Button>
          <strong>{month.toLocaleString('en-IN', { month: 'long', year: 'numeric' })}</strong>
          <Button size="sm" onClick={() => shift(1)}>›</Button>
          {res.data?.count > 100 && <span className="muted">Showing the first 100 of {res.data.count}; narrow the filters.</span>}
        </div>
      )}

      {view === 'list' && (
        <>
          <Table rows={rows} loading={res.loading} empty="No work orders." onRowClick={(w) => nav(`/work-orders/${w.public_id}`)}
            columns={[
              { key: 'wo_number', header: 'Number' },
              { key: 'type', header: 'Type', render: (w) => TYPE_LABEL[w.work_order_type] },
              { key: 'equipment', header: 'Equipment', render: (w) => `${w.equipment.asset_tag} · ${w.equipment.name}` },
              { key: 'priority', header: 'Priority', render: (w) => <PriorityPill priority={w.priority} /> },
              { key: 'status', header: 'Status', render: (w) => <><StatusPill status={w.status} /> <OverdueBadge show={w.is_overdue} /></> },
              { key: 'due_date', header: 'Due', render: (w) => fmt(w.due_date) },
              { key: 'assigned', header: 'Assigned to', render: (w) => fmt(w.assigned_to?.full_name) },
              { key: 'created_at', header: 'Created', render: (w) => fmtDateTime(w.created_at) },
            ]} />
          <SimplePager page={page} count={res.data?.count} pageSize={20} onPage={setPage} />
        </>
      )}
      {view === 'board' && <Board rows={rows} />}
      {view === 'calendar' && <Calendar rows={rows} month={month} />}

      {modal === 'breakdown' && (
        <ReportBreakdownModal onClose={() => setModal(null)}
          onDone={(wo) => { setModal(null); toast.success(`Breakdown reported: ${wo.wo_number}`); res.reload() }} />
      )}
      {modal === 'new' && (
        <WorkOrderFormModal onClose={() => setModal(null)}
          onDone={(wo) => { setModal(null); toast.success(`Work order created: ${wo.wo_number}`); nav(`/work-orders/${wo.public_id}`) }} />
      )}
    </section>
  )
}
