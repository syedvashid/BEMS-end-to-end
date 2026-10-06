import Button from './Button'

export default function Pagination({ page, pageSize, count, onPageChange }) {
  const pages = Math.max(1, Math.ceil(count / pageSize))
  return (
    <div className="pagination">
      <span className="muted">{count} record{count === 1 ? '' : 's'}</span>
      <div className="row">
        <Button size="sm" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>Previous</Button>
        <span>Page {page} of {pages}</span>
        <Button size="sm" disabled={page >= pages} onClick={() => onPageChange(page + 1)}>Next</Button>
      </div>
    </div>
  )
}