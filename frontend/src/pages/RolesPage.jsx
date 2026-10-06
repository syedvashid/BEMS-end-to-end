import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import PermissionGate from '../components/PermissionGate'
import RoleFormModal from '../components/RoleFormModal'
import { ActiveBadge, Button, FormError, FormField, Modal, Pagination, StatusBadge, Table, useToast } from '../components/ui'
import { useFacility } from '../context/FacilityContext'
import useFetch from '../hooks/useFetch'
import useSubmit from '../hooks/useSubmit'
import { PAGE_SIZE } from '../utils/format'

export default function RolesPage() {
  const { can } = useFacility()
  const navigate = useNavigate()
  const toast = useToast()
  const [page, setPage] = useState(1)
  const [name, setName] = useState('')
  const [appliedName, setAppliedName] = useState('')
  const [showInactive, setShowInactive] = useState(false)
  const [editing, setEditing] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const list = useFetch('/roles/', { page, page_size: PAGE_SIZE, name: appliedName, include_inactive: showInactive })
  const del = useSubmit()
  const manage = can('role.manage')

  const columns = [
    { key: 'code', header: 'Code' },
    { key: 'name', header: 'Name' },
    { key: 'is_system', header: 'Type', render: (r) => <StatusBadge tone={r.is_system ? 'info' : 'neutral'}>{r.is_system ? 'System' : 'Custom'}</StatusBadge> },
    { key: 'permission_codes', header: 'Permissions', render: (r) => r.permission_codes.length },
    { key: 'is_active', header: 'Status', render: (r) => <ActiveBadge active={r.is_active} /> },
    {
      key: 'actions', header: '', className: 'actions',
      render: (r) => (
        <div className="row">
          <Button size="sm" onClick={() => navigate(`/roles/${r.public_id}`)}>View</Button>
          {manage && !r.is_system && r.is_active && <Button size="sm" onClick={() => setEditing(r)}>Edit</Button>}
          {manage && !r.is_system && r.is_active && <Button size="sm" variant="danger" onClick={() => setDeleting(r)}>Delete</Button>}
        </div>
      ),
    },
  ]

  const confirmDelete = async () => {
    const res = await del.run(() => api.delete(`/roles/${deleting.public_id}/`, { params: { row_version: deleting.row_version } }))
    if (res) { setDeleting(null); toast.success('Role deleted.'); list.reload() }
  }

  return (
    <>
      <div className="page-head">
        <h1>Roles</h1><span className="spacer" />
        <PermissionGate code="role.manage"><Button variant="primary" onClick={() => setEditing('new')}>New custom role</Button></PermissionGate>
      </div>
      <form className="filters" onSubmit={(e) => { e.preventDefault(); setPage(1); setAppliedName(name) }}>
        <FormField label="Name" name="f_role_name" value={name} onChange={(e) => setName(e.target.value)} />
        <Button type="submit">Search</Button>
        <PermissionGate code="role.manage">
          <label className="check"><input type="checkbox" checked={showInactive} onChange={(e) => { setPage(1); setShowInactive(e.target.checked) }} /> Show inactive</label>
        </PermissionGate>
      </form>
      {list.error && <div className="alert alert-danger">{list.error.message}</div>}
      <Table columns={columns} rows={list.data?.results} loading={list.loading} />
      <Pagination page={page} pageSize={PAGE_SIZE} count={list.data?.count ?? 0} onPageChange={setPage} />

      {editing && (
        <RoleFormModal
          role={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onStale={list.reload}
          onSaved={(saved, isNew) => {
            setEditing(null)
            toast.success(isNew ? 'Role created. Set its permissions next.' : 'Role updated.')
            if (isNew) navigate(`/roles/${saved.public_id}`); else list.reload()
          }}
        />
      )}
      {deleting && (
        <Modal title="Delete role" onClose={() => setDeleting(null)}
          footer={<><Button onClick={() => setDeleting(null)}>Cancel</Button><Button variant="danger" loading={del.busy} onClick={confirmDelete}>Delete</Button></>}>
          <FormError error={del.error} />
          <p>Deactivate role <strong>{deleting.name}</strong>? Users holding it lose its permissions.</p>
        </Modal>
      )}
    </>
  )
}