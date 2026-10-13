import { useMemo, useState } from 'react'
import { useFacility } from '../../context/FacilityContext'
import { fmt, fmtDateTime } from '../../utils/equipment'
import { Button, FormField, Modal, StatusBadge } from '../ui'
import {
  ConflictNote, api, clean, fieldError, fmtDate, nn, parseApiError, today, useFetch, useForm, useOptions, withBlank,
} from '../compliance/shared'

export { ConflictNote, api, clean, fieldError, fmt, fmtDate, fmtDateTime, nn, parseApiError, today, useFetch, useForm, useOptions, withBlank }

export const lbl = (s) => (s ? s.charAt(0) + s.slice(1).toLowerCase().replace(/_/g, ' ') : '—')
export const opt = (values) => values.map((v) => ({ value: v, label: lbl(v) }))

export const INCIDENT_TYPES = ['MALFUNCTION', 'USE_ERROR', 'NEAR_MISS', 'OTHER']
export const SEVERITIES = ['NO_HARM', 'MINOR', 'MODERATE', 'SEVERE', 'DEATH']
export const INCIDENT_STATUSES = ['REPORTED', 'UNDER_INVESTIGATION', 'ACTION_TAKEN', 'CLOSED']
export const NOTICE_TYPES = ['RECALL', 'FIELD_SAFETY_NOTICE', 'SAFETY_ALERT', 'ADVISORY']
export const SOURCES = ['MANUFACTURER', 'REGULATOR', 'INTERNAL']
export const URGENCIES = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
export const ACTION_TYPES = ['STOP_USE', 'INSPECT', 'UPDATE_SOFTWARE', 'MODIFY', 'RETURN', 'INFORM_ONLY']
export const SCOPE_TYPES = ['FACILITY', 'DEPARTMENT', 'LOCATION']
export const RESULTS = ['PENDING', 'FOUND', 'FOUND_ELSEWHERE', 'MISSING', 'UNEXPECTED']

const TONES = {
  severity: { NO_HARM: 'neutral', MINOR: 'info', MODERATE: 'warning', SEVERE: 'danger', DEATH: 'danger' },
  incident: { REPORTED: 'warning', UNDER_INVESTIGATION: 'info', ACTION_TAKEN: 'info', CLOSED: 'success' },
  notice: { OPEN: 'warning', CLOSED: 'success', CANCELLED: 'neutral' },
  urgency: { LOW: 'neutral', MEDIUM: 'info', HIGH: 'warning', CRITICAL: 'danger' },
  verification: { PLANNED: 'neutral', IN_PROGRESS: 'info', COMPLETED: 'success', CANCELLED: 'neutral' },
  result: { PENDING: 'neutral', FOUND: 'success', FOUND_ELSEWHERE: 'warning', MISSING: 'danger', UNEXPECTED: 'warning' },
  unit: { PENDING: 'warning', ACTION_COMPLETED: 'success', NOT_APPLICABLE: 'neutral' },
}
export const Chip = ({ kind, value }) => (value ? <StatusBadge tone={TONES[kind]?.[value] || 'neutral'}>{lbl(value)}</StatusBadge> : null)

export const eqLabel = (e) => `${e.asset_tag} · ${e.name}`
export const nowLocal = () => {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
}

/** Runs an async call, tracks busy/error. run() resolves to {ok, data}; it never throws. */
export function useAction() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const run = async (fn) => {
    setBusy(true); setError(null)
    try { return { ok: true, data: await fn() } } catch (e) { setError(parseApiError(e)); return { ok: false } } finally { setBusy(false) }
  }
  return { busy, error, run, clear: () => setError(null) }
}

/** Tolerant view of whatever parseApiError returns: {code, message, details}. */
export const norm = (e) => ({
  code: e?.code ?? e?.error?.code ?? null,
  message: e?.message ?? e?.error?.message ?? null,
  details: e?.details ?? e?.error?.details ?? {},
})

