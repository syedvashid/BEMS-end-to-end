import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import RoleFormModal from '../components/RoleFormModal'
import { ActiveBadge, Button, FormError, StatusBadge, useToast } from '../components/ui'
import { useFacility } from '../context/FacilityContext'
import useFetch from '../hooks/useFetch'
import useSubmit from '../hooks/useSubmit'

export default function RoleDetailPage() {
  const { publicId } = useParams()
  const { can } = useFacility()
  const toast = useToast()
  const roleQ = useFetch(`/roles/${publicId}/`)
  const permsQ = useFetch('/permissions/')
  const role = roleQ.data
  const [selected, setSelected] = useState(new Set())
  const [editing, setEditing] = useState(false)
  const { busy, error, run } = useSubmit((e) => { if (e.code === 'stale_version') roleQ.reload() })

  useEffect(() => { if (role) setSelected(new Set(role.permission_codes)) }, [role])

  const permissions = useMemo(() => (Array.isArray(permsQ.data) ? permsQ.data : (permsQ.data?.results ?? [])), [permsQ.data])
  const byModule = useMemo(() => {
    const groups = {}
    for (const p of permissions) (groups[p.module] ??= []).push(p)
    return groups
  }, [permissions])

  if (roleQ.loading && !role) return <p className="muted">Loading…</p>
  if (roleQ.error) return <div className="alert alert-danger">{roleQ.error.message} <Link to="/roles">Back to roles</Link></div>
  if (!role) return null

  const editable = can('role.manage') && !role.is_system
  const original = new Set(role.permission_codes)
  const dirty = selected.size !== original.size || [...selected].some((c) => !original.has(c))
  const toggle = (code) => setSelected((s) => { const n = new Set(s); if (n.has(code)) n.delete(code); else n.add(code); return n })

  const save = async () => {
    const res = await run(() => api.put(`/roles/${role.public_id}/permissions/`, { permission_codes: [...selected], row_version: role.row_version }))
    if (res) { toast.success('Permissions saved.'); roleQ.reload() }
  }

  return (
    <>
      <div className="page-head">
        <Link to="/roles">← Roles</Link>
        <h1>{role.name}</h1>
        <span className="mono">{role.code}</span>
        <StatusBadge tone={role.is_system ? 'info' : 'neutral'}>{role.is_system ? 'System' : 'Custom'}</StatusBadge>
        <ActiveBadge active={role.is_active} />
        <span className="spacer" />
        {editable && <Button onClick={() => setEditing(true)}>Edit details</Button>}
      </div>
      {role.description && <p className="muted">{role.description}</p>}
      {role.is_system && <div className="alert alert-info">System roles are read-only.</div>}
      <FormError error={error} />
      <div className="card">
        <h2>Permission matrix</h2>
        <table className="matrix">
          <tbody>
            {Object.entries(byModule).map(([module, items]) => (
              <tr key={module}>
                <td className="module">{module}</td>
                <td>
                  <div className="perms">
                    {items.map((p) => (
                      <label key={p.code} className="check" title={p.description ?? undefined}>
                       <input type="checkbox" checked={selected.has(p.code)} disabled={!editable || !can(p.code)} onChange={() => toggle(p.code)} />
                        {p.code}
                      </label>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {editable && <div className="row" style={{ marginTop: 12 }}><Button variant="primary" disabled={!dirty} loading={busy} onClick={save}>Save permissions</Button></div>}
      </div>
      {editing && (
        <RoleFormModal role={role} onClose={() => setEditing(false)} onStale={roleQ.reload}
          onSaved={() => { setEditing(false); toast.success('Role updated.'); roleQ.reload() }} />
      )}
    </>
  )
}