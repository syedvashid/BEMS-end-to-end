import { useState } from 'react'
import { Button, FormField, Modal } from '../ui'
import {
  ACTION_TYPES, Check, ErrorBox, NOTICE_TYPES, SOURCES, URGENCIES, api, fieldError, nn, opt, useAction, useForm,
  useOptions, withBlank,
} from './shared'

function ModelPicker({ value, onChange, disabled, error }) {
  const models = useOptions('/equipment-models/', (m) => ({ value: m.public_id, label: `${m.model_name} (${m.model_number})` }))
  const [q, setQ] = useState('')
  const shown = models.filter((o) => o.label.toLowerCase().includes(q.toLowerCase()))
  const toggle = (id) => onChange(value.includes(id) ? value.filter((x) => x !== id) : [...value, id])
  return (
    <div>
      <label>Affected equipment models *</label>
      <input placeholder="Filter models…" value={q} onChange={(e) => setQ(e.target.value)} disabled={disabled} />
      <div style={{ maxHeight: 180, overflowY: 'auto' }}>
        {shown.map((o) => (
          <div key={o.value}><label><input type="checkbox" checked={value.includes(o.value)} disabled={disabled} onChange={() => toggle(o.value)} /> {o.label}</label></div>
        ))}
        {!shown.length && <p className="muted">No models found.</p>}
      </div>
      <div className="hint">{value.length} selected. The first 100 models are listed.</div>
      {error && <div className="alert alert-danger">{String(error)}</div>}
    </div>
  )
}

/** Create (notice undefined) or edit (notice = detail payload) a recall notice. */
export default function RecallFormModal({ notice, onClose, onDone }) {
  const edit = !!notice
  const hasUnits = edit && (notice.counts?.units || 0) > 0
  const vendors = useOptions('/vendors/', (x) => ({ value: x.public_id, label: x.name }))
  const { v, setV, bind } = useForm({
    title: notice?.title || '', notice_type: notice?.notice_type || 'RECALL', source: notice?.source || 'MANUFACTURER',
    issued_by_vendor: notice?.issued_by_vendor?.public_id || '', issued_date: notice?.issued_date || '',
    received_date: notice?.received_date || '', urgency: notice?.urgency || 'MEDIUM', action_type: notice?.action_type || 'INSPECT',
    stop_use: notice?.stop_use || false, reference_number: notice?.reference_number || '',
    description: notice?.description || '', required_action: notice?.required_action || '',
    affected_serials_note: notice?.affected_serials_note || '',
  })
  const [models, setModels] = useState((notice?.models || []).map((m) => m.public_id))
  const act = useAction()
  const forced = v.action_type === 'STOP_USE'

  const submit = async () => {
    const body = {
      title: v.title.trim(), notice_type: v.notice_type, source: v.source, issued_by_vendor: nn(v.issued_by_vendor),
      issued_date: nn(v.issued_date), received_date: nn(v.received_date), urgency: v.urgency, action_type: v.action_type,
      stop_use: forced ? true : v.stop_use, reference_number: nn(v.reference_number.trim()),
      description: v.description.trim(), required_action: nn(v.required_action.trim()),
      affected_serials_note: nn(v.affected_serials_note.trim()), models,
    }
    const r = await act.run(() => (edit
      ? api.patch(`/recall-notices/${notice.public_id}/`, { ...body, row_version: notice.row_version })
      : api.post('/recall-notices/', body)))
    if (r.ok) onDone(r.data.data)
  }

  return (
    <Modal title={edit ? `Edit ${notice.notice_number}` : 'New recall / field safety notice'} wide onClose={onClose}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={act.busy} onClick={submit}>Save</Button></>}>
      <ErrorBox error={act.error} />
      {hasUnits && <div className="alert alert-warning">Affected units exist, so “stop use” and the model list can no longer change.</div>}
      <FormField label="Title" required {...bind('title')} error={fieldError(act.error, 'title')} />
      <FormField label="Notice type" as="select" required options={opt(NOTICE_TYPES)} {...bind('notice_type')} error={fieldError(act.error, 'notice_type')} />
      <FormField label="Source" as="select" required options={opt(SOURCES)} {...bind('source')} error={fieldError(act.error, 'source')} />
      <FormField label="Issuing vendor" as="select" options={withBlank(vendors, '— none —')} {...bind('issued_by_vendor')} error={fieldError(act.error, 'issued_by_vendor')} />
      <FormField label="Manufacturer / regulator reference" {...bind('reference_number')} error={fieldError(act.error, 'reference_number')} />
      <FormField label="Issued date" type="date" {...bind('issued_date')} error={fieldError(act.error, 'issued_date')} />
      <FormField label="Received date" type="date" {...bind('received_date')} error={fieldError(act.error, 'received_date')} />
      <FormField label="Urgency" as="select" required options={opt(URGENCIES)} {...bind('urgency')} error={fieldError(act.error, 'urgency')} />
      <FormField label="Action required" as="select" required options={opt(ACTION_TYPES)} {...bind('action_type')} error={fieldError(act.error, 'action_type')} />
      <Check label="Stop use (take affected units out of service)" checked={forced || v.stop_use} disabled={forced || hasUnits}
        onChange={(e) => setV((p) => ({ ...p, stop_use: e.target.checked }))}
        hint={forced ? 'Always on when the action is “Stop use”.' : 'Holds are placed only on commissioned units.'} />
      <FormField label="Description" as="textarea" required {...bind('description')} error={fieldError(act.error, 'description')} />
      <FormField label="Required action details" as="textarea" {...bind('required_action')} error={fieldError(act.error, 'required_action')} />
      <FormField label="Affected serials (note)" as="textarea" {...bind('affected_serials_note')} error={fieldError(act.error, 'affected_serials_note')} />
      <ModelPicker value={models} onChange={setModels} disabled={hasUnits} error={fieldError(act.error, 'models')} />
    </Modal>
  )
}
