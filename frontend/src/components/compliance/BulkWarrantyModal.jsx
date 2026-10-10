import { useState } from 'react'
import { Button, FormError, FormField, Modal } from '../ui'
import { api, equipmentOption, fieldError, nn, useForm, useOptions, useSubmit, vendorOption, withBlank } from './shared'

export default function BulkWarrantyModal({ onClose, onDone }) {
  const equipment = useOptions('/equipment/', equipmentOption)
  const vendors = useOptions('/vendors/', vendorOption)
  const [picked, setPicked] = useState([])
  const [q, setQ] = useState('')
  const [created, setCreated] = useState(null)
  const { busy, error, run } = useSubmit()
  const { v, bind } = useForm({
    vendor: '', warranty_type: 'STANDARD', start_date: '', mode: 'months', duration_months: 12, end_date: '',
    reference_number: '', coverage_terms: '', exclusions: '',
  })
  const fe = (n) => fieldError(error, n)
  const shown = equipment.filter((e) => e.label.toLowerCase().includes(q.toLowerCase()))
  const toggle = (id) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]))

  const go = () => run(async () => {
    const body = {
      equipment: picked, vendor: nn(v.vendor), warranty_type: v.warranty_type, start_date: nn(v.start_date),
      reference_number: nn(v.reference_number), coverage_terms: nn(v.coverage_terms), exclusions: nn(v.exclusions),
      ...(v.mode === 'months' ? { duration_months: Number(v.duration_months) } : { end_date: v.end_date }),
    }
    const r = await api.post('/warranties/bulk/', body)
    setCreated(r.data.created)
  })

  return (
    <Modal wide title="Add warranties for several equipment" onClose={created != null ? onDone : onClose}
      footer={created != null ? <Button onClick={onDone}>Close</Button> : <>
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button onClick={go} loading={busy} disabled={!picked.length}>Create {picked.length || ''}</Button></>}>
      {created != null ? <p>{created} warranties created.</p> : (<>
        <FormError error={error} />
        {fe('equipment') && <p role="alert">{String(fe('equipment'))}</p>}
        <FormField label="Find equipment" name="q" value={q} onChange={(e) => setQ(e.target.value)} />
        <div style={{ maxHeight: 180, overflowY: 'auto', border: '1px solid var(--border, #ddd)', padding: 6 }}>
          {shown.map((e) => (
            <label key={e.value} style={{ display: 'block' }}>
              <input type="checkbox" checked={picked.includes(e.value)} onChange={() => toggle(e.value)} /> {e.label}
            </label>
          ))}
        </div>
        <p>{picked.length} selected (max 200). All are created together or none.</p>
        <FormField label="Vendor" as="select" options={withBlank(vendors, 'None')} {...bind('vendor')} />
        <FormField label="Type" as="select" options={[{ value: 'STANDARD', label: 'Standard' }, { value: 'EXTENDED', label: 'Extended' }]} {...bind('warranty_type')} />
        <FormField label="Start date" type="date" hint="Leave empty to use each equipment's acceptance date" error={fe('start_date')} {...bind('start_date')} />
        <FormField label="Length" as="select" options={[{ value: 'months', label: 'Months from start' }, { value: 'date', label: 'Fixed end date' }]} {...bind('mode')} />
        {v.mode === 'months'
          ? <FormField label="Months" type="number" min="1" error={fe('duration_months')} {...bind('duration_months')} />
          : <FormField label="End date" type="date" error={fe('end_date')} {...bind('end_date')} />}
        <FormField label="Reference number" {...bind('reference_number')} />
        <FormField label="Coverage terms" as="textarea" {...bind('coverage_terms')} />
        <FormField label="Exclusions" as="textarea" {...bind('exclusions')} />
      </>)}
    </Modal>
  )
}