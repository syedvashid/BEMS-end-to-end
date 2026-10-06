import { useState } from 'react'
import { api } from '../api/client'
import useSubmit from '../hooks/useSubmit'
import { fieldError } from '../utils/errors'
import { opts, toForm, toPayload } from '../utils/formHelpers'
import { Button, FormError, FormField, Modal } from './ui'

const TYPES = opts(['CLINICAL', 'DIAGNOSTIC', 'SUPPORT', 'ADMINISTRATIVE'])
const EMPTY = { code: '', name: '', department_type: 'CLINICAL', description: '' }

export default function DepartmentFormModal({ department, onClose, onSaved, onStale }) {
  const isEdit = Boolean(department)
  const [form, setForm] = useState(() => toForm(EMPTY, department))
  const { busy, error, run } = useSubmit((e) => { if (e.code === 'stale_version' && onStale) onStale() })
  const set = (name) => (e) => setForm((f) => ({ ...f, [name]: e.target.value }))
  const err = (name) => fieldError(error, name)

  const submit = async (e) => {
    e.preventDefault()
    const body = toPayload(form)
    const res = await run(() => (isEdit
      ? api.patch(`/departments/${department.public_id}/`, { ...body, row_version: department.row_version })
      : api.post('/departments/', body)))
    if (res) onSaved(res.data, !isEdit)
  }

  return (
    <Modal title={isEdit ? 'Edit department' : 'New department'} onClose={onClose}
      footer={<>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" type="submit" form="department-form" loading={busy}>Save</Button>
      </>}>
      <form id="department-form" onSubmit={submit}>
        <FormError error={error} />
        <div className="form-grid">
          <FormField label="Code" name="code" required value={form.code} onChange={set('code')} error={err('code')} maxLength={30} />
          <FormField label="Name" name="name" required value={form.name} onChange={set('name')} error={err('name')} maxLength={200} />
          <FormField label="Type" name="department_type" as="select" options={TYPES} value={form.department_type} onChange={set('department_type')} error={err('department_type')} />
          <FormField label="Description" name="description" as="textarea" value={form.description} onChange={set('description')} error={err('description')} maxLength={500} />
        </div>
      </form>
    </Modal>
  )
}