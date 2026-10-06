import { api } from '../api/client'
import useSubmit from '../hooks/useSubmit'
import { Button, FormError, Modal } from './ui'

// Soft delete. A 409 conflict (active dependents) is shown inside the modal.
export default function ConfirmDeleteModal({ title, label, path, rowVersion, onClose, onDone, onStale }) {
  const { busy, error, run } = useSubmit((e) => { if (e.code === 'stale_version' && onStale) onStale() })
  const confirm = async () => {
    const res = await run(() => api.delete(path, { params: { row_version: rowVersion } }))
    if (res) onDone()
  }
  return (
    <Modal title={title} onClose={onClose}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="danger" loading={busy} onClick={confirm}>Delete</Button></>}>
      <FormError error={error} />
      <p>Deactivate <strong>{label}</strong>? The record is kept (soft delete) but is hidden from lists.</p>
    </Modal>
  )
}