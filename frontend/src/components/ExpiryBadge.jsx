import { expiryStatus } from '../utils/documents'

export default function ExpiryBadge({ date }) {
  const s = expiryStatus(date)
  if (s === 'expired') return <span className="doc-badge doc-badge-expired">Expired</span>
  if (s === 'soon') return <span className="doc-badge doc-badge-soon">Expiring soon (30 days)</span>
  return null
}