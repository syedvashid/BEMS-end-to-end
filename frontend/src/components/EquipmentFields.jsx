import { FormField } from './ui'
import { fieldError } from '../utils/errors'
import {
  CRITICALITY_OPTIONS, OWNERSHIP_OPTIONS, codeName, useMasterOptions,
} from '../utils/equipment'

export const emptyForm = () => ({
  equipment_model: '', name: '', serial_number: '', legacy_asset_id: '', ownership_type: 'OWNED',
  owner_vendor: '', ownership_end_date: '', funding_source: '', supplier_vendor: '', owning_department: '',
  current_location: '', criticality: 'MEDIUM', purchase_order_number: '', purchase_order_date: '',
  grn_number: '', grn_date: '', invoice_number: '', invoice_date: '', purchase_cost: '', installation_cost: '',
  expected_life_years: '', notes: '', attrs: [],
})

const OPTIONAL = [
  'serial_number', 'legacy_asset_id', 'owner_vendor', 'ownership_end_date', 'funding_source', 'supplier_vendor',
  'owning_department', 'current_location', 'purchase_order_number', 'purchase_order_date', 'grn_number', 'grn_date',
  'invoice_number', 'invoice_date', 'purchase_cost', 'installation_cost', 'notes',
]

const parseValue = (v) => {
  const s = String(v).trim()
  if (s === 'true') return true
  if (s === 'false') return false
  if (s !== '' && /^-?\d+(\.\d+)?$/.test(s)) return Number(s)
  return s
}

// Optional fields send null instead of ""; name is omitted when empty so the server defaults it.
export function buildPayload(f, { bulk = false } = {}) {
  const body = {
    equipment_model: f.equipment_model, ownership_type: f.ownership_type, criticality: f.criticality,
    custom_attributes: Object.fromEntries(
      f.attrs.filter((a) => a.k.trim()).map((a) => [a.k.trim(), parseValue(a.v)])),
    expected_life_years: f.expected_life_years === '' ? null : Number(f.expected_life_years),
  }
  OPTIONAL.forEach((k) => {
    if (bulk && (k === 'serial_number' || k === 'legacy_asset_id')) return
    const v = typeof f[k] === 'string' ? f[k].trim() : f[k]
    body[k] = v === '' ? null : v
  })
  if (!bulk && f.name.trim()) body.name = f.name.trim()
  return body
}

