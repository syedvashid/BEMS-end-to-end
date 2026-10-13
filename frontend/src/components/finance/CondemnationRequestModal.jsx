import { useState } from 'react'
import { api } from '../../api/client'
import useFetch from '../../hooks/useFetch'
import { Button, FormField, Modal } from '../ui'
import {
  BlockerList, EquipmentPicker, ErrorNote, REASONS, fieldErr, nn, opts, useAction,
} from './shared'

// equipment: optional { public_id, asset_tag, name } to lock the equipment; initial: { reason_category, source_verification_item }.
export default function CondemnationRequestModal({ equipment, initial = {}, onClose, onDone }) {
  const [v, setV] = useState({
    equipment: equipment?.public_id || '', reason_category: initial.reason_category || 'UNECONOMICAL_TO_REPAIR',
    justification: '', technical_assessment: '', technical_assessment_by_name: '',
  })
  const set = (k) => (e) => setV((s) => ({ ...s, [k]: e.target.value }))
  const act = useAction()
  const check = useFetch(v.equipment ? `/equipment/${v.equipment}/condemnation-check/` : '/equipment/', undefined, !!v.equipment)
  const blockers = v.equipment ? check.data?.blockers || [] : []
  const linked = !!initial.source_verification_item

  const submit = () => act.run(async () => {
    const { data } = await api.post('/condemnation-requests/', {
      equipment: v.equipment, reason_category: v.reason_category, justification: v.justification,
      technical_assessment: nn(v.technical_assessment), technical_assessment_by_name: nn(v.technical_assessment_by_name),
      ...(linked ? { source_verification_item: initial.source_verification_item } : {}),
    })
    onDone(data)
  })

  return (
    <Modal title="Request condemnation" onClose={onClose} wide
      footer={<>
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button variant="primary" loading={act.busy} disabled={!v.equipment || blockers.length > 0} onClick={submit}>Submit request</Button>
      </>}>
      {equipment
        ? <p><strong>{equipment.asset_tag}</strong> · {equipment.name}</p>
        : <EquipmentPicker value={v.equipment} required error={fieldErr(act.error, 'equipment')}
          params={{ lifecycle_stage: 'COMMISSIONED' }} onChange={(id) => setV((s) => ({ ...s, equipment: id }))} />}
      {blockers.length > 0 && (
        <div className="alert alert-warning">
          This equipment cannot be condemned yet. Resolve these first:
          <BlockerList blockers={blockers} />
        </div>
      )}
      {linked && <p className="muted">Linked to a confirmed-missing item of a completed physical verification (write-off).</p>}
      <FormField label="Reason" name="reason_category" as="select" value={v.reason_category} disabled={linked}
        options={opts(REASONS)} error={fieldErr(act.error, 'reason_category')} onChange={set('reason_category')} />
      <FormField label="Justification" name="justification" as="textarea" required value={v.justification}
        error={fieldErr(act.error, 'justification')} onChange={set('justification')} />
      <FormField label="Technical assessment" name="technical_assessment" as="textarea" value={v.technical_assessment}
        onChange={set('technical_assessment')} />
      <FormField label="Assessed by" name="technical_assessment_by_name" value={v.technical_assessment_by_name}
        onChange={set('technical_assessment_by_name')} />
      <ErrorNote error={act.error} />
    </Modal>
  )
}
