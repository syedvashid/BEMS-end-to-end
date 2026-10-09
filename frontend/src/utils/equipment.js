import { useMemo } from 'react'
import { api } from '../api/client'
import useFetch from '../hooks/useFetch'

// Single place that defines the shape FormField expects for select options.
export const opt = (value, label) => ({ value, label })

export const STAGE_LABELS = {
  RECEIVED: 'Received', INSTALLED: 'Installed', COMMISSIONED: 'Commissioned',
  REJECTED: 'Rejected', CONDEMNED: 'Condemned', DISPOSED: 'Disposed',
}
export const STATE_LABELS = { IN_SERVICE: 'In service', UNDER_MAINTENANCE: 'Under maintenance', OUT_OF_SERVICE: 'Out of service' }
export const OWNERSHIP_OPTIONS = [
  opt('OWNED', 'Owned'), opt('LEASED', 'Leased'), opt('RENTAL', 'Rental'),
  opt('LOAN_DEMO', 'Loan / demo'), opt('VENDOR_PLACED', 'Vendor placed'),
]
export const CRITICALITY_OPTIONS = [opt('LOW', 'Low'), opt('MEDIUM', 'Medium'), opt('HIGH', 'High'), opt('CRITICAL', 'Critical')]
export const STATE_OPTIONS = Object.entries(STATE_LABELS).map(([v, l]) => opt(v, l))
export const BLANK = opt('', '—')

export const IMPORT_FIELDS = [
  ['manufacturer', 'Manufacturer', true], ['model_number', 'Model number', true], ['serial_number', 'Serial number'],
  ['name', 'Name'], ['department_code', 'Department code'], ['location_code', 'Location code', true],
  ['ownership_type', 'Ownership type'], ['owner_vendor_name', 'Owner vendor name'],
  ['funding_source_code', 'Funding source code'], ['supplier_name', 'Supplier name'],
  ['purchase_order_number', 'PO number'], ['purchase_order_date', 'PO date'], ['grn_number', 'GRN number'],
  ['grn_date', 'GRN date'], ['invoice_number', 'Invoice number'], ['invoice_date', 'Invoice date'],
  ['purchase_cost', 'Purchase cost (INR)'], ['installation_date', 'Installation date'],
  ['criticality', 'Criticality'], ['legacy_asset_id', 'Legacy asset ID'], ['operational_state', 'Operational state'],
  ['notes', 'Notes'],
]

const PAGE_100 = { page_size: 100 }   // stable reference so useFetch does not refetch every render

export function useMasterOptions(path, labelFn, enabled = true) {
  const res = useFetch(path, PAGE_100, enabled)
  const options = useMemo(
    // eslint-disable-next-line react-hooks/exhaustive-deps
    () => [BLANK, ...(res.data?.results || []).map((r) => opt(r.public_id, labelFn(r)))], [res.data])
  return { options, rows: res.data?.results || [] }
}

export const codeName = (r) => `${r.code} – ${r.name}`

export function friendly(err) {
  if (!err) return ''
  if (err.code === 'stale_version') return 'This record was changed by someone else. Close this dialog, reload and try again.'
  if (err.code === 'conflict') return err.message || 'This action is not allowed in the current state.'
  if (err.code === 'permission_denied') return 'You do not have permission to do this.'
  return err.message || 'Something went wrong.'
}

export const fmt = (v) => (v === null || v === undefined || v === '' ? '—' : String(v))
export const fmtDateTime = (v) => (v ? new Date(v).toLocaleString() : '—')

// Open a blob response in a new tab (window is opened first so popup blockers allow it).
export async function openBlob(request) {
  const w = window.open('', '_blank')
  try {
    const res = await api.request({ responseType: 'blob', ...request })
    const url = URL.createObjectURL(res.data)
    if (w) w.location.href = url
    else window.open(url, '_blank')
  } catch (e) {
    if (w) w.close()
    throw e
  }
}

export const labelsRequest = (ids) => ({ method: 'post', url: '/equipment/labels/', data: { equipment: ids } })
