import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Table } from '../ui'
import ClaimsSection from './ClaimsSection'
import LicenceModal, { LICENCE_TYPES } from './LicenceModal'
import WarrantyModal from './WarrantyModal'
import { ExpiryChip, fmtDate, useFetch, usePermission } from './shared'

export default function ContractsWarrantyTab({ equipment }) {
  const id = equipment.public_id
  const canW = usePermission('warranty.view'), canWAdd = usePermission('warranty.add'), canWDel = usePermission('warranty.delete')
  const canA = usePermission('amc.view')
  const canL = usePermission('licence.view'), canLAdd = usePermission('licence.add'), canLDel = usePermission('licence.delete')
  const w = useFetch('/warranties/', { equipment: id }, canW)
  const a = useFetch('/amc-contracts/', { equipment: id }, canA)
  const l = useFetch('/equipment-licences/', { equipment: id }, canL)
  const [modal, setModal] = useState(null)
  const done = () => { setModal(null); w.reload(); l.reload() }
  const lbl = (t) => LICENCE_TYPES.find((x) => x.value === t)?.label || t

  return (
    <div>
      {canW && (<section>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}><h3>Warranties</h3>
          {canWAdd && <Button size="sm" onClick={() => setModal({ t: 'w' })}>Add warranty</Button>}</div>
        <Table rows={w.data?.results || []} loading={w.loading} empty="No warranties." onRowClick={(r) => setModal({ t: 'w', row: r })}
          columns={[{ key: 'warranty_type', header: 'Type' }, { key: 'vendor_name', header: 'Vendor', render: (r) => r.vendor_name || '—' },
            { key: 'end_date', header: 'Ends', render: (r) => <>{fmtDate(r.end_date)} <ExpiryChip date={r.end_date} /></> }]} />
        <ClaimsSection equipment={id} />
      </section>)}
      {canA && (<section>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}><h3>AMC / CMC coverage</h3><Link to="/amc-contracts">Open AMC Contracts</Link></div>
        <Table rows={a.data?.results || []} loading={a.loading} empty="Not covered by an AMC contract."
          columns={[{ key: 'contract_number', header: 'Contract' }, { key: 'contract_type', header: 'Type', render: (r) => r.contract_type.replace('_', '-').toLowerCase() },
            { key: 'vendor_name', header: 'Vendor' }, { key: 'end_date', header: 'Ends', render: (r) => <>{fmtDate(r.end_date)} <ExpiryChip date={r.end_date} /></> }]} />
      </section>)}
      {canL && (<section>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}><h3>Licences</h3>
          {canLAdd && <Button size="sm" onClick={() => setModal({ t: 'l' })}>Add licence</Button>}</div>
        <Table rows={l.data?.results || []} loading={l.loading} empty="No licences." onRowClick={(r) => setModal({ t: 'l', row: r })}
          columns={[{ key: 'licence_type', header: 'Type', render: (r) => lbl(r.licence_type) }, { key: 'licence_number', header: 'Number', render: (r) => r.licence_number || '—' },
            { key: 'expiry_date', header: 'Expires', render: (r) => <>{fmtDate(r.expiry_date)} <ExpiryChip date={r.expiry_date} /></> }]} />
      </section>)}
      {modal?.t === 'w' && <WarrantyModal warranty={modal.row} presetEquipment={id} canDelete={canWDel} onClose={() => setModal(null)} onSaved={done} />}
      {modal?.t === 'l' && <LicenceModal licence={modal.row} presetEquipment={id} canDelete={canLDel} onClose={() => setModal(null)} onSaved={done} />}
    </div>
  )
}