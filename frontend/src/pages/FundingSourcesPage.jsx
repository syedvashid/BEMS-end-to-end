
import { useState } from 'react'
import ConfirmDeleteModal from '../components/ConfirmDeleteModal'
import FundingSourceFormModal, { SOURCE_TYPES } from '../components/FundingSourceFormModal'
import PermissionGate from '../components/PermissionGate'
import { Button, FormField, Pagination, Table, useToast } from '../components/ui'
import { useFacility } from '../context/FacilityContext'
import useFetch from '../hooks/useFetch'
import { opts } from '../utils/formHelpers'
import { PAGE_SIZE } from '../utils/format'

export default function FundingSourcesPage() {
  const { can } = useFacility()
  const toast = useToast()
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState({ search: '', source_type: '' })
  const [applied, setApplied] = useState(filters)
  const [editing, setEditing] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const list = useFetch('/funding-sources/', { page, page_size: PAGE_SIZE, ...applied })

  const columns = [
    { key: 'code', header: 'Code' },
    { key: 'name', header: 'Name' },
    { key: 'source_type', header: 'Type', render: (r) => r.source_type.replace(/_/g, ' ') },
    { key: 'description', header: 'Description' },
    {
      key: 'actions', header: '', className: 'actions',
      render: (r) => (
        <div className="row">
          {can('funding_source.change') && <Button size="sm" onClick={() => setEditing(r)}>Edit</Button>}
          {can('funding_source.delete') && <Button size="sm" variant="danger" onClick={() => setDeleting(r)}>Delete</Button>}
        </div>
      ),
    },
  ]

  return (
    <>
      <div className="page-head">
        <h1>Funding Sources</h1><span className="spacer" />
        <PermissionGate code="funding_source.add"><Button variant="primary" onClick={() => setEditing('new')}>New funding source</Button></PermissionGate>
      </div>
      <form className="filters" onSubmit={(e) => { e.preventDefault(); setPage(1); setApplied(filters) }}>
        <FormField label="Search" name="f_search" value={filters.search} onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))} />
        <FormField label="Type" name="f_type" as="select" options={opts(SOURCE_TYPES, 'All types')} value={filters.source_type} onChange={(e) => setFilters((f) => ({ ...f, source_type: e.target.value }))} />
        <Button type="submit">Search</Button>
      </form>
      {list.error && <div className="alert alert-danger">{list.error.message}</div>}
      <Table columns={columns} rows={list.data?.results} loading={list.loading} />
      <Pagination page={page} pageSize={PAGE_SIZE} count={list.data?.count ?? 0} onPageChange={setPage} />

      {editing && (
        <FundingSourceFormModal
          source={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)} onStale={list.reload}
          onSaved={(_, isNew) => { setEditing(null); toast.success(isNew ? 'Funding source created.' : 'Funding source updated.'); list.reload() }}
        />
      )}
      {deleting && (
        <ConfirmDeleteModal
          title="Delete funding source" label={deleting.name}
          path={`/funding-sources/${deleting.public_id}/`} rowVersion={deleting.row_version}
          onClose={() => setDeleting(null)} onStale={list.reload}
          onDone={() => { setDeleting(null); toast.success('Funding source deleted.'); list.reload() }}
        />
      )}
    </>
  )
}