/** General error box: the server message plus any field messages (409 stale_version / conflict included). */
export function ErrorBox({ error }) {
  if (!error) return null
  const { code, message, details } = norm(error)
  const lines = Object.entries(details || {}).flatMap(([k, v]) =>
    (Array.isArray(v) ? v : [String(v)]).map((m) => (k === 'non_field_errors' ? String(m) : `${lbl(k)}: ${m}`)))
  return (
    <div className="alert alert-danger" role="alert">
      <div>{message || 'Something went wrong.'}</div>
      {code === 'validation_error' && lines.length > 0 && <ul>{lines.map((l, i) => <li key={i}>{l}</li>)}</ul>}
    </div>
  )
}

export const Check = ({ label, checked, onChange, disabled, hint }) => (
  <div>
    <label><input type="checkbox" checked={!!checked} onChange={onChange} disabled={disabled} /> {label}</label>
    {hint && <div className="hint">{hint}</div>}
  </div>
)

export const FilterSelect = ({ label, value, onChange, options }) => (
  <FormField label={label} name={label} as="select" options={withBlank(options, 'All')} value={value}
    onChange={(e) => onChange(e.target.value)} />
)

/** Generic form dialog: fields = [{name,label,as,type,required,initial,hint,options}]; onSubmit(values) may throw. */
export function ActionModal({ title, submitLabel = 'Save', danger, intro, fields = [], onSubmit, onDone, onClose, wide, children }) {
  const [v, setV] = useState(() => Object.fromEntries(fields.map((f) => [f.name, f.initial ?? ''])))
  const act = useAction()
  const submit = async () => {
    const r = await act.run(() => onSubmit(v))
    if (r.ok) onDone?.(r.data)
  }
  return (
    <Modal title={title} onClose={onClose} wide={wide}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant={danger ? 'danger' : 'primary'} loading={act.busy} onClick={submit}>{submitLabel}</Button></>}>
      {intro && <p>{intro}</p>}
      <ErrorBox error={act.error} />
      {children}
      {fields.map((f) => (
        <FormField key={f.name} label={f.label} name={f.name} as={f.as} type={f.type} required={f.required} hint={f.hint}
          options={f.options} value={v[f.name]} error={fieldError(act.error, f.name)}
          onChange={(e) => setV((s) => ({ ...s, [f.name]: e.target.value }))} />
      ))}
    </Modal>
  )
}

/** Searchable location select over the whole tree (no 100-row cap). Needs location.view. */
export function LocationSelect({ label = 'Location', value, onChange, error, required, hint }) {
  const { can } = useFacility()
  const allowed = can('location.view')
  const tree = useFetch('/locations/tree/', {}, allowed)
  const [q, setQ] = useState('')
  const flat = useMemo(() => {
    const out = []
    const walk = (nodes, path) => (nodes || []).forEach((n) => {
      const p = [...path, n.name]
      out.push({ value: n.public_id, label: `${n.code} – ${p.join(' › ')}` })
      walk(n.children, p)
    })
    walk(Array.isArray(tree.data) ? tree.data : [], [])
    return out
  }, [tree.data])
  if (!allowed) return <p className="muted">{label}: you need permission to view locations.</p>
  const shown = q ? flat.filter((o) => o.label.toLowerCase().includes(q.toLowerCase())) : flat
  let options = shown.slice(0, 200)
  if (value && !options.some((o) => o.value === value)) {
    const cur = flat.find((o) => o.value === value)
    if (cur) options = [cur, ...options]
  }
  return (
    <div>
      <input placeholder={`Filter ${label.toLowerCase()} list…`} value={q} onChange={(e) => setQ(e.target.value)} />
      <FormField label={label} name={label} as="select" required={required} hint={hint || (shown.length > 200 ? 'Showing 200 of many; type to narrow.' : undefined)}
        options={withBlank(options, 'Select location…')} value={value || ''} error={error} onChange={(e) => onChange(e.target.value)} />
    </div>
  )
}

export const deptOption = (x) => ({ value: x.public_id, label: x.name })
