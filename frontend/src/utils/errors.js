// Normalises the standard error shape {"error": {"code","message","details"}}.
export function parseApiError(err) {
  const res = err?.response
  if (!res) {
    return { status: 0, code: 'network_error', message: 'Cannot reach the server. Check your connection and try again.', details: {} }
  }
  const e = res.data?.error
  return {
    status: res.status,
    code: e?.code ?? 'error',
    message: e?.message ?? 'Something went wrong.',
    details: e?.details ?? {},
  }
}

export function fieldError(error, name) {
  const d = error?.details?.[name]
  if (Array.isArray(d)) return d.join(' ')
  return d ? String(d) : undefined
}

export function cleanParams(params) {
  return Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== '' && v !== undefined && v !== null && v !== false),
  )
}