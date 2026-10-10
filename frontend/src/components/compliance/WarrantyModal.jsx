import { Button, FormError, FormField, Modal } from '../ui'
import DocumentsPanel from '../DocumentsPanel'
import ClaimsSection from './ClaimsSection'
import { ConflictNote, api, equipmentOption, fieldError, nn, useForm, useOptions, useSubmit, vendorOption, withBlank } from './shared'

const TYPES = [{ value: 'STANDARD', label: 'Standard' }, { value: 'EXTENDED', label: 'Extended' }]

export default function WarrantyModal({ warranty, presetEquipment, canDelete, onClose, onSaved }) {
  const editing = !!warranty
  const equipment = useOptions('/equipment/', equipmentOption)
  const vendors = useOptions('/vendors/', vendorOption)
  const { busy, error, run } = useSubmit()
  const { v, bind } = useForm({
    equipment: warranty?.equipment ?? presetEquipment ?? '', vendor: warranty?.vendor ?? '',
    warranty_type: warranty?.warranty_type ?? 'STANDARD', start_date: warranty?.start_date ?? '', end_date: warranty?.end_date ?? '',
    reference_number: warranty?.reference_number ?? '', coverage_terms: warranty?.coverage_terms ?? '',
    covered_parts: warranty?.covered_parts ?? '', exclusions: warranty?.exclusions ?? '', notes: warranty?.notes ?? '',
  })
  const fe = (n) => fieldError(error, n)
  const save = () => run(async () => {
    const body = {
      vendor: nn(v.vendor), warranty_type: v.warranty_type, start_date: v.start_date, end_date: v.end_date,
      reference_number: nn(v.reference_number), coverage_terms: nn(v.coverage_terms), covered_parts: nn(v.covered_parts),
      exclusions: nn(v.exclusions), notes: nn(v.notes),
    }
    if (editing) await api.patch(`/warranties/${warranty.public_id}/`, { ...body, row_version: warranty.row_version })
    else await api.post('/warranties/', { ...body, equipment: v.equipment })
    onSaved()
  })
  const remove = () => run(async () => {
    await api.delete(`/warranties/${warranty.public_id}/`, { params: { row_version: warranty.row_version } })
    onSaved()
  })
  return (
    <Modal wide title={editing ? `Warranty — ${warranty.equipment_asset_tag}` : 'New warranty'} onClose={onClose}
      footer={<>
        {editing && canDelete && <Button variant="danger" onClick={remove} loading={busy}>Delete</Button>}
        <Button variant="secondary" onClick={onClose}>Close</Button>
        <Button onClick={save} loading={busy}>Save</Button></>}>
      <FormError error={error} /><ConflictNote error={error} />
      {!editing && !presetEquipment && <FormField label="Equipment" as="select" required options={withBlank(equipment)} error={fe('equipment')} {...bind('equipment')} />}
      <FormField label="Vendor" as="select" options={withBlank(vendors, 'None')} error={fe('vendor')} {...bind('vendor')} />
      <FormField label="Type" as="select" options={TYPES} error={fe('warranty_type')} {...bind('warranty_type')} />
      <FormField label="Start date" type="date" required error={fe('start_date')} {...bind('start_date')} />
      <FormField label="End date" type="date" required error={fe('end_date')} {...bind('end_date')} />
      <FormField label="Reference number" error={fe('reference_number')} {...bind('reference_number')} />
      <FormField label="Coverage terms" as="textarea" error={fe('coverage_terms')} {...bind('coverage_terms')} />
      <FormField label="Covered parts" as="textarea" error={fe('covered_parts')} {...bind('covered_parts')} />
      <FormField label="Exclusions" as="textarea" error={fe('exclusions')} {...bind('exclusions')} />
      <FormField label="Notes" as="textarea" error={fe('notes')} {...bind('notes')} />
      {editing && (<>
        <ClaimsSection warranty={warranty} />
        <h4>Documents</h4>
        <DocumentsPanel entityType="warranty" entityId={warranty.public_id} />
      </>)}
    </Modal>
  )
}