export default function EquipmentFields({ f, setF, err, bulk = false }) {
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }))
  const models = useMasterOptions('/equipment-models/', (m) => `${m.model_name} (${m.model_number})`)
  const depts = useMasterOptions('/departments/', codeName)
  const locs = useMasterOptions('/locations/', codeName)
  const vendors = useMasterOptions('/vendors/', (v) => v.name)
  const funds = useMasterOptions('/funding-sources/', codeName)
  const E = (k) => fieldError(err, k)

  const onModel = (e) => {
    const id = e.target.value
    setF((x) => {
      const prev = models.rows.find((m) => m.public_id === x.equipment_model)
      const next = models.rows.find((m) => m.public_id === id)
      const auto = !x.name || (prev && x.name === prev.model_name)
      return { ...x, equipment_model: id, name: auto ? (next?.model_name ?? '') : x.name }
    })
  }
  const setAttr = (i, k) => (e) => setF((x) => ({ ...x, attrs: x.attrs.map((a, j) => (j === i ? { ...a, [k]: e.target.value } : a)) }))

  return (
    <>
      <FormField label="Equipment model" name="equipment_model" as="select" required options={models.options}
        value={f.equipment_model} onChange={onModel} error={E('equipment_model')} />
      {!bulk && (
        <>
          <FormField label="Name" name="name" value={f.name} onChange={set('name')} error={E('name')}
            hint="Prefilled from the model" />
          <FormField label="Serial number" name="serial_number" value={f.serial_number}
            onChange={set('serial_number')} error={E('serial_number')} />
          <FormField label="Legacy asset ID" name="legacy_asset_id" value={f.legacy_asset_id}
            onChange={set('legacy_asset_id')} error={E('legacy_asset_id')} hint="The hospital's old tag, optional" />
        </>
      )}
      <FormField label="Criticality" name="criticality" as="select" options={CRITICALITY_OPTIONS}
        value={f.criticality} onChange={set('criticality')} error={E('criticality')} />
      <FormField label="Ownership" name="ownership_type" as="select" options={OWNERSHIP_OPTIONS}
        value={f.ownership_type} onChange={set('ownership_type')} error={E('ownership_type')} />
      {f.ownership_type !== 'OWNED' && (
        <>
          <FormField label="Owner vendor" name="owner_vendor" as="select" required options={vendors.options}
            value={f.owner_vendor} onChange={set('owner_vendor')} error={E('owner_vendor')} />
          <FormField label="Ownership end date" name="ownership_end_date" type="date"
            value={f.ownership_end_date} onChange={set('ownership_end_date')} error={E('ownership_end_date')} />
        </>
      )}
      <FormField label="Funding source" name="funding_source" as="select" options={funds.options}
        value={f.funding_source} onChange={set('funding_source')} error={E('funding_source')} />
      <FormField label="Supplier" name="supplier_vendor" as="select" options={vendors.options}
        value={f.supplier_vendor} onChange={set('supplier_vendor')} error={E('supplier_vendor')} />
      <FormField label="Department" name="owning_department" as="select" options={depts.options}
        value={f.owning_department} onChange={set('owning_department')} error={E('owning_department')} />
      <FormField label="Location" name="current_location" as="select" options={locs.options}
        value={f.current_location} onChange={set('current_location')} error={E('current_location')}
        hint="Required when a department is chosen" />

      <h3>Procurement</h3>
      <FormField label="PO number" name="purchase_order_number" value={f.purchase_order_number}
        onChange={set('purchase_order_number')} error={E('purchase_order_number')} />
      <FormField label="PO date" name="purchase_order_date" type="date" value={f.purchase_order_date}
        onChange={set('purchase_order_date')} error={E('purchase_order_date')} />
      <FormField label="GRN number" name="grn_number" value={f.grn_number} onChange={set('grn_number')} error={E('grn_number')} />
      <FormField label="GRN date" name="grn_date" type="date" value={f.grn_date} onChange={set('grn_date')} error={E('grn_date')} />
      <FormField label="Invoice number" name="invoice_number" value={f.invoice_number}
        onChange={set('invoice_number')} error={E('invoice_number')} />
      <FormField label="Invoice date" name="invoice_date" type="date" value={f.invoice_date}
        onChange={set('invoice_date')} error={E('invoice_date')} />
      <FormField label="Purchase cost (INR)" name="purchase_cost" type="number" value={f.purchase_cost}
        onChange={set('purchase_cost')} error={E('purchase_cost')} />
      <FormField label="Installation cost (INR)" name="installation_cost" type="number" value={f.installation_cost}
        onChange={set('installation_cost')} error={E('installation_cost')} />
      <FormField label="Expected life (years)" name="expected_life_years" type="number" value={f.expected_life_years}
        onChange={set('expected_life_years')} error={E('expected_life_years')} hint="Overrides the model value" />
      <FormField label="Notes" name="notes" as="textarea" value={f.notes} onChange={set('notes')} error={E('notes')} />

      <h3>Custom attributes</h3>
      {f.attrs.map((a, i) => (
        <div className="row" key={i}>
          <input placeholder="Name" value={a.k} onChange={setAttr(i, 'k')} maxLength={40} />
          <input placeholder="Value" value={a.v} onChange={setAttr(i, 'v')} maxLength={200} />
          <button type="button" onClick={() => setF((x) => ({ ...x, attrs: x.attrs.filter((_, j) => j !== i) }))}>Remove</button>
        </div>
      ))}
      {E('custom_attributes') && <div className="alert alert-danger">{E('custom_attributes')}</div>}
      <button type="button" disabled={f.attrs.length >= 30}
        onClick={() => setF((x) => ({ ...x, attrs: [...x.attrs, { k: '', v: '' }] }))}>Add attribute</button>
    </>
  )
}
