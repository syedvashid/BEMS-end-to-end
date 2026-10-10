const COLS = [['parameter', 'Parameter'], ['nominal', 'Nominal'], ['measured', 'Measured'], ['unit', 'Unit'], ['tolerance', 'Tolerance']]
export const emptyReading = () => ({ parameter: '', nominal: '', measured: '', unit: '', tolerance: '' })

/** Rows of parameter / nominal / measured / unit / tolerance. Max 50 rows (server limit). */
export default function ReadingsEditor({ rows, onChange }) {
  const set = (i, k, val) => onChange(rows.map((r, j) => (j === i ? { ...r, [k]: val } : r)))
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%' }}>
        <thead><tr>{COLS.map(([k, h]) => <th key={k} style={{ textAlign: 'left' }}>{h}</th>)}<th /></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {COLS.map(([k]) => (
                <td key={k}><input value={r[k]} maxLength={k === 'parameter' ? 100 : 50} style={{ width: '100%' }}
                  onChange={(e) => set(i, k, e.target.value)} aria-label={`${k} ${i + 1}`} /></td>
              ))}
              <td><button type="button" onClick={() => onChange(rows.filter((_, j) => j !== i))} aria-label="Remove reading">✕</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length < 50 && <button type="button" onClick={() => onChange([...rows, emptyReading()])}>+ Add reading</button>}
    </div>
  )
}