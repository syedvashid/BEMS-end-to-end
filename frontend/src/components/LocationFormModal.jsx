import { useMemo, useState } from 'react'
import { api } from '../api/client'
import useFetch from '../hooks/useFetch'
import useSubmit from '../hooks/useSubmit'
import { fieldError } from '../utils/errors'
import { opts, toForm, toPayload } from '../utils/formHelpers'
import { Button, FormError, FormField, Modal } from './ui'

export const ALL_TYPES = ['BUILDING', 'FLOOR', 'WARD', 'ROOM', 'BED', 'STORE', 'OTHER']
const ALLOWED = { FLOOR: ['BUILDING'], WARD: ['FLOOR'], ROOM: ['FLOOR', 'WARD'], BED: ['ROOM', 'WARD'], STORE: ['BUILDING', 'FLOOR'] }
// Mirrors the server rule: can a location of type `t` sit under a parent of type `parentType`?
export const parentOk = (t, parentType) => t === 'OTHER' || (ALLOWED[t] || []).includes(parentType)

export function flatten(nodes, out = []) {
  for (const n of nodes) { out.push(n); flatten(n.children, out) }
  return out
}
function findNode(nodes, id) {
  for (const n of nodes) {
    if (n.public_id === id) return n
    const hit = findNode(n.children, id)
    if (hit) return hit
  }
  return null
}

const EMPTY = { parent_location: '', location_type: 'BUILDING', code: '', name: '', department: '', description: '' }

export default function LocationFormModal({ location, presetParent, tree, onClose, onSaved, onStale }) {
  const isEdit = Boolean(location)
  const flat = useMemo(() => flatten(tree), [tree])
  const excluded = useMemo(() => {
    if (!location) return new Set()
    const self = findNode(tree, location.public_id)
    return new Set(self ? flatten([self]).map((n) => n.public_id) : [location.public_id])   // self + descendants
  }, [tree, location])

  const typeOptions = isEdit ? ALL_TYPES
    : presetParent ? ALL_TYPES.filter((t) => parentOk(t, presetParent.location_type))
      : ['BUILDING', 'OTHER']

  const [form, setForm] = useState(() => {
    const f = toForm(EMPTY, location)
    if (!isEdit) { f.parent_location = presetParent?.public_id ?? ''; f.location_type = typeOptions[0] }
    return f
  })
  const { busy, error, run } = useSubmit((e) => { if (e.code === 'stale_version' && onStale) onStale() })
  const depts = useFetch('/departments/', { page_size: 100 })
  const set = (name) => (e) => setForm((f) => ({ ...f, [name]: e.target.value }))
  const err = (name) => fieldError(error, name)

  const setType = (e) => {
    const t = e.target.value
    setForm((f) => {
      const cur = flat.find((n) => n.public_id === f.parent_location)
      const ok = !f.parent_location || (cur && parentOk(t, cur.location_type))
      return { ...f, location_type: t, parent_location: ok ? f.parent_location : '' }
    })
  }

  const parentOptions = [{ value: '', label: '— none —' }].concat(
    flat.filter((n) => !excluded.has(n.public_id) && parentOk(form.location_type, n.location_type))
      .map((n) => ({ value: n.public_id, label: `${n.location_type}: ${n.code} - ${n.name}` })),
  )
  const deptOptions = [{ value: '', label: '— none —' }].concat(
    (depts.data?.results ?? []).map((d) => ({ value: d.public_id, label: `${d.code} - ${d.name}` })),
  )

  const submit = async (e) => {
    e.preventDefault()
    const body = toPayload(form)
    const res = await run(() => (isEdit
      ? api.patch(`/locations/${location.public_id}/`, { ...body, row_version: location.row_version })
      : api.post('/locations/', body)))
    if (res) onSaved(res.data, !isEdit)
  }

  return (
    <Modal wide title={isEdit ? 'Edit location' : 'New location'} onClose={onClose}
      footer={<>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" type="submit" form="location-form" loading={busy}>Save</Button>
      </>}>
      <form id="location-form" onSubmit={submit}>
        <FormError error={error} />
        <div className="form-grid">
          <FormField label="Type" name="location_type" as="select" options={opts(typeOptions)} value={form.location_type} onChange={setType} error={err('location_type')} />
          <FormField label="Parent location" name="parent_location" as="select" options={parentOptions} value={form.parent_location} onChange={set('parent_location')} error={err('parent_location')}
            hint={form.location_type === 'BUILDING' ? 'A building has no parent.' : 'Only valid parent types are listed.'} />
          <FormField label="Code" name="code" required value={form.code} onChange={set('code')} error={err('code')} maxLength={30} />
          <FormField label="Name" name="name" required value={form.name} onChange={set('name')} error={err('name')} maxLength={200} />
          <FormField label="Department" name="department" as="select" options={deptOptions} value={form.department} onChange={set('department')} error={err('department')} />
          <FormField label="Description" name="description" as="textarea" value={form.description} onChange={set('description')} error={err('description')} maxLength={500} />
        </div>
      </form>
    </Modal>
  )
}