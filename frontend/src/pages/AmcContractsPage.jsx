import { useState } from 'react'
import { Button, FormField, Pagination, StatusBadge, Table } from '../components/ui'
import AmcContractModal from '../components/compliance/AmcContractModal'
import { ExpiryChip, clean, fmtDate, useFetch, usePermission } from '../components/compliance/shared'

const EXPIRING = [{ value: '', label: 'All' }, { value: '30', label: 'Expiring in 30 days' }, { value: '60', label: 'Expiring in 60 days' }, { value: '90', label: 'Expiring in 90 days' }]
const TYPE = [{ value: '', label: 'All types' }, { value: 'COMPREHENSIVE', label: 'Comprehensive' }, { value: 'NON_COMPREHENSIVE', label: 'Non-comprehensive' }]

export default function AmcContractsPage() {
  const canAdd = usePermission('amc.add')
  const [page, setPage] = useState(1)
  const [expiring, setExpiring] = useState('')
  const [type, setType] = useState('')
  const [modal, setModal] = useState(null)
  const { data, loading, error, reload } = useFetch('/amc-contracts/', clean({ page, page_size: 20, expiring_within_days: expiring, contract_type: type }))
  const cols = [
    { key: 'contract_number', header: 'Contract', render: (r) => <strong>{r.contract_number}</strong> },
    { key: 'vendor_name', header: 'Vendor' },
    { key: 'contract_type', header: 'Type', render: (r) => <StatusBadge tone={r.contract_type === 'COMPREHENSIVE' ? 'success' : 'warning'}>{r.contract_type === 'COMPREHENSIVE' ? 'Comprehensive' : 'Non-comprehensive'}</StatusBadge> },
    { key: 'start_date', header: 'Period', render: (r) => `${fmtDate(r.start_date)} – ${fmtDate(r.end_date)}` },
    { key: 'equipment_count', header: 'Equipment' },
    { key: 'contract_cost', header: 'Cost' },
    { key: 'end_date', header: 'Expiry', render: (r) => <ExpiryChip date={r.end_date} /> },
  ]
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <h1>AMC Contracts</h1>
        {canAdd && <Button onClick={() => setModal({})}>New contract</Button>}
      </div>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <FormField label="Expiry" name="exp" as="select" options={EXPIRING} value={expiring} onChange={(e) => { setExpiring(e.target.value); setPage(1) }} />
        <FormField label="Type" name="type" as="select" options={TYPE} value={type} onChange={(e) => { setType(e.target.value); setPage(1) }} />
      </div>
      {error && <p role="alert">Could not load contracts.</p>}
      <Table columns={cols} rows={data?.results || []} loading={loading} empty="No AMC contracts." onRowClick={(r) => setModal({ row: r })} />
      <Pagination page={page} pageSize={20} count={data?.count || 0} onChange={setPage} />
      {modal && <AmcContractModal contract={modal.row} onClose={() => { setModal(null); reload() }} onChanged={reload} />}
    </div>
  )
}