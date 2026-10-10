import { Button, FormError, FormField, Modal } from '../ui'
import { ConflictNote, api, fieldError, nn, today, useForm, useSubmit } from './shared'

const STATUS = ['RAISED', 'ACCEPTED', 'REJECTED', 'RESOLVED'].map((s) => ({ value: s, label: s[0] + s.slice(1).toLowerCase() }))

export default function ClaimModal({ warranty, claim, onClose, onSaved }) {
  const editing = !!claim
  const { busy, error, run } = useSubmit()
  const { v, bind } = useForm({
    claim_number: claim?.claim_number ?? '', claim_date: claim?.claim_date ?? today(), description: claim?.description ?? '',
    status: claim?.status ?? 'RAISED', claim_amount: claim?.claim_amount ?? '', resolved_date: claim?.resolved_date ?? '',
    resolution_notes: claim?.resolution_notes ?? '',
  })
  const fe = (n) => fieldError(error, n)
  const save = () => run(async () => {
    const body = {
      claim_number: nn(v.claim_number), claim_date: v.claim_date, description: v.description, status: v.status,
      claim_amount: nn(v.claim_amount), resolved_date: nn(v.resolved_date), resolution_notes: nn(v.resolution_notes),
    }
    if (editing) await api.patch(`/warranty-claims/${claim.public_id}/`, { ...body, row_version: claim.row_version })
    else await api.post('/warranty-claims/', { ...body, warranty: warranty.public_id })
    onSaved()
  })
  const remove = () => run(async () => {
    await api.delete(`/warranty-claims/${claim.public_id}/`, { params: { row_version: claim.row_version } })
    onSaved()
  })
  return (
    <Modal title={editing ? 'Edit claim' : 'New warranty claim'} onClose={onClose}
      footer={<>
        {editing && <Button variant="danger" onClick={remove} loading={busy}>Delete</Button>}
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button onClick={save} loading={busy}>Save</Button></>}>
      <FormError error={error} /><ConflictNote error={error} />
      <FormField label="Claim number" error={fe('claim_number')} {...bind('claim_number')} />
      <FormField label="Claim date" type="date" required error={fe('claim_date')} {...bind('claim_date')} />
      <FormField label="Description" as="textarea" required error={fe('description')} {...bind('description')} />
      <FormField label="Status" as="select" options={STATUS} error={fe('status')} {...bind('status')} />
      <FormField label="Claim amount" type="number" min="0" step="0.01" error={fe('claim_amount')} {...bind('claim_amount')} />
      <FormField label="Resolved on" type="date" error={fe('resolved_date')} {...bind('resolved_date')} />
      <FormField label="Resolution notes" as="textarea" error={fe('resolution_notes')} {...bind('resolution_notes')} />
    </Modal>
  )
}