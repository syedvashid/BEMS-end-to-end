import { useState } from 'react'
import { Link } from 'react-router-dom'
import EquipmentFields, { buildPayload, emptyForm } from '../components/EquipmentFields'
import { Button, FormField, Table } from '../components/ui'
import { api } from '../api/client'
import { fieldError, parseApiError } from '../utils/errors'
import { friendly } from '../utils/equipment'

export default function EquipmentBulkPage() {
  const [f, setF] = useState(emptyForm)
  const [quantity, setQuantity] = useState('1')
  const [serials, setSerials] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [created, setCreated] = useState(null)

  const submit = async () => {
    setBusy(true); setErr(null)
    const lines = serials.split('\n').map((s) => s.trim())
    while (lines.length && !lines[lines.length - 1]) lines.pop()
    const body = { ...buildPayload(f, { bulk: true }), quantity: Number(quantity) }
    if (lines.length) body.serial_numbers = lines
    try {
      const { data } = await api.post('/equipment/bulk-create/', body)
      setCreated(data.results)
    } catch (e) { setErr(parseApiError(e)) }
    setBusy(false)
  }

  if (created) {
    return (
      <section>
        <div className="page-head"><h2>Created {created.length} units</h2><span className="spacer" />
          <Link to="/equipment">Back to equipment</Link></div>
        <Table columns={[
          { key: 'asset_tag', header: 'Asset tag', render: (r) => <Link to={`/equipment/${r.public_id}`}>{r.asset_tag}</Link> },
          { key: 'name', header: 'Name' },
        ]} rows={created} />
      </section>
    )
  }

  return (
    <section>
      <div className="page-head"><h2>Bulk add equipment</h2><span className="spacer" />
        <Link to="/equipment">Cancel</Link></div>
      {err && err.code !== 'validation_error' && <div className="alert alert-danger">{friendly(err)}</div>}
      <FormField label="Quantity (1-200)" name="quantity" type="number" required value={quantity}
        onChange={(e) => setQuantity(e.target.value)} error={fieldError(err, 'quantity')} />
      <FormField label="Serial numbers" name="serial_numbers" as="textarea" value={serials}
        onChange={(e) => setSerials(e.target.value)} error={fieldError(err, 'serial_numbers')}
        hint="Optional. One per line; if given, the number of lines must equal the quantity." />
      <EquipmentFields f={f} setF={setF} err={err} bulk />
      <Button variant="primary" loading={busy} onClick={submit}>Create units</Button>
    </section>
  )
}
