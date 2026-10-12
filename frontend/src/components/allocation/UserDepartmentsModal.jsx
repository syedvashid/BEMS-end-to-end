import { useEffect, useState } from 'react'
import { useToast } from '../ui'
import { ApiAlert, Button, Check, Modal, api, useAction, useFetch } from './shared'

export default function UserDepartmentsModal({ user, onClose, onSaved }) {
  const toast = useToast()
  const cur = useFetch(`/users/${user.public_id}/departments/`)
  const all = useFetch('/departments/', { page_size: 100 })
  const [sel, setSel] = useState(null)
  const { busy, error, run } = useAction()
  useEffect(() => { if (cur.data && sel === null) setSel(new Set(cur.data.departments.map((d) => d.public_id))) }, [cur.data, sel])
  const toggle = (id) => setSel((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n })
  const save = () => run(async () => {
    await api.put(`/users/${user.public_id}/departments/`, { departments: [...sel] })
    toast.success('Departments saved.'); onSaved()
  })
  const rows = all.data?.results || []
  return (
    <Modal title={`Departments · ${user.full_name || user.username}`} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Close</Button>
        <Button variant="primary" loading={busy} disabled={sel === null} onClick={save}>Save</Button></>}>
      <ApiAlert error={error} />
      <p className="muted">Departments this user may reserve equipment for and request transfers to, in this facility.</p>
      {sel === null ? <p className="muted">Loading…</p> : rows.map((d) => (
        <div key={d.public_id}><Check label={`${d.code} – ${d.name}`} checked={sel.has(d.public_id)} onChange={() => toggle(d.public_id)} /></div>
      ))}
    </Modal>
  )
}