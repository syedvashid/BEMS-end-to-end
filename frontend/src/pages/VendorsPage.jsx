import { useState } from 'react'
import ConfirmDeleteModal from '../components/ConfirmDeleteModal'
import PermissionGate from '../components/PermissionGate'
import VendorContactsPanel from '../components/VendorContactsPanel'
import VendorFormModal from '../components/VendorFormModal'
import { Button, FormField, Pagination, Table, useToast } from '../components/ui'
import { useFacility } from '../context/FacilityContext'
import useFetch from '../hooks/useFetch'
import { dash } from '../utils/formHelpers'
import { PAGE_SIZE } from '../utils/format'

const TYPE_FILTERS = [
  { value: '', label: 'All types' },
  { value: 'is_manufacturer', label: 'Manufacturer' },
  { value: 'is_supplier', label: 'Supplier' },
  { value: 'is_service_provider', label: 'Service provider' },
]

const typesOf = (v) => [v.is_manufacturer && 'Manufacturer', v.is_supplier && 'Supplier', v.is_service_provider && 'Service'].filter(Boolean).join(', ')

export default function VendorsPage() {
  const { can } = useFacility()
  const toast = useToast()
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState({ search: '', type: '' })
  const [applied, setApplied] = useState(filters)
  const [editing, setEditing] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [selected, setSelected] = useState(null)
  const params = { page, page_size: PAGE_SIZE, search: applied.search, ...(applied.type ? { [applied.type]: true } : {}) }
  const list = useFetch('/vendors/', params)

  const columns = [
    { key: 'name', header: 'Name' },
    { key: 'types', header: 'Types', render: typesOf },
    { key: 'city', header: 'City', render: (r) => dash(r.city) },
    { key: 'gstin', header: 'GSTIN', render: (r) => dash(r.gstin) },
    { key: 'rating', header: 'Rating', render: (r) => dash(r.rating) },
    {
      key: 'actions', header: '', className: 'actions',
      render: (r) => (
        <div className="row">
          <Button size="sm" onClick={(e) => { e.stopPropagation(); setSelected(r) }}>Contacts</Button>
          {can('vendor.change') && <Button size="sm" onClick={(e) => { e.stopPropagation(); setEditing(r) }}>Edit</Button>}
          {can('vendor.delete') && <Button size="sm" variant="danger" onClick={(e) => { e.stopPropagation(); setDeleting(r) }}>Delete</Button>}
        </div>
      ),
    },
  ]

  return (
    <>
      <div className="page-head">
        <h1>Vendors</h1><span className="spacer" />
        <PermissionGate code="vendor.add"><Button variant="primary" onClick={() => setEditing('new')}>New vendor</Button></PermissionGate>
      </div>
      <form className="filters" onSubmit={(e) => { e.preventDefault(); setPage(1); setApplied(filters) }}>
        <FormField label="Search" name="f_search" value={filters.search} onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))} />
        <FormField label="Type" name="f_type" as="select" options={TYPE_FILTERS} value={filters.type} onChange={(e) => setFilters((f) => ({ ...f, type: e.target.value }))} />
        <Button type="submit">Search</Button>
      </form>
      {list.error && <div className="alert alert-danger">{list.error.message}</div>}
      <Table columns={columns} rows={list.data?.results} loading={list.loading} onRowClick={setSelected} />
      <Pagination page={page} pageSize={PAGE_SIZE} count={list.data?.count ?? 0} onPageChange={setPage} />

      {selected && <VendorContactsPanel key={selected.public_id} vendor={selected} />}

      {editing && (
        <VendorFormModal
          vendor={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)} onStale={list.reload}
          onSaved={(saved, isNew) => {
            setEditing(null)
            toast.success(isNew ? 'Vendor created.' : 'Vendor updated.')
            if (selected?.public_id === saved.public_id) setSelected(saved)
            list.reload()
          }}
        />
      )}
      {deleting && (
        <ConfirmDeleteModal
          title="Delete vendor" label={deleting.name}
          path={`/vendors/${deleting.public_id}/`} rowVersion={deleting.row_version}
          onClose={() => setDeleting(null)} onStale={list.reload}
          onDone={() => {
            if (selected?.public_id === deleting.public_id) setSelected(null)
            setDeleting(null); toast.success('Vendor deleted.'); list.reload()
          }}
        />
      )}
    </>
  )
}