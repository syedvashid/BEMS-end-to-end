import { useState } from 'react'
import { Button, FormField, Pagination, StatusBadge, Table } from '../components/ui'
import BulkWarrantyModal from '../components/compliance/BulkWarrantyModal'
import WarrantyModal from '../components/compliance/WarrantyModal'
import { ExpiryChip, clean, fmtDate, useFetch, usePermission } from '../components/compliance/shared'

const EXPIRING = [{ value: '', label: 'All' }, { value: '30', label: 'Expiring in 30 days' }, { value: '60', label: 'Expiring in 60 days' }, { value: '90', label: 'Expiring in 90 days' }]

export default function WarrantiesPage() {
  const canAdd = usePermission('warranty.add')
  const canDelete = usePermission('warranty.delete')
  const [page, setPage] = useState(1)
  const [expiring, setExpiring] = useState('')
  const [modal, setModal] = useState(null)
  const { data, loading, error, reload } = useFetch('/warranties/', clean({ page, page_size: 20, expiring_within_days: expiring }))
  const done = () => { setModal(null); reload() }
  const cols = [
    { key: 'equipment_asset_tag', header: 'Equipment', render: (r) => <><strong>{r.equipment_asset_tag}</strong><br />{r.equipment_name}</> },
    { key: 'vendor_name', header: 'Vendor', render: (r) => r.vendor_name || '—' },
    { key: 'warranty_type', header: 'Type', render: (r) => <StatusBadge tone={r.warranty_type === 'EXTENDED' ? 'info' : 'neutral'}>{r.warranty_type.toLowerCase()}</StatusBadge> },
    { key: 'start_date', header: 'Period', render: (r) => `${fmtDate(r.start_date)} – ${fmtDate(r.end_date)}` },
    { key: 'end_date', header: 'Expiry', render: (r) => <ExpiryChip date={r.end_date} /> },
  ]
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <h1>Warranties</h1>
        {canAdd && <span style={{ display: 'flex', gap: 8 }}>
          <Button variant="secondary" onClick={() => setModal({ type: 'bulk' })}>Add for several equipment</Button>
          <Button onClick={() => setModal({ type: 'one' })}>New warranty</Button></span>}
      </div>
      <FormField label="Show" name="exp" as="select" options={EXPIRING} value={expiring} onChange={(e) => { setExpiring(e.target.value); setPage(1) }} />
      {error && <p role="alert">Could not load warranties.</p>}
      <Table columns={cols} rows={data?.results || []} loading={loading} empty="No warranties." onRowClick={(r) => setModal({ type: 'one', row: r })} />
      <Pagination page={page} pageSize={20} count={data?.count || 0} onChange={setPage} />
      {modal?.type === 'one' && <WarrantyModal warranty={modal.row} canDelete={canDelete} onClose={() => setModal(null)} onSaved={done} />}
      {modal?.type === 'bulk' && <BulkWarrantyModal onClose={() => setModal(null)} onDone={done} />}
    </div>
  )
}