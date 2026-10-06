import { useState } from 'react'
import ConfirmDeleteModal from '../components/ConfirmDeleteModal'
import DepartmentFormModal from '../components/DepartmentFormModal'
import PermissionGate from '../components/PermissionGate'
import { Button, FormField, Pagination, Table, useToast } from '../components/ui'
import { useFacility } from '../context/FacilityContext'
import useFetch from '../hooks/useFetch'
import { opts } from '../utils/formHelpers'
import { PAGE_SIZE } from '../utils/format'

const TYPES = opts(['CLINICAL', 'DIAGNOSTIC', 'SUPPORT', 'ADMINISTRATIVE'], 'All types')

export default function DepartmentsPage() {
  const { can } = useFacility()
  const toast = useToast()
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState({ search: '', department_type: '' })
  const [applied, setApplied] = useState(filters)
  const [editing, setEditing] = useState(null)   // null | 'new' | record
  const [deleting, setDeleting] = useState(null)
  const list = useFetch('/departments/', { page, page_size: PAGE_SIZE, ...applied })

  const columns = [
    { key: 'code', header: 'Code' },
    { key: 'name', header: 'Name' },
    { key: 'department_type', header: 'Type' },
    { key: 'description', header: 'Description' },
    {
      key: 'actions', header: '', className: 'actions',
      render: (r) => (
        <div className="row">
          {can('department.change') && <Button size="sm" onClick={() => setEditing(r)}>Edit</Button>}
          {can('department.delete') && <Button size="sm" variant="danger" onClick={() => setDeleting(r)}>Delete</Button>}
        </div>
      ),
    },
  ]

  return (
    <>
      <div className="page-head">
        <h1>Departments</h1><span className="spacer" />
        <PermissionGate code="department.add"><Button variant="primary" onClick={() => setEditing('new')}>New department</Button></PermissionGate>
      </div>
      <form className="filters" onSubmit={(e) => { e.preventDefault(); setPage(1); setApplied(filters) }}>
        <FormField label="Search" name="f_search" value={filters.search} onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))} />
        <FormField label="Type" name="f_type" as="select" options={TYPES} value={filters.department_type} onChange={(e) => setFilters((f) => ({ ...f, department_type: e.target.value }))} />
        <Button type="submit">Search</Button>
      </form>
      {list.error && <div className="alert alert-danger">{list.error.message}</div>}
      <Table columns={columns} rows={list.data?.results} loading={list.loading} />
      <Pagination page={page} pageSize={PAGE_SIZE} count={list.data?.count ?? 0} onPageChange={setPage} />

      {editing && (
        <DepartmentFormModal
          department={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onStale={list.reload}
          onSaved={(_, isNew) => { setEditing(null); toast.success(isNew ? 'Department created.' : 'Department updated.'); list.reload() }}
        />
      )}
      {deleting && (
        <ConfirmDeleteModal
          title="Delete department" label={deleting.name}
          path={`/departments/${deleting.public_id}/`} rowVersion={deleting.row_version}
          onClose={() => setDeleting(null)} onStale={list.reload}
          onDone={() => { setDeleting(null); toast.success('Department deleted.'); list.reload() }}
        />
      )}
    </>
  )
}