import { useState } from 'react'
import { api } from '../api/client'
import useSubmit from '../hooks/useSubmit'
import { fieldError } from '../utils/errors'
import { Button, FormError, FormField, Modal } from './ui'

const EMPTY = { username: '', full_name: '', email: '', phone: '', employee_code: '', designation: '' }

export default function UserFormModal({ user, onClose, onSaved, onStale }) {
  const isEdit = Boolean(user)
  const [form, setForm] = useState(() => {
    const out = { ...EMPTY }
    if (user) for (const k of Object.keys(EMPTY)) out[k] = user[k] ?? ''
    return out
  })
  const { busy, error, run } = useSubmit((e) => { if (e.code === 'stale_version' && onStale) onStale() })
  const set = (name) => (e) => setForm((f) => ({ ...f, [name]: e.target.value }))
  const err = (name) => fieldError(error, name)

  const submit = async (e) => {
    e.preventDefault()
    const payload = {}
    for (const [k, v] of Object.entries(form)) payload[k] = v.trim() === '' ? null : v.trim()
    const res = await run(() => (isEdit
      ? api.patch(`/users/${user.public_id}/`, { ...payload, row_version: user.row_version })
      : api.post('/users/', payload)))
    if (res) onSaved(res.data, !isEdit)
  }

  return (
    <Modal title={isEdit ? 'Edit user' : 'New user'} onClose={onClose}
      footer={<>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" type="submit" form="user-form" loading={busy}>Save</Button>
      </>}>
      <form id="user-form" onSubmit={submit}>
        <FormError error={error} />
        <FormField label="Username" name="username" required value={form.username} onChange={set('username')} error={err('username')} maxLength={64} />
        <FormField label="Full name" name="full_name" required value={form.full_name} onChange={set('full_name')} error={err('full_name')} />
        <FormField label="Email" name="email" type="email" value={form.email} onChange={set('email')} error={err('email')} />
        <FormField label="Phone" name="phone" value={form.phone} onChange={set('phone')} error={err('phone')} />
        <FormField label="Employee code" name="employee_code" value={form.employee_code} onChange={set('employee_code')} error={err('employee_code')} />
        <FormField label="Designation" name="designation" value={form.designation} onChange={set('designation')} error={err('designation')} />
      </form>
    </Modal>
  )
}