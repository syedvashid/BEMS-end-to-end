import { useState } from 'react'
import { api } from '../api/client'
import useSubmit from '../hooks/useSubmit'
import { fieldError } from '../utils/errors'
import { opts, toForm, toPayload } from '../utils/formHelpers'
import { Button, FormError, FormField, Modal } from './ui'

export const SOURCE_TYPES = ['OWN_FUNDS', 'GRANT', 'DONATION', 'CSR', 'GOVERNMENT_SCHEME', 'LEASE_LOAN', 'OTHER']
const EMPTY = { code: '', name: '', source_type: 'OWN_FUNDS', description: '' }

export default function FundingSourceFormModal({ source, onClose, onSaved, onStale }) {
  const isEdit = Boolean(source)
  const [form, setForm] = useState(() => toForm(EMPTY, source))
  const { busy, error, run } = useSubmit((e) => { if (e.code === 'stale_version' && onStale) onStale() })
  const set = (name) => (e) => setForm((f) => ({ ...f, [name]: e.target.value }))
  const err = (name) => fieldError(error, name)

  const submit = async (e) => {
    e.preventDefault()
    const body = toPayload(form)
    const res = await run(() => (isEdit
      ? api.patch(`/funding-sources/${source.public_id}/`, { ...body, row_version: source.row_version })
      : api.post('/funding-sources/', body)))
    if (res) onSaved(res.data, !isEdit)
  }

  return (
    <Modal title={isEdit ? 'Edit funding source' : 'New funding source'} onClose={onClose}
      footer={<>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" type="submit" form="funding-form" loading={busy}>Save</Button>
      </>}>
      <form id="funding-form" onSubmit={submit}>
        <FormError error={error} />
        <div className="form-grid">
          <FormField label="Code" name="code" required value={form.code} onChange={set('code')} error={err('code')} maxLength={30} />
          <FormField label="Name" name="name" required value={form.name} onChange={set('name')} error={err('name')} maxLength={200} />
          <FormField label="Type" name="source_type" as="select" options={opts(SOURCE_TYPES)} value={form.source_type} onChange={set('source_type')} error={err('source_type')} />
          <FormField label="Description" name="description" as="textarea" value={form.description} onChange={set('description')} error={err('description')} maxLength={500} />
        </div>
      </form>
    </Modal>
  )
}