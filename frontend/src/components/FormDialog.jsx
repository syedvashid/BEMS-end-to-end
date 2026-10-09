import { useState } from 'react'
import { Button, FormField, Modal } from './ui'
import { apiError, errorText, fe } from '../utils/maintenance'

// Generic dialog. fields: [{ name, label, as, type, required, options, hint, initial }]
// onSubmit(values) must return a promise; errors from the API are shown inline.
export default function FormDialog({ title, fields, onSubmit, onClose, submitLabel = 'Save', intro, danger }) {
  const [values, setValues] = useState(() => Object.fromEntries(fields.map((f) => [f.name, f.initial ?? ''])))
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const set = (name) => (e) => setValues((v) => ({ ...v, [name]: e.target.value }))
  const submit = async () => {
    setBusy(true); setErr(null)
    try { await onSubmit(values) } catch (e) { setErr(apiError(e)) } finally { setBusy(false) }
  }
  return (
    <Modal title={title} onClose={onClose}
      footer={(
        <>
          <Button variant="secondary" onClick={onClose}>Close</Button>
          <Button variant={danger ? 'danger' : 'primary'} loading={busy} onClick={submit}>{submitLabel}</Button>
        </>
      )}>
      {intro && <p className="muted">{intro}</p>}
      {err && !Object.keys(err.details || {}).length && <div className="alert alert-danger">{errorText(err)}</div>}
      {err && err.code === 'stale_version' && <div className="alert alert-danger">{errorText(err)}</div>}
      {fields.map((f) => (
        <FormField key={f.name} label={f.label} name={f.name} as={f.as} type={f.type} options={f.options}
          required={f.required} hint={f.hint} value={values[f.name]} onChange={set(f.name)} error={fe(err, f.name)} />
      ))}
    </Modal>
  )
}
