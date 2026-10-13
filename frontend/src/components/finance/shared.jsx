import { useState } from 'react'
import { parseApiError } from '../../utils/errors'
import useFetch from '../../hooks/useFetch'
import { FormField, StatusBadge } from '../ui'

// ---------------------------------------------------------------- formatting
const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 })
const compact = new Intl.NumberFormat('en-IN', { notation: 'compact', maximumFractionDigits: 1 })
const has = (v) => v !== null && v !== undefined && v !== '' && !Number.isNaN(Number(v))

export const fmtMoney = (v) => (has(v) ? inr.format(Number(v)) : '—')
export const fmtNum = (v, digits = 2) => (has(v) ? Number(v).toLocaleString('en-IN', { maximumFractionDigits: digits }) : '—')
export const fmtDay = (d) => (d ? new Date(`${String(d).slice(0, 10)}T00:00:00`).toLocaleDateString('en-IN') : '—')
export const fmtStamp = (d) => (d ? new Date(d).toLocaleString('en-IN') : '—')
export const lbl = (s) => (s ? String(s).replace(/_/g, ' ').toLowerCase().replace(/^\w/, (c) => c.toUpperCase()) : '—')
export const clean = (o) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== '' && v !== null && v !== undefined))
export const nn = (v) => (v === '' || v === undefined ? null : v)
export const opts = (list) => list.map((v) => ({ value: v, label: lbl(v) }))
export const withBlank = (list, text = 'All') => [{ value: '', label: text }, ...list]

export const REASONS = ['UNECONOMICAL_TO_REPAIR', 'BEYOND_ECONOMIC_LIFE', 'OBSOLETE', 'UNSAFE', 'DAMAGED_BEYOND_REPAIR', 'LOST_MISSING', 'OTHER']
export const DISPOSAL_METHODS = ['SOLD', 'SCRAPPED_E_WASTE', 'DONATED', 'RETURNED_TO_VENDOR', 'TRADE_IN', 'AUCTIONED', 'LOST_MISSING']

export const thisMonthInput = () => new Date().toISOString().slice(0, 7)
export const lastMonthInput = () => {
  const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

// ---------------------------------------------------------------- errors
// {code, message, details, status}; details is {field: [messages]} or {blockers: [...]}.
export const apiError = (e) => {
  const body = e?.response?.data?.error
  if (body) return { code: body.code, message: body.message, details: body.details || {}, status: e.response.status }
  const p = parseApiError(e) || {}
  return { code: p.code, message: p.message || 'Something went wrong.', details: p.details || p.fields || {}, status: e?.response?.status }
}
export const fieldErr = (err, name) => {
  const v = err?.details?.[name]
  return Array.isArray(v) ? v.join(' ') : v || undefined
}

export function useAction() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const run = async (fn) => {
    setBusy(true); setError(null)
    try { return await fn() } catch (e) { setError(apiError(e)); return undefined } finally { setBusy(false) }
  }
  return { busy, error, setError, run }
}

export function BlockerList({ blockers }) {
  if (!blockers?.length) return null
  return (
    <ul className="fin-blockers">
      {blockers.map((b) => (
        <li key={b.code}>
          <strong>{b.message}</strong>
          {b.refs?.length > 0 && <span className="muted"> ({b.refs.map((r) => r.label).join(', ')})</span>}
        </li>
      ))}
    </ul>
  )
}

export function ErrorNote({ error }) {
  if (!error) return null
  const fieldLines = Object.entries(error.details || {}).filter(([k]) => k !== 'blockers')
    .map(([k, v]) => `${lbl(k)}: ${Array.isArray(v) ? v.join(' ') : v}`)
  return (
    <div className="alert alert-danger">
      {error.code === 'stale_version' ? 'This record was changed by someone else. Close this window, reload and try again.' : error.message}
      {fieldLines.length > 0 && <ul>{fieldLines.map((l) => <li key={l}>{l}</li>)}</ul>}
      <BlockerList blockers={error.details?.blockers} />
    </div>
  )
}

// ---------------------------------------------------------------- chips
const INDICATOR = { NONE: ['neutral', 'No flag'], REVIEW: ['warning', 'Review'], REPLACE_RECOMMENDED: ['danger', 'Replace recommended'] }
export const IndicatorChip = ({ value }) => <StatusBadge tone={(INDICATOR[value] || INDICATOR.NONE)[0]}>{(INDICATOR[value] || INDICATOR.NONE)[1]}</StatusBadge>

