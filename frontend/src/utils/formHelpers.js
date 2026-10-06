export function toForm(empty, rec) {
  const out = { ...empty }
  if (rec) for (const k of Object.keys(empty)) out[k] = rec[k] ?? (typeof empty[k] === 'boolean' ? false : '')
  return out
}

// '' -> null; keys in `numeric` become numbers; booleans pass through.
export function toPayload(form, numeric = []) {
  const p = {}
  for (const [k, v] of Object.entries(form)) {
    if (typeof v === 'boolean') { p[k] = v; continue }
    const t = String(v ?? '').trim()
    p[k] = t === '' ? null : numeric.includes(k) ? Number(t) : t
  }
  return p
}

export const opts = (arr, all) =>
  (all ? [{ value: '', label: all }] : []).concat(arr.map((v) => ({ value: v, label: v.replace(/_/g, ' ') })))

export const dash = (v) => (v === null || v === undefined || v === '' ? '—' : v)