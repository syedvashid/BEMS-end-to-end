import { api } from '../api/client'

export const DOCUMENT_TYPES = [
  { value: 'MANUAL', label: 'Manual' }, { value: 'INVOICE', label: 'Invoice' },
  { value: 'PURCHASE_ORDER', label: 'Purchase order' }, { value: 'GRN', label: 'GRN' },
  { value: 'WARRANTY_CARD', label: 'Warranty card' }, { value: 'INSTALLATION_REPORT', label: 'Installation report' },
  { value: 'ACCEPTANCE_REPORT', label: 'Acceptance report' }, { value: 'SERVICE_REPORT', label: 'Service report' },
  { value: 'CALIBRATION_CERTIFICATE', label: 'Calibration certificate' }, { value: 'CONTRACT', label: 'Contract' },
  { value: 'LICENSE', label: 'Licence' }, { value: 'REGISTRATION_CERTIFICATE', label: 'Registration certificate' },
  { value: 'PHOTO', label: 'Photo' }, { value: 'OTHER', label: 'Other' },
]
export const ENTITY_TYPES = [
  { value: 'vendor', label: 'Vendor' },
  { value: 'equipment_model', label: 'Equipment model' },
]
export const INLINE_TYPES = ['application/pdf', 'image/png', 'image/jpeg']
export const MAX_UPLOAD_MB = 20
const ALLOWED_EXT = ['pdf', 'jpg', 'jpeg', 'png', 'docx', 'xlsx']

export const typeLabel = (v) => DOCUMENT_TYPES.find((t) => t.value === v)?.label ?? v
export const entityLabel = (v) => ENTITY_TYPES.find((t) => t.value === v)?.label ?? v
export const fmtDate = (s) => (s ? new Date(s).toLocaleDateString('en-IN') : '—')
export const formatBytes = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`)

// 'expired' | 'soon' (within 30 days) | null
export function expiryStatus(date) {
  if (!date) return null
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const days = Math.round((new Date(`${date}T00:00:00`) - today) / 86400000)
  if (days < 0) return 'expired'
  return days <= 30 ? 'soon' : null
}

// Convenience only; the server re-validates type, size and content.
export function checkFile(file) {
  if (!file) return 'Choose a file.'
  const ext = file.name.includes('.') ? file.name.split('.').pop().toLowerCase() : ''
  if (!ALLOWED_EXT.includes(ext)) return 'File type not allowed. Allowed: PDF, JPG, PNG, DOCX, XLSX.'
  if (file.size === 0) return 'The file is empty.'
  if (file.size > MAX_UPLOAD_MB * 1048576) return `File is too large. Maximum size is ${MAX_UPLOAD_MB} MB.`
  return null
}

// e = normalised error from parseApiError
export function friendlyError(e) {
  if (!e) return null
  if (e.code === 'stale_version') return 'This document was changed by someone else. The list was refreshed, please try again.'
  if (e.status === 404 || e.code === 'not_found') return 'The record or document was not found. It may have been removed.'
  return e.message || 'Something went wrong.'
}

const absolute = (url) => {
  const base = api.defaults.baseURL || ''
  return /^https?:/i.test(base) ? new URL(url, base).href : url
}

// Asks the server for a short-lived link, then opens it. Inline = preview in a new tab.
export async function openDocumentLink(docId, versionNo, inline) {
  const win = inline ? window.open('about:blank', '_blank') : null
  if (win) win.opener = null
  try {
    const r = await api.post(`/documents/${docId}/versions/${versionNo}/download-link/`, null,
      { params: inline ? { inline: 'true' } : undefined })
    const url = absolute(r.data.url)
    if (inline) { if (win) win.location.href = url; else window.open(url, '_blank') } else window.location.assign(url)
  } catch (e) {
    if (win) win.close()
    throw e
  }
}