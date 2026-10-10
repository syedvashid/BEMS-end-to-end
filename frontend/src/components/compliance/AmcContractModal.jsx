import { useState } from 'react'
import { Button, FormError, FormField, Modal } from '../ui'
import DocumentsPanel from '../DocumentsPanel'
import AmcRenewModal from './AmcRenewModal'
import CoverageEditor from './CoverageEditor'
import { ConflictNote, api, fieldError, nn, useFetch, useForm, useOptions, usePermission, useSubmit, vendorOption, withBlank } from './shared'

const TYPES = [{ value: 'COMPREHENSIVE', label: 'Comprehensive (AMC/CMC)' }, { value: 'NON_COMPREHENSIVE', label: 'Non-comprehensive' }]

export default function AmcContractModal({ contract: initial, onClose, onChanged }) {
  const canAdd = usePermission('amc.add')
  const canChange = usePermission('amc.change')
  const canDelete = usePermission('amc.delete')
  const [contract, setContract] = useState(initial || null)
  const [renew, setRenew] = useState(false)
  const [msg, setMsg] = useState('')
  const vendors = useOptions('/vendors/', vendorOption)
  const detail = useFetch(contract ? `/amc-contracts/${contract.public_id}/` : '/amc-contracts/', {}, !!contract)
  const renewedFrom = useFetch(contract?.renewed_from_contract ? `/amc-contracts/${contract.renewed_from_contract}/` : '/amc-contracts/', {}, !!contract?.renewed_from_contract)
  const { busy, error, run } = useSubmit()
  const c = contract
  const { v, bind } = useForm({
    contract_number: c?.contract_number ?? '', vendor: c?.vendor ?? '', contract_type: c?.contract_type ?? 'COMPREHENSIVE',
    start_date: c?.start_date ?? '', end_date: c?.end_date ?? '', contract_cost: c?.contract_cost ?? 0,
    visit_frequency_per_year: c?.visit_frequency_per_year ?? 0, response_sla_hours: c?.response_sla_hours ?? '',
    uptime_guarantee_percent: c?.uptime_guarantee_percent ?? '', covered_scope: c?.covered_scope ?? '',
    exclusions: c?.exclusions ?? '', penalty_terms: c?.penalty_terms ?? '', notes: c?.notes ?? '',
  })
  const fe = (n) => fieldError(error, n)

  const save = () => run(async () => {
    const body = {
      contract_number: v.contract_number, vendor: v.vendor, contract_type: v.contract_type, start_date: v.start_date,
      end_date: v.end_date, contract_cost: v.contract_cost || 0, visit_frequency_per_year: Number(v.visit_frequency_per_year) || 0,
      response_sla_hours: nn(v.response_sla_hours), uptime_guarantee_percent: nn(v.uptime_guarantee_percent),
      covered_scope: nn(v.covered_scope), exclusions: nn(v.exclusions), penalty_terms: nn(v.penalty_terms), notes: nn(v.notes),
    }
    if (c) {
      const r = await api.patch(`/amc-contracts/${c.public_id}/`, { ...body, row_version: c.row_version })
      setContract(r.data); setMsg('Saved.')
    } else {
      const r = await api.post('/amc-contracts/', body)
      setContract(r.data); setMsg('Contract created. Now add the covered equipment below.')
    }
    detail.reload(); onChanged()
  })
  const remove = () => run(async () => {
    await api.delete(`/amc-contracts/${c.public_id}/`, { params: { row_version: c.row_version } })
    onChanged(); onClose()
  })

  return (
    <Modal wide title={c ? `AMC ${c.contract_number}` : 'New AMC / CMC contract'} onClose={onClose}
      footer={<>
        {c && canDelete && <Button variant="danger" onClick={remove} loading={busy}>Delete</Button>}
        {c && canAdd && <Button variant="secondary" onClick={() => setRenew(true)}>Renew</Button>}
        <Button variant="secondary" onClick={onClose}>Close</Button>
        {(c ? canChange : canAdd) && <Button onClick={save} loading={busy}>Save</Button>}</>}>
      <FormError error={error} /><ConflictNote error={error} />
      {msg && <p>{msg}</p>}
      {renewedFrom.data && <p>Renewed from contract {renewedFrom.data.contract_number}.</p>}
      <FormField label="Contract number" required error={fe('contract_number')} {...bind('contract_number')} />
      <FormField label="Vendor" as="select" required options={withBlank(vendors)} error={fe('vendor')} {...bind('vendor')} />
      <FormField label="Type" as="select" options={TYPES} error={fe('contract_type')} {...bind('contract_type')} />
      <FormField label="Start date" type="date" required error={fe('start_date')} {...bind('start_date')} />
      <FormField label="End date" type="date" required error={fe('end_date')} {...bind('end_date')} />
      <FormField label="Contract cost" type="number" min="0" step="0.01" error={fe('contract_cost')} {...bind('contract_cost')} />
      <FormField label="Visits per year" type="number" min="0" error={fe('visit_frequency_per_year')} {...bind('visit_frequency_per_year')} />
      <FormField label="Response SLA (hours)" type="number" min="1" error={fe('response_sla_hours')} {...bind('response_sla_hours')} />
      <FormField label="Uptime guarantee (%)" type="number" min="0" max="100" step="0.01" error={fe('uptime_guarantee_percent')} {...bind('uptime_guarantee_percent')} />
      <FormField label="Covered scope" as="textarea" error={fe('covered_scope')} {...bind('covered_scope')} />
      <FormField label="Exclusions (e.g. tubes, coils, consumables)" as="textarea" error={fe('exclusions')} {...bind('exclusions')} />
      <FormField label="Penalty terms" as="textarea" error={fe('penalty_terms')} {...bind('penalty_terms')} />
      <FormField label="Notes" as="textarea" error={fe('notes')} {...bind('notes')} />
      {c && detail.data && (<>
        <CoverageEditor key={detail.data.row_version + ':' + (detail.data.coverage || []).length} contract={c}
          coverage={detail.data.coverage} canChange={canChange} onSaved={() => { setMsg('Coverage saved.'); detail.reload(); onChanged() }} />
        <h4>Documents</h4>
        <DocumentsPanel entityType="amc_contract" entityId={c.public_id} />
      </>)}
      {renew && <AmcRenewModal contract={c} onClose={() => setRenew(false)}
        onRenewed={(n) => { setRenew(false); setContract(n); setMsg(`Renewed as ${n.contract_number}.`); onChanged() }} />}
    </Modal>
  )
}