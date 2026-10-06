import { useState } from 'react'
import { api } from '../api/client'
import useFetch from '../hooks/useFetch'
import useSubmit from '../hooks/useSubmit'
import { useFacility } from '../context/FacilityContext'
import { fieldError } from '../utils/errors'
import { dash, opts, toForm, toPayload } from '../utils/formHelpers'
import ConfirmDeleteModal from './ConfirmDeleteModal'
import { Button, FormError, FormField, Modal, Table, useToast } from './ui'

const TYPES = opts(['SALES', 'SERVICE', 'ESCALATION', 'OTHER'])
const EMPTY = { name: '', designation: '', phone: '', email: '', contact_type: 'SALES', is_primary: false }

function ContactFormModal({ vendor, contact, onClose, onSaved, onStale }) {
  const isEdit = Boolean(contact)
  const [form, setForm] = useState(() => toForm(EMPTY, contact))
  const { busy, error, run } = useSubmit((e) => { if (e.code === 'stale_version' && onStale) onStale() })
  const set = (name) => (e) => setForm((f) => ({ ...f, [name]: e.target.value }))
  const err = (name) => fieldError(error, name)

  const submit = async (e) => {
    e.preventDefault()
    const body = { ...toPayload(form), vendor: vendor.public_id }
    const res = await run(() => (isEdit
      ? api.patch(`/vendor-contacts/${contact.public_id}/`, { ...body, row_version: contact.row_version })
      : api.post('/vendor-contacts/', body)))
    if (res) onSaved(res.data, !isEdit)
  }

  return (
    <Modal title={isEdit ? 'Edit contact' : 'New contact'} onClose={onClose}
      footer={<>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" type="submit" form="contact-form" loading={busy}>Save</Button>
      </>}>
      <form id="contact-form" onSubmit={submit}>
        <FormError error={error} />
        <div className="form-grid">
          <FormField label="Name" name="name" required value={form.name} onChange={set('name')} error={err('name')} maxLength={200} />
          <FormField label="Designation" name="designation" value={form.designation} onChange={set('designation')} error={err('designation')} maxLength={100} />
          <FormField label="Phone" name="phone" value={form.phone} onChange={set('phone')} error={err('phone')} />
          <FormField label="Email" name="email" type="email" value={form.email} onChange={set('email')} error={err('email')} />
          <FormField label="Contact type" name="contact_type" as="select" options={TYPES} value={form.contact_type} onChange={set('contact_type')} error={err('contact_type')} />
          <label className="checkbox-row">
            <input type="checkbox" checked={form.is_primary} onChange={(e) => setForm((f) => ({ ...f, is_primary: e.target.checked }))} /> Primary contact
          </label>
        </div>
      </form>
    </Modal>
  )
}

export default function VendorContactsPanel({ vendor }) {
  const { can } = useFacility()
  const toast = useToast()
  const list = useFetch('/vendor-contacts/', { vendor: vendor.public_id, page_size: 100 })
  const [editing, setEditing] = useState(null)
  const [deleting, setDeleting] = useState(null)

  const columns = [
    { key: 'name', header: 'Name', render: (r) => <>{r.name} {r.is_primary && <span className="primary-tag">Primary</span>}</> },
    { key: 'designation', header: 'Designation', render: (r) => dash(r.designation) },
    { key: 'contact_type', header: 'Type' },
    { key: 'phone', header: 'Phone', render: (r) => dash(r.phone) },
    { key: 'email', header: 'Email', render: (r) => dash(r.email) },
    {
      key: 'actions', header: '', className: 'actions',
      render: (r) => (
        <div className="row">
          {can('vendor.change') && <Button size="sm" onClick={() => setEditing(r)}>Edit</Button>}
          {can('vendor.delete') && <Button size="sm" variant="danger" onClick={() => setDeleting(r)}>Delete</Button>}
        </div>
      ),
    },
  ]

  return (
    <section className="panel">
      <div className="page-head">
        <h2>Contacts — {vendor.name}</h2><span className="spacer" />
        {can('vendor.add') && <Button variant="primary" onClick={() => setEditing('new')}>Add contact</Button>}
      </div>
      {list.error && <div className="alert alert-danger">{list.error.message}</div>}
      <Table columns={columns} rows={list.data?.results} loading={list.loading} empty="No contacts yet." />

      {editing && (
        <ContactFormModal
          vendor={vendor} contact={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)} onStale={list.reload}
          onSaved={(_, isNew) => { setEditing(null); toast.success(isNew ? 'Contact added.' : 'Contact updated.'); list.reload() }}
        />
      )}
      {deleting && (
        <ConfirmDeleteModal
          title="Delete contact" label={deleting.name}
          path={`/vendor-contacts/${deleting.public_id}/`} rowVersion={deleting.row_version}
          onClose={() => setDeleting(null)} onStale={list.reload}
          onDone={() => { setDeleting(null); toast.success('Contact deleted.'); list.reload() }}
        />
      )}
    </section>
  )
}