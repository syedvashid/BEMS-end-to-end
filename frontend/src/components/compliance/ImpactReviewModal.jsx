import { Button, FormError, FormField, Modal } from '../ui'
import { api, fieldError, useForm, useSubmit } from './shared'

export default function ImpactReviewModal({ record, onClose, onSaved }) {
  const { busy, error, run } = useSubmit()
  const { v, bind } = useForm({ review_notes: '', patient_impact_found: false })
  const save = () => run(async () => {
    await api.post(`/calibration-records/${record.public_id}/review-impact/`,
      { review_notes: v.review_notes, patient_impact_found: !!v.patient_impact_found })
    onSaved()
  })
  return (
    <Modal title="Calibration failure — impact review" onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={save} loading={busy}>Save review</Button></>}>
      <FormError error={error} />
      <p>Review patients and procedures that used this equipment since its last passing calibration. A review can be saved only once.</p>
      <FormField label="Review notes" as="textarea" required error={fieldError(error, 'review_notes')} {...bind('review_notes')} />
      <label><input type="checkbox" checked={!!v.patient_impact_found} onChange={bind('patient_impact_found').onChange} name="patient_impact_found" /> Patient impact found</label>
    </Modal>
  )
}