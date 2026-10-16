import './reports.css'
import * as client from '../../api/client'
import useFetch from '../../hooks/useFetch'
import { usePermission } from '../compliance/shared.jsx'

export { useFetch, usePermission }
export { apiError, ErrorNote, fmtMoney, fmtNum, fmtDay, fmtStamp, lbl, clean, withBlank } from '../finance/shared.jsx'

// src/api/client.js exports the axios instance (named or default); accept both.
export const api = client.api || client.default

export const isoDay = (d) => d.toISOString().slice(0, 10)
export const daysAgo = (n) => { const d = new Date(); d.setDate(d.getDate() - n); return isoDay(d) }

// Hooks are called in a fixed order for a fixed list, so this is safe.
export function useCanAny(codes) {
  const flags = codes.map((c) => usePermission(c)) // eslint-disable-line react-hooks/rules-of-hooks
  return flags.some(Boolean)
}

export function downloadFromUrl(url) {
  const a = document.createElement('a')
  a.href = url
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
}

export function useMasterOptions(path, label = (r) => r.name, blank = 'All') {
  const res = useFetch(path, { page_size: 100 })
  const rows = res.data?.results || []
  return [{ value: '', label: blank }, ...rows.map((r) => ({ value: r.public_id, label: label(r) }))]
}

// Backend error body -> readable lines (message + field details such as non_field_errors).
export function errorLines(err) {
  if (!err) return []
  const lines = [err.message || 'Something went wrong.']
  const details = err.details || err.fields || {}
  Object.entries(details).forEach(([k, v]) => {
    if (k === 'blockers') return
    lines.push(`${k === 'non_field_errors' ? '' : `${k}: `}${Array.isArray(v) ? v.join(' ') : v}`)
  })
  return lines
}

export function FetchError({ error }) {
  if (!error) return null
  const lines = errorLines(error)
  return (
    <div className="alert alert-danger">
      {lines[0]}
      {lines.length > 1 && <ul>{lines.slice(1).map((l) => <li key={l}>{l}</li>)}</ul>}
    </div>
  )
}
