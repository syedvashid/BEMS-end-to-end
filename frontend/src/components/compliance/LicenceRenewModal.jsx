import { Button, FormError, FormField, Modal } from '../ui'
import { ConflictNote, api, fieldError, nn, useForm, useSubmit } from './shared'

export default function LicenceRenewModal({ licence, onClose, onRenewed }) {
  const { busy, error, run } = useSubmit()
  const { v, bind } = useForm({ issue_date: '', expiry_date: '', licence_number: licence.licence_number ?? '', issuing_authority: '', notes: '' })
  const fe = (n) => fieldError(error, n)
  const go = () => run(async () => {
    await api.post(`/equipment-licences/${licence.public_id}/renew/`, {
      issue_date: v.issue_date, expiry_date: v.expiry_date, licence_number: nn(v.licence_number),
      issuing_authority: nn(v.issuing_authority), notes: nn(v.notes),
    })
    onRenewed()
  })
  return (
    <Modal title="Renew licence" onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={go} loading={busy}>Renew</Button></>}>
      <FormError error={error} /><ConflictNote error={error} />
      <p>Creates a new licence record linked to this one. The old record stays as history.</p>
      <FormField label="New issue date" type="date" required error={fe('issue_date')} {...bind('issue_date')} />
      <FormField label="New expiry date" type="date" required error={fe('expiry_date')} {...bind('expiry_date')} />
      <FormField label="Licence number" error={fe('licence_number')} {...bind('licence_number')} />
      <FormField label="Issuing authority (empty = same)" error={fe('issuing_authority')} {...bind('issuing_authority')} />
      <FormField label="Notes" as="textarea" {...bind('notes')} />
    </Modal>
  )
}