export default function Table({ columns, rows, rowKey = 'public_id', loading = false, empty = 'No records found.', onRowClick }) {
  const list = rows ?? []
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>{columns.map((c) => <th key={c.key}>{c.header}</th>)}</tr>
        </thead>
        <tbody>
          {list.length === 0 ? (
            <tr><td colSpan={columns.length} className="muted">{loading ? 'Loading…' : empty}</td></tr>
          ) : (
            list.map((row) => (
              <tr key={row[rowKey]} className={onRowClick ? 'clickable' : undefined} onClick={onRowClick ? () => onRowClick(row) : undefined}>
                {columns.map((c) => (
                  <td key={c.key} className={c.className}>{c.render ? c.render(row) : (row[c.key] ?? '—')}</td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}