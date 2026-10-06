export default function RiskBadge({ value }) {
  if (!value) return '—'
  return <span className={`risk-badge risk-${value.toLowerCase()}`}>{value}</span>
}