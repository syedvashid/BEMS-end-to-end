import { useState } from 'react'
import { api } from '../api/client'
import useSubmit from '../hooks/useSubmit'
import { fieldError } from '../utils/errors'
import { Button, FormError, FormField, Modal } from './ui'

export default function RoleFormModal({ role, onClose, onSaved, onStale }) {
  const isEdit = Boolean(role)
  const [form, setForm] = useState({ code: role?.code ?? '', name: role?.name ?? '', description: role?.description ?? '' })
  const { busy, error, run } = useSubmit((e) => { if (e.code === 'stale_version' && onStale) onStale() })
  const set = (name) => (e) => setForm((f) => ({ ...f, [name]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    const payload = { code: form.code.trim().toUpperCase(), name: form.name.trim(), description: form.description.trim() || null }
    const res = await run(() => (isEdit
      ? api.patch(`/roles/${role.public_id}/`, { ...payload, row_version: role.row_version })
      : api.post('/roles/', payload)))
    if (res) onSaved(res.data, !isEdit)
  }

  return (
    <Modal title={isEdit ? 'Edit role' : 'New custom role'} onClose={onClose}
      footer={<>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" type="submit" form="role-form" loading={busy}>Save</Button>
      </>}>
      <form id="role-form" onSubmit={submit}>
        <FormError error={error} />
        <FormField label="Code" name="code" required value={form.code} onChange={set('code')} error={fieldError(error, 'code')} hint="A-Z, 0-9 and _" />
        <FormField label="Name" name="name" required value={form.name} onChange={set('name')} error={fieldError(error, 'name')} />
        <FormField label="Description" name="description" as="textarea" value={form.description} onChange={set('description')} error={fieldError(error, 'description')} />
      </form>
    </Modal>
  )
}