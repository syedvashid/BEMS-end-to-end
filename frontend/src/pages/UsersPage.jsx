import { useState } from 'react'
import { api } from '../api/client'
import AssignRolesModal from '../components/AssignRolesModal'
import PermissionGate from '../components/PermissionGate'
import UserFormModal from '../components/UserFormModal'
import { ActiveBadge, Button, FormError, FormField, Modal, Pagination, Table, useToast } from '../components/ui'
import { useFacility } from '../context/FacilityContext'
import useFetch from '../hooks/useFetch'
import useSubmit from '../hooks/useSubmit'
import { PAGE_SIZE } from '../utils/format'

export default function UsersPage() {
  const { can, me, refresh } = useFacility()
  const toast = useToast()
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState({ username: '', full_name: '' })
  const [applied, setApplied] = useState(filters)
  const [showInactive, setShowInactive] = useState(false)
  const [editing, setEditing] = useState(null)       // null | 'new' | user
  const [assigning, setAssigning] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const list = useFetch('/users/', { page, page_size: PAGE_SIZE, ...applied, include_inactive: showInactive })
  const del = useSubmit()

  const columns = [
    { key: 'username', header: 'Username' },
    { key: 'full_name', header: 'Name' },
    { key: 'designation', header: 'Designation' },
    {
      key: 'roles', header: 'Roles here',
      render: (u) => (u.facility_roles.length ? u.facility_roles.map((r) => <span key={r.role} className="chip">{r.role_code}</span>) : <span className="muted">—</span>),
    },
    { key: 'is_active', header: 'Status', render: (u) => <ActiveBadge active={u.is_active} /> },
    {
      key: 'actions', header: '', className: 'actions',
      render: (u) => (
        <div className="row">
          {u.is_active && can('user.change') && <Button size="sm" onClick={() => setEditing(u)}>Edit</Button>}
          {u.is_active && can('user.change') && <Button size="sm" onClick={() => setAssigning(u)}>Roles</Button>}
          {u.is_active && can('user.delete') && <Button size="sm" variant="danger" onClick={() => setDeleting(u)}>Deactivate</Button>}
        </div>
      ),
    },
  ]

  const confirmDelete = async () => {
    const res = await del.run(() => api.delete(`/users/${deleting.public_id}/`, { params: { row_version: deleting.row_version } }))
    if (res) { setDeleting(null); toast.success('User deactivated.'); list.reload() }
  }

  return (
    <>
      <div className="page-head">
        <h1>Users</h1><span className="spacer" />
        <PermissionGate code="user.add"><Button variant="primary" onClick={() => setEditing('new')}>New user</Button></PermissionGate>
      </div>
      <form className="filters" onSubmit={(e) => { e.preventDefault(); setPage(1); setApplied(filters) }}>
        <FormField label="Username" name="f_username" value={filters.username} onChange={(e) => setFilters((f) => ({ ...f, username: e.target.value }))} />
        <FormField label="Name" name="f_full_name" value={filters.full_name} onChange={(e) => setFilters((f) => ({ ...f, full_name: e.target.value }))} />
        <Button type="submit">Search</Button>
        <PermissionGate code="user.delete">
          <label className="check"><input type="checkbox" checked={showInactive} onChange={(e) => { setPage(1); setShowInactive(e.target.checked) }} /> Show inactive</label>
        </PermissionGate>
      </form>
      {list.error && <div className="alert alert-danger">{list.error.message}</div>}
      <Table columns={columns} rows={list.data?.results} loading={list.loading} />
      <Pagination page={page} pageSize={PAGE_SIZE} count={list.data?.count ?? 0} onPageChange={setPage} />

      {editing && (
        <UserFormModal
          user={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onStale={list.reload}
          onSaved={(saved, isNew) => {
            setEditing(null)
            list.reload()
            if (isNew) { toast.success('User created. Assign a role to add them to this facility.'); setAssigning(saved) }
            else toast.success('User updated.')
          }}
        />
      )}
      {assigning && (
        <AssignRolesModal
          user={assigning}
          onClose={() => setAssigning(null)}
          onSaved={() => {
            const self = assigning.public_id === me?.user?.public_id
            setAssigning(null)
            toast.success('Role assignments saved.')
            if (self) refresh(); else list.reload()
          }}
        />
      )}
      {deleting && (
        <Modal title="Deactivate user" onClose={() => setDeleting(null)}
          footer={<><Button onClick={() => setDeleting(null)}>Cancel</Button><Button variant="danger" loading={del.busy} onClick={confirmDelete}>Deactivate</Button></>}>
          <FormError error={del.error} />
          <p>Deactivate <strong>{deleting.username}</strong>? The record is kept; the user can no longer act.</p>
        </Modal>
      )}
    </>
  )
}