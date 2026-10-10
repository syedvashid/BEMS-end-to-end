import { Button, FormError, FormField, Modal } from '../ui'
import { ConflictNote, api, fieldError, nn, useForm, useSubmit } from './shared'

export default function AmcRenewModal({ contract, onClose, onRenewed }) {
  const { busy, error, run } = useSubmit()
  const { v, bind } = useForm({ contract_number: '', start_date: '', end_date: '', contract_cost: '' })
  const fe = (n) => fieldError(error, n)
  const go = () => run(async () => {
    const r = await api.post(`/amc-contracts/${contract.public_id}/renew/`, {
      contract_number: nn(v.contract_number), start_date: nn(v.start_date), end_date: nn(v.end_date),
      contract_cost: nn(v.contract_cost),
    })
    onRenewed(r.data)
  })
  return (
    <Modal title={`Renew ${contract.contract_number}`} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={go} loading={busy}>Renew</Button></>}>
      <FormError error={error} /><ConflictNote error={error} />
      <p>Creates a new contract with the same terms and covered equipment. The old contract is not changed.</p>
      <FormField label="New contract number" hint="Empty = automatic" error={fe('contract_number')} {...bind('contract_number')} />
      <FormField label="Start date" type="date" hint="Empty = day after the old end date" error={fe('start_date')} {...bind('start_date')} />
      <FormField label="End date" type="date" hint="Empty = one year from the start" error={fe('end_date')} {...bind('end_date')} />
      <FormField label="Contract cost" type="number" min="0" step="0.01" hint="Empty = same as before" error={fe('contract_cost')} {...bind('contract_cost')} />
    </Modal>
  )
}