import { useState } from 'react'
import { Button, Modal } from '../ui'
import { ErrBox, parseApiError } from './shared.jsx'

// Confirm dialog in the style of the existing pages. onConfirm may throw; the error is shown inside the dialog.
export default function ConfirmModal({ title, children, confirmLabel = 'Delete', onConfirm, onClose }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  async function go() {
    setBusy(true)
    setError(null)
    try {
      await onConfirm()
    } catch (err) {
      console.error('[billing] confirmed action failed', err)
      setError(parseApiError(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal title={title} onClose={onClose}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="danger" loading={busy} onClick={go}>{confirmLabel}</Button></>}>
      <ErrBox error={error} />
      {children}
    </Modal>
  )
}
