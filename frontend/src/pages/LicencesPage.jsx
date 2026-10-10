import { useState } from 'react'
import { Button, FormField, Pagination, Table } from '../components/ui'
import LicenceModal, { LICENCE_TYPES } from '../components/compliance/LicenceModal'
import LicenceRenewModal from '../components/compliance/LicenceRenewModal'
import { ExpiryChip, clean, fmtDate, useFetch, usePermission } from '../components/compliance/shared'

const EXPIRING = [{ value: '', label: 'All' }, { value: '30', label: 'Expiring in 30 days' }, { value: '60', label: 'Expiring in 60 days' }, { value: '90', label: 'Expiring in 90 days' }]
const label = (t) => LICENCE_TYPES.find((x) => x.value === t)?.label || t

export default function LicencesPage() {
  const canAdd = usePermission('licence.add')
  const canDelete = usePermission('licence.delete')
  const [page, setPage] = useState(1)
  const [expiring, setExpiring] = useState('')
  const [type, setType] = useState('')
  const [modal, setModal] = useState(null)
  const { data, loading, error, reload } = useFetch('/equipment-licences/', clean({ page, page_size: 20, expiring_within_days: expiring, licence_type: type }))
  const done = () => { setModal(null); reload() }
  const cols = [
    { key: 'equipment_asset_tag', header: 'Equipment', render: (r) => <><strong>{r.equipment_asset_tag}</strong><br />{r.equipment_name}</> },
    { key: 'licence_type', header: 'Type', render: (r) => label(r.licence_type) },
    { key: 'licence_number', header: 'Number', render: (r) => r.licence_number || '—' },
    { key: 'issuing_authority', header: 'Authority', render: (r) => r.issuing_authority || '—' },
    { key: 'expiry_date', header: 'Expiry', render: (r) => <>{fmtDate(r.expiry_date)} <ExpiryChip date={r.expiry_date} /></> },
    { key: 'actions', header: '', render: (r) => canAdd && (
      <Button size="sm" variant="secondary" onClick={(e) => { e.stopPropagation(); setModal({ type: 'renew', row: r }) }}>Renew</Button>) },
  ]
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <h1>Licences</h1>
        {canAdd && <Button onClick={() => setModal({ type: 'one' })}>New licence</Button>}
      </div>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <FormField label="Expiry" name="exp" as="select" options={EXPIRING} value={expiring} onChange={(e) => { setExpiring(e.target.value); setPage(1) }} />
        <FormField label="Type" name="type" as="select" options={[{ value: '', label: 'All types' }, ...LICENCE_TYPES]} value={type} onChange={(e) => { setType(e.target.value); setPage(1) }} />
      </div>
      {error && <p role="alert">Could not load licences.</p>}
      <Table columns={cols} rows={data?.results || []} loading={loading} empty="No licences." onRowClick={(r) => setModal({ type: 'one', row: r })} />
      <Pagination page={page} pageSize={20} count={data?.count || 0} onChange={setPage} />
      {modal?.type === 'one' && <LicenceModal licence={modal.row} canDelete={canDelete} onClose={() => setModal(null)} onSaved={done} />}
      {modal?.type === 'renew' && <LicenceRenewModal licence={modal.row} onClose={() => setModal(null)} onRenewed={done} />}
    </div>
  )
}