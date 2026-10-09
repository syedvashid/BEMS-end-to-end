export const WO_STATUSES = ['OPEN', 'ASSIGNED', 'IN_PROGRESS', 'WAITING_PARTS', 'COMPLETED', 'CLOSED', 'CANCELLED']
export const STATUS_LABEL = {
  OPEN: 'Open', ASSIGNED: 'Assigned', IN_PROGRESS: 'In progress', WAITING_PARTS: 'Waiting for parts',
  COMPLETED: 'Completed', CLOSED: 'Closed', CANCELLED: 'Cancelled',
}
export const PRIORITIES = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
export const PRIORITY_LABEL = { LOW: 'Low', MEDIUM: 'Medium', HIGH: 'High', CRITICAL: 'Critical' }
export const WO_TYPES = ['PREVENTIVE', 'BREAKDOWN', 'CORRECTIVE']
export const TYPE_LABEL = { PREVENTIVE: 'Preventive', BREAKDOWN: 'Breakdown', CORRECTIVE: 'Corrective' }
export const COVERAGE = ['WARRANTY', 'AMC', 'PAID', 'IN_HOUSE']
export const COVERAGE_LABEL = { WARRANTY: 'Warranty', AMC: 'AMC', PAID: 'Paid', IN_HOUSE: 'In-house' }

// [{value,label}] for FormField selects; `blank` adds an empty first option.
export const opts = (list, labels, blank) => [
  ...(blank ? [{ value: '', label: blank }] : []),
  ...list.map((v) => ({ value: v, label: (labels && labels[v]) || v })),
]

// Normalised API error: { status, code, message, details }
export const apiError = (e) => {
  const b = e?.response?.data?.error
  return {
    status: e?.response?.status,
    code: b?.code,
    message: b?.message || 'Something went wrong. Please try again.',
    details: b?.details || {},
  }
}
export const fe = (err, name) => {
  const d = err?.details?.[name]
  return Array.isArray(d) ? d[0] : d
}
// Clear message for the three 409 kinds, otherwise the server message.
export const errorText = (err) => {
  if (!err) return ''
  if (err.code === 'stale_version') return 'This record was changed by someone else. Reload it and try again.'
  if (err.code === 'insufficient_stock') return `Not enough stock. Available: ${err.details?.available ?? '0'}.`
  return err.message
}
export const toNull = (v) => (v === '' || v === undefined ? null : v)
export const num = (v) => (v === null || v === undefined || v === '' ? null : Number(v))
export const money = (v) => (v === null || v === undefined ? '—' : Number(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }))

// <input type="datetime-local"> <-> ISO
export const toLocalInput = (iso) => {
  if (!iso) return ''
  const d = new Date(iso)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
}
export const fromLocalInput = (v) => (v ? new Date(v).toISOString() : null)
export const ymd = (d) => {
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}
export const outOfRange = (r) => {
  if (r.item_type !== 'MEASUREMENT' || r.measured_value === '' || r.measured_value === null || r.measured_value === undefined) return false
  const v = Number(r.measured_value)
  return (r.min_value !== null && r.min_value !== undefined && v < Number(r.min_value))
    || (r.max_value !== null && r.max_value !== undefined && v > Number(r.max_value))
}
