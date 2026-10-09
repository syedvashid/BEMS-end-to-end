import { useState } from 'react'
import { api } from '../api/client'
import { parseApiError } from '../utils/errors'
import { friendly } from '../utils/equipment'
import EquipmentFields, { buildPayload, emptyForm } from './EquipmentFields'
import { Button, Modal } from './ui'

export default function EquipmentFormModal({ onClose, onDone }) {
  const [f, setF] = useState(emptyForm)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const submit = async () => {
    setBusy(true); setErr(null)
    try {
      const { data } = await api.post('/equipment/', buildPayload(f))
      onDone(data)
    } catch (e) { setErr(parseApiError(e)); setBusy(false) }
  }

  return (
    <Modal title="Register equipment" onClose={onClose} wide
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} onClick={submit}>Register</Button></>}>
      {err && err.code !== 'validation_error' && <div className="alert alert-danger">{friendly(err)}</div>}
      <EquipmentFields f={f} setF={setF} err={err} />
    </Modal>
  )
}
