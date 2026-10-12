import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, FormField, Modal, StatusBadge, Table } from '../ui'
import EquipmentPicker from '../EquipmentPicker'
import { fmtDateTime } from '../../utils/equipment'
import {
  api, CalChip, clean, fieldError, nn, parseApiError, today, useForm, useFetch, useOptions, withBlank,
} from '../compliance/shared'

export { api, CalChip, clean, nn, today, useForm, useFetch, useOptions, withBlank, fmtDateTime, parseApiError }

const p2 = (n) => String(n).padStart(2, '0')
export const toInput = (d) => {
  const x = d instanceof Date ? d : new Date(d)
  return `${x.getFullYear()}-${p2(x.getMonth() + 1)}-${p2(x.getDate())}T${p2(x.getHours())}:${p2(x.getMinutes())}`
}
export const toIso = (s) => (s ? new Date(s).toISOString() : null)
export const fe = (err, name) => (err ? fieldError(err, name) : undefined)
export const eqValue = (e) => ({ public_id: e.public_id, label: `${e.asset_tag} · ${e.name}` })
export const SOURCES = ['MANUAL', 'IPD', 'OT', 'ICU', 'ER', 'RADIOLOGY', 'LAB']
export const toOpts = (list) => list.map((x) => ({ value: x, label: x }))

// ---- submit helper: run(fn) -> sets busy/error from a thrown axios error
export function useAction() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const run = async (fn) => {
    setBusy(true); setError(null)
    try { return await fn() } catch (e) { setError(parseApiError(e)); return undefined } finally { setBusy(false) }
  }
  return { busy, error, run, setError }
}

// ---- location tree (indented select options)
export function treeOptions(rows) {
  const pid = (r) => r.parent_location?.public_id ?? (typeof r.parent_location === 'string' ? r.parent_location : null)
  const ids = new Set(rows.map((r) => r.public_id))
  const kids = {}
  rows.forEach((r) => { const p = pid(r); const k = p && ids.has(p) ? p : 'root'; (kids[k] ||= []).push(r) })
  const out = []
  const walk = (k, depth) => (kids[k] || []).forEach((r) => {
    out.push({ value: r.public_id, label: `${'\u00a0\u00a0'.repeat(depth)}${r.code} – ${r.name}` })
    walk(r.public_id, depth + 1)
  })
  walk('root', 0)
  return out
}
export function useLocationOptions() {
  const rows = useFetch('/locations/', { page_size: 100 }).data?.results
  return useMemo(() => treeOptions(rows || []), [rows])
}
export const useDepartmentOptions = (path = '/departments/') =>
  useOptions(path, (d) => ({ value: d.public_id, label: `${d.code} – ${d.name}` }))

// ---- display bits
const TEXT = {
  stale_version: 'This record was changed by someone else. Close it, reopen it and try again.',
  permission_denied: 'You do not have permission to do this.',
  calibration_gate: 'Calibration gate: allocation is blocked.',
}
export function Items({ items, tone = 'warning' }) {
  if (!items?.length) return null
  return (
    <ul className="al-items">
      {items.map((i, k) => (
        <li key={k}>
          <StatusBadge tone={tone}>{i.code.replaceAll('_', ' ').toLowerCase()}</StatusBadge> {i.message}
          {i.reservation && <> ({i.reservation.department?.name}, {fmtDateTime(i.reservation.start_at)} – {fmtDateTime(i.reservation.end_at)})</>}
          {i.allocation && <> ({i.allocation.department?.name || i.allocation.location?.name || 'allocated'}, since {fmtDateTime(i.allocation.assigned_at)})</>}
        </li>
      ))}
    </ul>
  )
}
export function ApiAlert({ error }) {
  if (!error) return null
  const d = error.details || {}
  if (error.code === 'validation_error') {
    return d.non_field_errors ? <div className="alert alert-danger" role="alert">{d.non_field_errors.join(' ')}</div> : null
  }
  const c = d.clashing_reservation
  const o = d.overlapping_session
  return (
    <div className="alert alert-danger" role="alert">
      {TEXT[error.code] || error.message || 'Something went wrong.'}
      {d.blocking && <Items items={d.blocking} tone="danger" />}
      {c && <div>Clashes with: {c.equipment?.asset_tag} · {c.department?.name} · {fmtDateTime(c.start_at)} – {fmtDateTime(c.end_at)} ({c.purpose})</div>}
      {o && <div>Overlaps session: {fmtDateTime(o.started_at)} – {fmtDateTime(o.ended_at)}{o.operator_name ? ` (${o.operator_name})` : ''}</div>}
    </div>
  )
}
export function EquipmentField({ value, onChange, locked, error }) {
  if (locked && value) return <p><strong>{value.label}</strong></p>
  return <EquipmentPicker value={value} onChange={onChange} required error={error} />
}
export const EqLink = ({ e }) => <Link to={`/equipment/${e.public_id}`}>{e.asset_tag} · {e.name}</Link>
export const Check = ({ label, checked, onChange }) => (
  <label className="al-check"><input type="checkbox" checked={checked} onChange={onChange} /> {label}</label>
)

/** One free-text step (approve / reject / cancel with a reason). onSubmit(text) must throw on failure. */
export function NoteModal({ title, label, required, submitLabel = 'Confirm', field = 'note', onSubmit, onClose }) {
  const [text, setText] = useState('')
  const { busy, error, run } = useAction()
  const go = () => run(() => onSubmit(text.trim() || null))
  return (
    <Modal title={title} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Close</Button>
        <Button variant="primary" loading={busy} onClick={go}>{submitLabel}</Button></>}>
      <ApiAlert error={error} />
      <FormField label={label} name={field} as="textarea" required={required} value={text}
        onChange={(e) => setText(e.target.value)} error={fe(error, field)} />
    </Modal>
  )
}

export { Button, FormField, Modal, StatusBadge, Table }