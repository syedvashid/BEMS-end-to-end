import { useState } from 'react'
import { api } from '../api/client'
import FacilityFormModal from '../components/FacilityFormModal'
import PermissionGate from '../components/PermissionGate'
import { ActiveBadge, Button, FormError, FormField, Modal, Pagination, Table, useToast } from '../components/ui'
import { useFacility } from '../context/FacilityContext'
import useFetch from '../hooks/useFetch'
import useSubmit from '../hooks/useSubmit'
import { PAGE_SIZE } from '../utils/format'

export default function FacilitiesPage() {
  const { facilityId, can, refresh } = useFacility()
  const toast = useToast()
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState({ name: '', city: '' })
  const [applied, setApplied] = useState(filters)
  const [editing, setEditing] = useState(null)      // null | 'new' | facility
  const [created, setCreated] = useState(null)      // newly created facility (shown once)
  const [deleting, setDeleting] = useState(null)
  const list = useFetch('/facilities/', { page, page_size: PAGE_SIZE, ...applied })
  const del = useSubmit()

  const columns = [
    { key: 'code', header: 'Code' },
    { key: 'name', header: 'Name' },
    { key: 'facility_type', header: 'Type' },
    { key: 'city', header: 'City' },
    { key: 'state', header: 'State' },
    { key: 'is_active', header: 'Status', render: (r) => <ActiveBadge active={r.is_active} /> },
    {
      key: 'actions', header: '', className: 'actions',
      render: (r) => {
        const isCurrent = r.public_id === facilityId   // the API only edits/deletes the CURRENT facility
        return (
          <div className="row">
            {isCurrent && can('facility.change') && <Button size="sm" onClick={() => setEditing(r)}>Edit</Button>}
            {isCurrent && can('facility.delete') && <Button size="sm" variant="danger" onClick={() => setDeleting(r)}>Delete</Button>}
          </div>
        )
      },
    },
  ]

  const confirmDelete = async () => {
    const res = await del.run(() => api.delete(`/facilities/${deleting.public_id}/`, { params: { row_version: deleting.row_version } }))
    if (res) { setDeleting(null); toast.success('Facility deleted.'); refresh() }
  }

  return (
    <>
      <div className="page-head">
        <h1>Facilities</h1><span className="spacer" />
        <PermissionGate code="facility.add"><Button variant="primary" onClick={() => setEditing('new')}>New facility</Button></PermissionGate>
      </div>
      <form className="filters" onSubmit={(e) => { e.preventDefault(); setPage(1); setApplied(filters) }}>
        <FormField label="Name" name="f_name" value={filters.name} onChange={(e) => setFilters((f) => ({ ...f, name: e.target.value }))} />
        <FormField label="City" name="f_city" value={filters.city} onChange={(e) => setFilters((f) => ({ ...f, city: e.target.value }))} />
        <Button type="submit">Search</Button>
      </form>
      {list.error && <div className="alert alert-danger">{list.error.message}</div>}
      <Table columns={columns} rows={list.data?.results} loading={list.loading} />
      <Pagination page={page} pageSize={PAGE_SIZE} count={list.data?.count ?? 0} onPageChange={setPage} />

      {editing && (
        <FacilityFormModal
          facility={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onStale={list.reload}
          onSaved={(saved, isNew) => {
            setEditing(null)
            if (isNew) { setCreated(saved); list.reload() }
            else { toast.success('Facility updated.'); refresh() }
          }}
        />
      )}
      {created && (
        <Modal title="Facility created" onClose={() => setCreated(null)} footer={<Button variant="primary" onClick={() => setCreated(null)}>OK</Button>}>
          <p><strong>{created.name}</strong> was created. It appears in your list once a user has a role there.</p>
          <p>Go to Users, choose Roles, pick &quot;Other facility&quot; and paste this ID:</p>
          <pre className="json">{created.public_id}</pre>
        </Modal>
      )}
      {deleting && (
        <Modal title="Delete facility" onClose={() => setDeleting(null)}
          footer={<><Button onClick={() => setDeleting(null)}>Cancel</Button><Button variant="danger" loading={del.busy} onClick={confirmDelete}>Delete</Button></>}>
          <FormError error={del.error} />
          <p>Deactivate <strong>{deleting.name}</strong>? Its data is kept (soft delete) but the facility stops being accessible.</p>
        </Modal>
      )}
    </>
  )
}