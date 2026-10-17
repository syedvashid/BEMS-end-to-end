// Phase 11 shared helpers. Anything that depends on the shape of an existing shared component is wrapped here.
import { FormError, FormField, Pagination, StatusBadge } from '../ui'
import { parseApiError } from '../compliance/shared.jsx'

export { api, useFetch, usePermission, fieldError, parseApiError } from '../compliance/shared.jsx'

export const RULES = [
  { value: 'HOURLY', label: 'Hourly' },
  { value: 'DAILY', label: 'Daily' },
  { value: 'PER_USE', label: 'Per use (one per allocation)' },
  { value: 'PER_SESSION', label: 'Per session (one per usage log)' },
  { value: 'PER_ADMISSION', label: 'Per admission (one per encounter)' },
  { value: 'BUNDLED', label: 'Bundled (covered by a package)' },
  { value: 'DISABLED', label: 'Disabled (no charge)' },
]
export const RULE_LABEL = Object.fromEntries(RULES.map((r) => [r.value, r.label.split(' (')[0]]))
export const BASIS_LABEL = { ALLOCATION: 'Allocation', USAGE_LOG: 'Usage log' }
export const ALLOWED_BASES = {
  HOURLY: ['ALLOCATION', 'USAGE_LOG'], DAILY: ['ALLOCATION'], PER_USE: ['ALLOCATION'],
  PER_SESSION: ['USAGE_LOG'], PER_ADMISSION: ['ALLOCATION', 'USAGE_LOG'],
  BUNDLED: ['ALLOCATION', 'USAGE_LOG'], DISABLED: ['ALLOCATION', 'USAGE_LOG'],
}
// which mapping fields matter for which rule (same table as the backend serializer)
export const RULE_FIELDS = {
  HOURLY: ['rate_override', 'minimum_billable_minutes', 'grace_minutes', 'rounding', 'daily_cap_amount'],
  DAILY: ['rate_override', 'grace_minutes', 'day_block_mode'],
  PER_USE: ['rate_override'], PER_SESSION: ['rate_override'], PER_ADMISSION: ['rate_override'],
  BUNDLED: ['bundle_reference'], DISABLED: [],
}
export const STATUS = {
  PENDING_REVIEW: { label: 'Pending review', tone: 'warning' },
  APPROVED: { label: 'Approved', tone: 'success' },
  CANCELLED: { label: 'Cancelled', tone: 'neutral' },
  REVERSED: { label: 'Reversed', tone: 'danger' },
}

// Table may call render(row) or render(value, row): accept both.
export const rowOf = (a, b) => (b && typeof b === 'object' ? b : a)

export function inr(v) {
  if (v === null || v === undefined || v === '') return '-'
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2 }).format(Number(v))
}
export const fmtDT = (v) => (v ? new Date(v).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) : '-')
export const fmtD = (v) => (v ? new Date(`${String(v).slice(0, 10)}T00:00:00`).toLocaleDateString('en-IN', { dateStyle: 'medium' }) : '-')
export const todayStr = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10)
export const qty = (v) => (v === null || v === undefined ? '-' : String(Number(v)))

export function qs(obj) {
  const p = new URLSearchParams()
  Object.entries(obj).forEach(([k, v]) => { if (v !== '' && v !== null && v !== undefined) p.set(k, String(v)) })
  return p.toString()
}

export function errMessage(err) {
  const e = parseApiError(err)
  return typeof e === 'string' ? e : (e && e.message) || 'Something went wrong.'
}

export function Badge({ tone = 'neutral', children }) {
  return <StatusBadge tone={tone}>{children}</StatusBadge>
}
export const StatusPill = ({ status }) => <Badge tone={(STATUS[status] || {}).tone}>{(STATUS[status] || {}).label || status}</Badge>

// FormField wrapper: value/onChange are passed straight through; options are [{value, label}].
export function Field(props) {
  return <FormField {...props} />
}

// Accepts a parsed error (parseApiError / useSubmit) or a plain string.
export function ErrBox({ error }) {
  if (!error) return null
  if (typeof error === 'string') return <div role="alert" className="alert alert-danger">{error}</div>
  return <FormError error={error} />
}

export function Pager({ data, page, onPage }) {
  if (!data) return null
  return <Pagination page={page} pageSize={20} count={data.count ?? 0} onPageChange={onPage} />
}