const REQ_TONE = { REQUESTED: 'warning', APPROVED: 'info', REJECTED: 'danger', CANCELLED: 'neutral', COMPLETED: 'success' }
export const RequestChip = ({ value }) => <StatusBadge tone={REQ_TONE[value] || 'neutral'}>{lbl(value)}</StatusBadge>
const DSP_TONE = { IN_PROGRESS: 'warning', COMPLETED: 'success', CANCELLED: 'neutral' }
export const DisposalChip = ({ value }) => <StatusBadge tone={DSP_TONE[value] || 'neutral'}>{lbl(value)}</StatusBadge>
const PLAN_TONE = { CANDIDATE: 'info', APPROVED_FOR_BUDGET: 'success', DEFERRED: 'warning', COMPLETED: 'success', CANCELLED: 'neutral' }
export const PlanChip = ({ value }) => <StatusBadge tone={PLAN_TONE[value] || 'neutral'}>{lbl(value)}</StatusBadge>

export const REASON_TEXT = {
  MAINTENANCE_COST_ABOVE_THRESHOLD: 'Maintenance cost is above the threshold share of the purchase cost',
  AGE_BEYOND_EXPECTED_LIFE: 'Age is beyond the expected life',
}

// ---------------------------------------------------------------- pickers
export function EquipmentPicker({ label = 'Equipment', value, onChange, error, required, params, disabled }) {
  const [q, setQ] = useState('')
  const [picked, setPicked] = useState(null)
  const res = useFetch('/equipment/', clean({ search: q.trim(), page_size: 20, ...params }))
  const rows = res.data?.results || []
  const options = [{ value: '', label: 'Select equipment…' }, ...rows.map((r) => ({ value: r.public_id, label: `${r.asset_tag} · ${r.name}` }))]
  if (picked && !rows.some((r) => r.public_id === picked.value)) options.splice(1, 0, picked)
  return (
    <div>
      <FormField label="Find equipment (asset tag or name)" name="eq_search" value={q} onChange={(e) => setQ(e.target.value)} disabled={disabled} />
      <FormField label={label} name="equipment" as="select" required={required} value={value || ''} error={error} disabled={disabled}
        options={options}
        onChange={(e) => { const v = e.target.value; setPicked(options.find((o) => o.value === v) || null); onChange(v) }} />
    </div>
  )
}

// ---------------------------------------------------------------- plain-SVG line chart
// actual / projection: [{ x: 'YYYY-MM', y: number }]. The dashed projection continues from the last actual point.
export function LineChart({ actual = [], projection = [], height = 240 }) {
  const w = 680
  const pad = { l: 64, r: 14, t: 12, b: 28 }
  const pts = [...actual, ...projection]
  if (pts.length < 2) return <p className="muted">Not enough data to draw a chart yet.</p>
  const ys = pts.map((p) => Number(p.y))
  const max = Math.max(...ys); const min = Math.min(...ys)
  const span = max - min || 1
  const X = (i) => pad.l + (i * (w - pad.l - pad.r)) / (pts.length - 1)
  const Y = (v) => pad.t + (1 - (v - min) / span) * (height - pad.t - pad.b)
  const path = (arr, offset) => arr.map((p, i) => `${i ? 'L' : 'M'}${X(i + offset).toFixed(1)},${Y(Number(p.y)).toFixed(1)}`).join(' ')
  const projPath = projection.length
    ? path([actual[actual.length - 1], ...projection].filter(Boolean), Math.max(actual.length - 1, 0)) : ''
  const ticks = [0, 1, 2, 3].map((i) => min + (span * i) / 3)
  const labelAt = [0, Math.floor((pts.length - 1) / 2), pts.length - 1]
  return (
    <svg className="fin-chart" viewBox={`0 0 ${w} ${height}`} width="100%" role="img" aria-label="Book value over time">
      {ticks.map((t) => (
        <g key={t}>
          <line className="grid" x1={pad.l} x2={w - pad.r} y1={Y(t)} y2={Y(t)} />
          <text className="axis" x={pad.l - 6} y={Y(t) + 4} textAnchor="end">{compact.format(t)}</text>
        </g>
      ))}
      {labelAt.map((i) => <text key={i} className="axis" x={X(i)} y={height - 8} textAnchor={i === 0 ? 'start' : i === pts.length - 1 ? 'end' : 'middle'}>{pts[i].x}</text>)}
      {actual.length > 1 && <path className="actual" d={path(actual, 0)} />}
      {projPath && <path className="proj" d={projPath} />}
    </svg>
  )
}
