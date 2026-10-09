import { STAGE_LABELS, STATE_LABELS } from '../utils/equipment'

export function StageBadge({ value }) {
  if (!value) return '—'
  return <span className={`eq-badge eq-badge-${value.toLowerCase()}`}>{STAGE_LABELS[value] || value}</span>
}

export function StateBadge({ value }) {
  if (!value) return '—'
  return <span className={`eq-badge eq-badge-${value.toLowerCase()}`}>{STATE_LABELS[value] || value}</span>
}
