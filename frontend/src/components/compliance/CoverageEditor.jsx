import { useState } from 'react'
import { Button, FormError } from '../ui'
import { api, equipmentOption, useOptions, useSubmit, withBlank } from './shared'

/** Covered equipment + allocated cost. Saved as a whole set (PUT). */
export default function CoverageEditor({ contract, coverage, canChange, onSaved }) {
  const options = useOptions('/equipment/', equipmentOption, { lifecycle_stage: 'COMMISSIONED' })
  const [rows, setRows] = useState((coverage || []).map((c) => ({ equipment: c.equipment.public_id, label: `${c.equipment.asset_tag} — ${c.equipment.name}`, cost: c.allocated_cost ?? '' })))
  const [adding, setAdding] = useState('')
  const { busy, error, run } = useSubmit()
  const total = rows.reduce((s, r) => s + (Number(r.cost) || 0), 0)

  const add = (id) => {
    const o = options.find((x) => x.value === id)
    if (o && !rows.some((r) => r.equipment === id)) setRows([...rows, { equipment: id, label: o.label, cost: '' }])
    setAdding('')
  }
  const save = () => run(async () => {
    await api.put(`/amc-contracts/${contract.public_id}/coverage/`, {
      items: rows.map((r) => ({ equipment: r.equipment, allocated_cost: r.cost === '' ? null : r.cost })),
    })
    onSaved()
  })
  return (
    <div>
      <h4>Covered equipment</h4>
      <FormError error={error} />
      {rows.length === 0 && <p>No equipment covered yet.</p>}
      {rows.map((r, i) => (
        <div key={r.equipment} style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
          <span style={{ flex: 1 }}>{r.label}</span>
          <input type="number" min="0" step="0.01" placeholder="Allocated cost" value={r.cost} disabled={!canChange}
            onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, cost: e.target.value } : x)))} aria-label={`Allocated cost ${r.label}`} />
          {canChange && <button type="button" onClick={() => setRows(rows.filter((_, j) => j !== i))} aria-label="Remove">✕</button>}
        </div>
      ))}
      {total > Number(contract.contract_cost) && <p role="alert">Allocated costs ({total}) exceed the contract cost ({contract.contract_cost}).</p>}
      {canChange && (<>
        <select value={adding} onChange={(e) => add(e.target.value)} aria-label="Add equipment">
          {withBlank(options, 'Add equipment…').map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>{' '}
        <Button size="sm" onClick={save} loading={busy}>Save coverage</Button>
      </>)}
    </div>
  )
}