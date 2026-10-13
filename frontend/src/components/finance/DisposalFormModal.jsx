import { useState } from 'react'
import { api } from '../../api/client'
import useFetch from '../../hooks/useFetch'
import { Button, FormField, Modal } from '../ui'
import {
  DISPOSAL_METHODS, ErrorNote, fieldErr, nn, opts, useAction,
} from './shared'

const Check = ({ label, checked, onChange }) => (
  <label className="row"><input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} /> {label}</label>
)

// requestId: create under this condemnation request. disposal: edit this one (while IN_PROGRESS).
export default function DisposalFormModal({ requestId, disposal, onClose, onDone }) {
  const d = disposal
  const vendors = useFetch('/vendors/', { page_size: 100 })
  const [v, setV] = useState({
    disposal_method: d?.disposal_method || 'SCRAPPED_E_WASTE', disposal_date: d?.disposal_date || '',
    recipient_name: d?.recipient_name || '', recipient_vendor: d?.recipient_vendor || '',
    proceeds_amount: d?.proceeds_amount ?? '0', decontamination_done: !!d?.decontamination_done,
    decontamination_notes: d?.decontamination_notes || '', data_wipe_required: !!d?.data_wipe_required,
    data_wipe_done: !!d?.data_wipe_done, recycler_name: d?.recycler_name || '',
    ewaste_certificate_number: d?.ewaste_certificate_number || '', notes: d?.notes || '',
  })
  const set = (k) => (e) => setV((s) => ({ ...s, [k]: e.target ? e.target.value : e }))
  const act = useAction()
  const ewaste = v.disposal_method === 'SCRAPPED_E_WASTE'

  const submit = () => act.run(async () => {
    const body = {
      disposal_method: v.disposal_method, disposal_date: nn(v.disposal_date), recipient_name: nn(v.recipient_name),
      recipient_vendor: nn(v.recipient_vendor), proceeds_amount: Number(v.proceeds_amount || 0),
      decontamination_done: v.decontamination_done, decontamination_notes: nn(v.decontamination_notes),
      data_wipe_required: v.data_wipe_required, data_wipe_done: v.data_wipe_done,
      recycler_name: nn(v.recycler_name), ewaste_certificate_number: nn(v.ewaste_certificate_number), notes: nn(v.notes),
    }
    if (d) await api.patch(`/disposals/${d.public_id}/`, { ...body, row_version: d.row_version })
    else await api.post(`/condemnation-requests/${requestId}/disposal/`, body)
    onDone()
  })

  const vendorOptions = [{ value: '', label: 'None' }, ...(vendors.data?.results || []).map((x) => ({ value: x.public_id, label: x.name }))]
  return (
    <Modal title={d ? `Edit disposal ${d.disposal_number}` : 'Create disposal'} onClose={onClose} wide
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={act.busy} onClick={submit}>Save</Button></>}>
      <FormField label="Method" name="disposal_method" as="select" value={v.disposal_method} options={opts(DISPOSAL_METHODS)}
        error={fieldErr(act.error, 'disposal_method')} onChange={set('disposal_method')} />
      <FormField label="Disposal date" name="disposal_date" type="date" value={v.disposal_date}
        hint="Required to complete. Not in the future and not before the decision date."
        error={fieldErr(act.error, 'disposal_date')} onChange={set('disposal_date')} />
      <FormField label="Recipient / buyer name" name="recipient_name" value={v.recipient_name}
        hint="Required for sold, auctioned, donated and trade-in." error={fieldErr(act.error, 'recipient_name')} onChange={set('recipient_name')} />
      <FormField label="Recipient vendor (optional)" name="recipient_vendor" as="select" value={v.recipient_vendor}
        options={vendorOptions} onChange={set('recipient_vendor')} />
      <FormField label="Proceeds (INR)" name="proceeds_amount" type="number" step="0.01" min="0" value={v.proceeds_amount}
        error={fieldErr(act.error, 'proceeds_amount')} onChange={set('proceeds_amount')} />
      <Check label="Decontamination done (not needed for lost equipment)" checked={v.decontamination_done}
        onChange={(c) => setV((s) => ({ ...s, decontamination_done: c }))} />
      <FormField label="Decontamination notes" name="decontamination_notes" as="textarea" value={v.decontamination_notes}
        onChange={set('decontamination_notes')} />
      <Check label="Data wipe required (the equipment stores patient or other data)" checked={v.data_wipe_required}
        onChange={(c) => setV((s) => ({ ...s, data_wipe_required: c }))} />
      {v.data_wipe_required && (
        <Check label="Data wipe done" checked={v.data_wipe_done} onChange={(c) => setV((s) => ({ ...s, data_wipe_done: c }))} />
      )}
      {ewaste && (
        <>
          <FormField label="E-waste recycler" name="recycler_name" value={v.recycler_name}
            error={fieldErr(act.error, 'recycler_name')} onChange={set('recycler_name')} />
          <FormField label="E-waste certificate number" name="ewaste_certificate_number" value={v.ewaste_certificate_number}
            error={fieldErr(act.error, 'ewaste_certificate_number')} onChange={set('ewaste_certificate_number')} />
        </>
      )}
      <FormField label="Notes" name="notes" as="textarea" value={v.notes} onChange={set('notes')} />
      <ErrorNote error={act.error} />
    </Modal>
  )
}
