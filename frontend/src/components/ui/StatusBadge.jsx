export default function StatusBadge({ tone = 'neutral', children }) {
  return <span className={`badge badge-${tone}`}>{children}</span>
}

export function ActiveBadge({ active }) {
  return <StatusBadge tone={active ? 'success' : 'danger'}>{active ? 'Active' : 'Inactive'}</StatusBadge>
}