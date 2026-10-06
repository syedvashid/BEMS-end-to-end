import { useState } from 'react'
import { api } from '../api/client'
import ConfirmDeleteModal from '../components/ConfirmDeleteModal'
import LocationFormModal from '../components/LocationFormModal'
import PermissionGate from '../components/PermissionGate'
import { Button, FormError, useToast } from '../components/ui'
import { useFacility } from '../context/FacilityContext'
import useFetch from '../hooks/useFetch'
import useSubmit from '../hooks/useSubmit'

function TreeNode({ node, depth, can, onAddChild, onEdit, onDelete }) {
  return (
    <>
      <div className="loc-row" style={{ paddingLeft: 12 + depth * 24 }}>
        <span className="loc-type">{node.location_type}</span>
        <strong>{node.code}</strong>
        <span>{node.name}</span>
        {node.department_name && <span className="loc-dept">{node.department_name}</span>}
        <span className="spacer" />
        <div className="row">
          {can('location.add') && <Button size="sm" onClick={() => onAddChild(node)}>Add child</Button>}
          {can('location.change') && <Button size="sm" onClick={() => onEdit(node)}>Edit</Button>}
          {can('location.delete') && <Button size="sm" variant="danger" onClick={() => onDelete(node)}>Delete</Button>}
        </div>
      </div>
      {node.children.map((c) => (
        <TreeNode key={c.public_id} node={c} depth={depth + 1} can={can} onAddChild={onAddChild} onEdit={onEdit} onDelete={onDelete} />
      ))}
    </>
  )
}

export default function LocationsPage() {
  const { can } = useFacility()
  const toast = useToast()
  const tree = useFetch('/locations/tree/', {})
  const [editing, setEditing] = useState(null)    // { record?, parent? }
  const [deleting, setDeleting] = useState(null)  // full record (has row_version)
  const loader = useSubmit()

  // The tree has no row_version, so load the full record before editing/deleting.
  const openWith = async (node, kind) => {
    const res = await loader.run(() => api.get(`/locations/${node.public_id}/`))
    if (!res) return
    if (kind === 'edit') setEditing({ record: res.data })
    else setDeleting(res.data)
  }

  return (
    <>
      <div className="page-head">
        <h1>Locations</h1><span className="spacer" />
        <PermissionGate code="location.add"><Button variant="primary" onClick={() => setEditing({})}>New top-level location</Button></PermissionGate>
      </div>
      <FormError error={loader.error} />
      {tree.error && <div className="alert alert-danger">{tree.error.message}</div>}
      <div className="loc-tree">
        {tree.loading && <p>Loading…</p>}
        {!tree.loading && tree.data?.length === 0 && <p className="muted">No locations yet.</p>}
        {tree.data?.map((n) => (
          <TreeNode key={n.public_id} node={n} depth={0} can={can}
            onAddChild={(p) => setEditing({ parent: p })}
            onEdit={(node) => openWith(node, 'edit')}
            onDelete={(node) => openWith(node, 'delete')} />
        ))}
      </div>

      {editing && (
        <LocationFormModal
          location={editing.record ?? null} presetParent={editing.parent ?? null} tree={tree.data ?? []}
          onClose={() => setEditing(null)} onStale={tree.reload}
          onSaved={(_, isNew) => { setEditing(null); toast.success(isNew ? 'Location created.' : 'Location updated.'); tree.reload() }}
        />
      )}
      {deleting && (
        <ConfirmDeleteModal
          title="Delete location" label={`${deleting.code} - ${deleting.name}`}
          path={`/locations/${deleting.public_id}/`} rowVersion={deleting.row_version}
          onClose={() => setDeleting(null)} onStale={tree.reload}
          onDone={() => { setDeleting(null); toast.success('Location deleted.'); tree.reload() }}
        />
      )}
    </>
  )
}