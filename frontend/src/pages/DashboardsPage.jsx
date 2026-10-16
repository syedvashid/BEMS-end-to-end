import { useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import WidgetRenderer, { isWide } from '../components/charts/WidgetRenderer.jsx'
import { Button, FormField, Modal } from '../components/ui'
import {
  api, apiError, daysAgo, ErrorNote, fmtDay, useCanAny, useFetch, usePermission,
} from '../components/reports/shared.jsx'
import AccessDeniedPage from './AccessDeniedPage.jsx'

const TABS = [
  { key: 'executive', label: 'Executive', codes: ['equipment.view'] },
  { key: 'operations', label: 'Operations', codes: ['work_order.view'] },
  { key: 'utilization', label: 'Utilization', codes: ['usage.view', 'allocation.view'] },
  { key: 'finance', label: 'Finance', codes: ['finance.view'] },
  { key: 'analytics', label: 'Analytics', codes: ['work_order.view'] },
]
const NEEDS_STATS = ['utilization', 'analytics']

function RebuildModal({ onClose, onDone }) {
  const [from, setFrom] = useState(daysAgo(7))
  const [to, setTo] = useState(daysAgo(1))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const go = async () => {
    setBusy(true); setError(null)
    try {
      const res = await api.post('/stats/rebuild/', { from, to })
      setResult(res.data); onDone()
    } catch (e) { setError(apiError(e)) } finally { setBusy(false) }
  }
  return (
    <Modal title="Rebuild statistics" onClose={onClose}
      footer={<><Button onClick={onClose}>Close</Button><Button variant="primary" loading={busy} onClick={go}>Rebuild</Button></>}>
      <p className="rp-note">Recomputes the daily statistics for the range (at most 366 days). Safe to repeat.</p>
      <div className="rp-toolbar">
        <FormField label="From" name="rb_from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        <FormField label="To" name="rb_to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
      </div>
      {error && <ErrorNote error={error.status === 409 ? { ...error, message: 'A rebuild is already running for this facility. Try again in a few minutes.' } : error} />}
      {result && <div className="alert alert-success">Done: {result.equipment_processed} equipment, {result.rows_written} daily rows ({result.seconds}s).</div>}
    </Modal>
  )
}

function DashboardTab({ name }) {
  const [draft, setDraft] = useState({ days: '14', group_by: 'department', low: '20', high: '80', from: '', to: '' })
  const [applied, setApplied] = useState({})
  const [showRebuild, setShowRebuild] = useState(false)
  const canRebuild = usePermission('stats.run')
  const params = name === 'utilization'
    ? { days: applied.days, group_by: applied.group_by, low: applied.low, high: applied.high }
    : name === 'analytics' ? { from: applied.from, to: applied.to } : {}
  const res = useFetch(`/dashboards/${name}/`, params)
  const status = useFetch('/stats/status/', {}, NEEDS_STATS.includes(name))
  const set = (k) => (e) => setDraft((d) => ({ ...d, [k]: e.target.value }))
  const widgets = res.data?.widgets || []
  const kpis = widgets.filter((w) => w.type === 'kpi')
  const rest = widgets.filter((w) => w.type !== 'kpi')
  const upTo = status.data?.data_up_to || res.data?.data_up_to

  return (
    <>
      <div className="rp-toolbar">
        {name === 'utilization' && (
          <>
            <FormField label="Days" name="u_days" as="select" value={draft.days} onChange={set('days')}
              options={['7', '14', '30', '60', '90'].map((v) => ({ value: v, label: `${v} days` }))} />
            <FormField label="Group by" name="u_group" as="select" value={draft.group_by} onChange={set('group_by')}
              options={[{ value: 'department', label: 'Department' }, { value: 'location', label: 'Ward / location' }]} />
            <FormField label="Low below %" name="u_low" type="number" value={draft.low} onChange={set('low')} />
            <FormField label="High above %" name="u_high" type="number" value={draft.high} onChange={set('high')} />
          </>
        )}
        {name === 'analytics' && (
          <>
            <FormField label="From" name="a_from" type="date" value={draft.from} onChange={set('from')} hint="Default: last 12 months" />
            <FormField label="To" name="a_to" type="date" value={draft.to} onChange={set('to')} />
          </>
        )}
        {(name === 'utilization' || name === 'analytics') && <Button variant="primary" onClick={() => setApplied({ ...draft })}>Apply</Button>}
        <Button onClick={res.reload}>Refresh</Button>
        {NEEDS_STATS.includes(name) && (
          <span className="rp-note">Data up to {upTo ? fmtDay(upTo) : 'no statistics yet'}</span>
        )}
        {NEEDS_STATS.includes(name) && canRebuild && <Button onClick={() => setShowRebuild(true)}>Rebuild statistics</Button>}
      </div>
      {res.error && <div className="alert alert-danger">{res.error.message}</div>}
      {res.loading && !res.data && <p className="rp-note">Loading…</p>}
      {kpis.length > 0 && <div className="rp-kpis">{kpis.map((w) => <WidgetRenderer key={w.key} widget={w} />)}</div>}
      <div className="rp-grid">
        {rest.map((w) => <div key={w.key} style={isWide(w) ? { gridColumn: '1 / -1' } : undefined}><WidgetRenderer widget={w} /></div>)}
      </div>
      {showRebuild && <RebuildModal onClose={() => setShowRebuild(false)} onDone={() => { res.reload(); status.reload() }} />}
    </>
  )
}

export default function DashboardsPage() {
  const { name } = useParams()
  const navigate = useNavigate()
  const allowed = {
    executive: useCanAny(TABS[0].codes),
    operations: useCanAny(TABS[1].codes),
    utilization: useCanAny(TABS[2].codes),
    finance: useCanAny(TABS[3].codes),
    analytics: useCanAny(TABS[4].codes),
  }
  const visible = TABS.filter((t) => allowed[t.key])
  if (!visible.length) return <AccessDeniedPage />
  if (!name || !allowed[name]) return <Navigate to={`/dashboards/${visible[0].key}`} replace />
  return (
    <>
      <div className="page-head"><h1>Dashboards</h1></div>
      <div className="rp-tabs" role="tablist">
        {visible.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={t.key === name}
            className={`rp-tab${t.key === name ? ' active' : ''}`} onClick={() => navigate(`/dashboards/${t.key}`)}>{t.label}</button>
        ))}
      </div>
      <DashboardTab key={name} name={name} />
    </>
  )
}
