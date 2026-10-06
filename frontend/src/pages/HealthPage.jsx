// HealthPage.jsx
import { StatusBadge } from '../components/ui'
import useFetch from '../hooks/useFetch'

export default function HealthPage() {
  const q = useFetch('/health/')
  return (
    <>
      <div className="page-head"><h1>API health</h1></div>
      {q.loading && <p className="muted">Checking…</p>}
      {q.error && <div className="alert alert-danger">{q.error.message}</div>}
      {q.data && <StatusBadge tone={q.data.status === 'ok' ? 'success' : 'danger'}>{q.data.status}</StatusBadge>}
    </>
  )
}