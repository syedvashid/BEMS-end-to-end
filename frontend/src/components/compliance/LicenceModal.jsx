import { Button, FormError, FormField, Modal } from '../ui'
import DocumentsPanel from '../DocumentsPanel'
import { ConflictNote, api, equipmentOption, fieldError, nn, useForm, useOptions, useSubmit, withBlank } from './shared'

export const LICENCE_TYPES = [
  ['AERB_LICENCE', 'AERB licence'], ['AERB_QA_CERTIFICATE', 'AERB QA certificate'],
  ['PRESSURE_VESSEL_INSPECTION', 'Pressure vessel inspection'], ['ELECTRICAL_SAFETY_TEST', 'Electrical safety test'], ['OTHER', 'Other'],
].map(([value, label]) => ({ value, label }))

export default function LicenceModal({ licence, presetEquipment, canDelete, onClose, onSaved }) {
  const editing = !!licence
  const equipment = useOptions('/equipment/', equipmentOption)
  const { busy, error, run } = useSubmit()
  const { v, bind } = useForm({
    equipment: licence?.equipment ?? presetEquipment ?? '', licence_type: licence?.licence_type ?? 'AERB_LICENCE',
    licence_number: licence?.licence_number ?? '', issuing_authority: licence?.issuing_authority ?? '',
    issue_date: licence?.issue_date ?? '', expiry_date: licence?.expiry_date ?? '', notes: licence?.notes ?? '',
  })
  const fe = (n) => fieldError(error, n)
  const save = () => run(async () => {
    const body = {
      licence_type: v.licence_type, licence_number: nn(v.licence_number), issuing_authority: nn(v.issuing_authority),
      issue_date: v.issue_date, expiry_date: v.expiry_date, notes: nn(v.notes),
    }
    if (editing) await api.patch(`/equipment-licences/${licence.public_id}/`, { ...body, row_version: licence.row_version })
    else await api.post('/equipment-licences/', { ...body, equipment: v.equipment })
    onSaved()
  })
  const remove = () => run(async () => {
    await api.delete(`/equipment-licences/${licence.public_id}/`, { params: { row_version: licence.row_version } })
    onSaved()
  })
  return (
    <Modal title={editing ? `Licence — ${licence.equipment_asset_tag}` : 'New licence'} onClose={onClose}
      footer={<>
        {editing && canDelete && <Button variant="danger" onClick={remove} loading={busy}>Delete</Button>}
        <Button variant="secondary" onClick={onClose}>Close</Button>
        <Button onClick={save} loading={busy}>Save</Button></>}>
      <FormError error={error} /><ConflictNote error={error} />
      {!editing && !presetEquipment && <FormField label="Equipment" as="select" required options={withBlank(equipment)} error={fe('equipment')} {...bind('equipment')} />}
      <FormField label="Type" as="select" options={LICENCE_TYPES} error={fe('licence_type')} {...bind('licence_type')} />
      <FormField label="Licence number" error={fe('licence_number')} {...bind('licence_number')} />
      <FormField label="Issuing authority" error={fe('issuing_authority')} {...bind('issuing_authority')} />
      <FormField label="Issue date" type="date" required error={fe('issue_date')} {...bind('issue_date')} />
      <FormField label="Expiry date" type="date" required error={fe('expiry_date')} {...bind('expiry_date')} />
      <FormField label="Notes" as="textarea" error={fe('notes')} {...bind('notes')} />
      {editing && (<><h4>Documents</h4><DocumentsPanel entityType="equipment_licence" entityId={licence.public_id} /></>)}
    </Modal>
  )
}