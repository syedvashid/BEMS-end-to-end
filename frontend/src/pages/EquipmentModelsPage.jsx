import { useState } from 'react'
import ConfirmDeleteModal from '../components/ConfirmDeleteModal'
import EquipmentModelFormModal from '../components/EquipmentModelFormModal'
import PermissionGate from '../components/PermissionGate'
import RiskBadge from '../components/RiskBadge'
// import { Button, FormField, Pagination, Table, useToast } from '../components/ui'
import { useFacility } from '../context/FacilityContext'
import useFetch from '../hooks/useFetch'
import { dash } from '../utils/formHelpers'
import { PAGE_SIZE } from '../utils/format'

// import ConfirmDeleteModal from '../components/ConfirmDeleteModal'
import DocumentsPanel from '../components/DocumentsPanel'
// import EquipmentModelFormModal from '../components/EquipmentModelFormModal'
// import PermissionGate from '../components/PermissionGate'
// import RiskBadge from '../components/RiskBadge'
import { Button, FormField, Modal, Pagination, Table, useToast } from '../components/ui'

export default function EquipmentModelsPage() {
  const { can } = useFacility()
  const toast = useToast()
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState({ search: '', category: '', manufacturer: '' })
  const [applied, setApplied] = useState(filters)
  const [editing, setEditing] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const list = useFetch('/equipment-models/', { page, page_size: PAGE_SIZE, ...applied })
  const cats = useFetch('/equipment-categories/', { page_size: 100 })
  const mfrs = useFetch('/vendors/', { is_manufacturer: true, page_size: 100 })
  const [docsFor, setDocsFor] = useState(null)
  const catName = Object.fromEntries((cats.data?.results ?? []).map((c) => [c.public_id, c.name]))
  const mfrName = Object.fromEntries((mfrs.data?.results ?? []).map((v) => [v.public_id, v.name]))
  const catOptions = [{ value: '', label: 'All categories' }].concat(
    (cats.data?.results ?? []).map((c) => ({ value: c.public_id, label: c.name })))
  const mfrOptions = [{ value: '', label: 'All manufacturers' }].concat(
    (mfrs.data?.results ?? []).map((v) => ({ value: v.public_id, label: v.name })))

  const columns = [
    { key: 'model_name', header: 'Model' },
    { key: 'model_number', header: 'Model no.' },
    { key: 'category', header: 'Category', render: (r) => dash(catName[r.category]) },
    { key: 'manufacturer', header: 'Manufacturer', render: (r) => dash(mfrName[r.manufacturer]) },
    { key: 'effective_risk_class', header: 'Risk', render: (r) => <RiskBadge value={r.effective_risk_class} /> },
    { key: 'effective_pm_interval_days', header: 'PM (days)', render: (r) => dash(r.effective_pm_interval_days) },
    { key: 'effective_calibration_interval_days', header: 'Calibration (days)', render: (r) => dash(r.effective_calibration_interval_days) },
    {
      key: 'actions', header: '', className: 'actions',
      render: (r) => (
        <div className="row">
            {can('document.view') && <Button size="sm" onClick={() => setDocsFor(r)}>Documents</Button>}
          {can('equipment_model.change') && <Button size="sm" onClick={() => setEditing(r)}>Edit</Button>}
          {can('equipment_model.delete') && <Button size="sm" variant="danger" onClick={() => setDeleting(r)}>Delete</Button>}
        </div>
      ),
    },
  ]

  return (
    <>
      <div className="page-head">
        <h1>Equipment Models</h1><span className="spacer" />
        <PermissionGate code="equipment_model.add"><Button variant="primary" onClick={() => setEditing('new')}>New model</Button></PermissionGate>
      </div>
      <form className="filters" onSubmit={(e) => { e.preventDefault(); setPage(1); setApplied(filters) }}>
        <FormField label="Search" name="f_search" value={filters.search} onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))} />
        <FormField label="Category" name="f_category" as="select" options={catOptions} value={filters.category} onChange={(e) => setFilters((f) => ({ ...f, category: e.target.value }))} />
        <FormField label="Manufacturer" name="f_manufacturer" as="select" options={mfrOptions} value={filters.manufacturer} onChange={(e) => setFilters((f) => ({ ...f, manufacturer: e.target.value }))} />
        <Button type="submit">Search</Button>
      </form>
      {list.error && <div className="alert alert-danger">{list.error.message}</div>}
      <Table columns={columns} rows={list.data?.results} loading={list.loading} />
      <Pagination page={page} pageSize={PAGE_SIZE} count={list.data?.count ?? 0} onPageChange={setPage} />

      {editing && (
        <EquipmentModelFormModal
          model={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)} onStale={list.reload}
          onSaved={(_, isNew) => { setEditing(null); toast.success(isNew ? 'Model created.' : 'Model updated.'); list.reload() }}
        />
      )}
       {docsFor && (
        <Modal title={`Documents: ${docsFor.model_name}`} onClose={() => setDocsFor(null)} wide
          footer={<Button onClick={() => setDocsFor(null)}>Close</Button>}>
          <DocumentsPanel entityType="equipment_model" entityId={docsFor.public_id}
            viewPermission="equipment_model.view" attachPermission="equipment_model.change" />
        </Modal>
      )}
      {deleting && (
        <ConfirmDeleteModal
          title="Delete equipment model"label={`${deleting.model_name} (${deleting.model_number})`}
          path={`/equipment-models/${deleting.public_id}/`} rowVersion={deleting.row_version}
          onClose={() => setDeleting(null)} onStale={list.reload}
          onDone={() => { setDeleting(null); toast.success('Model deleted.'); list.reload() }}
        />
      )}
    </>
  )
}