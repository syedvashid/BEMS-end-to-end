import { fmtMoney, fmtNum } from '../finance/shared.jsx'

export const PALETTE = ['var(--rp-c1)', 'var(--rp-c2)', 'var(--rp-c3)', 'var(--rp-c4)', 'var(--rp-c5)', 'var(--rp-c6)', 'var(--rp-c7)', 'var(--rp-c8)']

export function valueFormatter(format) {
  switch (format) {
    case 'money': return (v) => fmtMoney(v)
    case 'percent': return (v) => (v === null || v === undefined ? '—' : `${fmtNum(v, 2)}%`)
    case 'hours': return (v) => (v === null || v === undefined ? '—' : `${fmtNum(v, 1)} h`)
    default: return (v) => fmtNum(v, 2)
  }
}

export const shorten = (s, n = 18) => {
  const t = String(s ?? '')
  return t.length > n ? `${t.slice(0, n - 1)}…` : t
}
