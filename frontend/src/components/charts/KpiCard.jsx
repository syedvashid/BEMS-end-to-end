import { valueFormatter } from './format.js'

export default function KpiCard({ title, value, format = 'number', hint }) {
  const text = value === null || value === undefined ? '—' : valueFormatter(format)(value)
  return (
    <div className="rp-kpi" role="group" aria-label={title}>
      <div className="rp-kpi-title">{title}</div>
      <div className="rp-kpi-value">{text}</div>
      {hint && <div className="rp-kpi-hint">{hint}</div>}
    </div>
  )
}
