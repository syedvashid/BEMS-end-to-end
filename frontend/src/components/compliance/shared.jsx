import { useEffect, useState } from 'react'
import { StatusBadge } from '../ui'
// ---- the ONLY place with guessed import paths/export styles: adjust here if they differ ----
import { api } from '../../api/client'
import useFetch from '../../hooks/useFetch'
import useSubmit from '../../hooks/useSubmit'
import usePermission from '../../hooks/usePermission'
import { fieldError, parseApiError } from '../../utils/errors'
export { api, fieldError, parseApiError, useFetch, useSubmit, usePermission }

const pad = (n) => String(n).padStart(2, '0')
export const today = () => {
  const d = new Date()
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
export const fmtDate = (s) =>
  s ? new Date(`${s}T00:00:00`).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'
export const nn = (v) => (v === '' || v === undefined ? null : v)
export const clean = (o) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== '' && v != null))

/** Tiny form state: bind('field') -> {name, value, onChange} for FormField / inputs. */
export function useForm(initial) {
  const [v, setV] = useState(initial)
  const bind = (name) => ({
    name,
    value: v[name] ?? '',
    onChange: (e) => setV((p) => ({ ...p, [name]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })),
  })
  return { v, setV, bind }
}

/** Options for a select, from a list endpoint (first 100 rows). */
export function useOptions(path, toOption, params = {}) {
  const [opts, setOpts] = useState([])
  useEffect(() => {
    let on = true
    api.get(path, { params: { page_size: 100, ...params } })
      .then((r) => on && setOpts((r.data.results || []).map(toOption)))
      .catch(() => {})
    return () => { on = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path])
  return opts
}
export const withBlank = (opts, label = 'Select…') => [{ value: '', label }, ...opts]
export const equipmentOption = (e) => ({ value: e.public_id, label: `${e.asset_tag} — ${e.name}` })
export const vendorOption = (x) => ({ value: x.public_id, label: x.name })

const daysFromToday = (date) =>
  Math.round((new Date(`${date}T00:00:00`) - new Date(`${today()}T00:00:00`)) / 86400000)

export const CAL_STATUS = {
  OK: ['success', 'OK'], DUE_SOON: ['warning', 'Due soon'], OVERDUE: ['danger', 'Overdue'],
  NOT_REQUIRED: ['neutral', 'Not required'],
}
export function CalChip({ status }) {
  const [tone, label] = CAL_STATUS[status] || ['neutral', status || '—']
  return <StatusBadge tone={tone}>{label}</StatusBadge>
}

export function ExpiryChip({ date }) {
  if (!date) return null
  const d = daysFromToday(date)
  const tone = d < 0 ? 'danger' : d <= 7 ? 'danger' : d <= 30 ? 'warning' : d <= 90 ? 'info' : 'success'
  const text = d < 0 ? `Expired ${-d}d ago` : d === 0 ? 'Expires today' : `${d}d left`
  return <StatusBadge tone={tone}>{text}</StatusBadge>
}

export const BUCKETS = {
  OVERDUE: ['danger', 'Overdue'], D7: ['danger', '≤ 7 days'], D30: ['warning', '≤ 30 days'],
  D60: ['info', '≤ 60 days'], D90: ['neutral', '≤ 90 days'], LATER: ['neutral', 'Later'],
}
export function BucketChip({ bucket }) {
  const [tone, label] = BUCKETS[bucket] || ['neutral', bucket]
  return <StatusBadge tone={tone}>{label}</StatusBadge>
}

export function ConflictNote({ error }) {
  const code = error?.code ?? error?.error?.code
  if (code !== 'stale_version') return null
  return <p role="alert">This record was changed by someone else. Close it, reopen it and try again.</p>
}