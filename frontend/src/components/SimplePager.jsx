import { Button } from './ui'

export default function SimplePager({ page, count, pageSize = 20, onPage }) {
  const pages = Math.max(1, Math.ceil((count || 0) / pageSize))
  return (
    <div className="row">
      <Button size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</Button>
      <span className="muted">Page {page} of {pages} ({count || 0} records)</span>
      <Button size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</Button>
    </div>
  )
}
