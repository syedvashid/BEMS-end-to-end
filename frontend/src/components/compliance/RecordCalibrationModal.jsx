import { useState } from 'react'
import { Button, FormError, FormField, Modal } from '../ui'
import { api, fieldError, nn, today, useForm, useOptions, useSubmit, vendorOption, withBlank } from './shared'
import ReadingsEditor, { emptyReading } from './ReadingsEditor'

const REASONS = [['SCHEDULED', 'Scheduled'], ['POST_REPAIR', 'After repair'], ['AFTER_FAILURE', 'After a failure'], ['OTHER', 'Other']]
const PERFORMERS = [['IN_HOUSE', 'In-house'], ['VENDOR', 'Vendor'], ['ACCREDITED_LAB', 'Accredited lab']]
const opt = (pairs) => pairs.map(([value, label]) => ({ value, label }))

export default function RecordCalibrationModal({ schedule, onClose, onSaved }) {
  const vendors = useOptions('/vendors/', vendorOption)
  const { busy, error, run } = useSubmit()
  const [readings, setReadings] = useState([])
  const { v, bind } = useForm({
    performed_date: today(), calibration_reason: 'SCHEDULED', performed_by_type: 'IN_HOUSE', performer_vendor: '',
    performer_name: '', reference_standard_details: '', certificate_number: '', result: 'PASS',
    deviation_summary: '', next_due_date: '', notes: '',
  })
  const fe = (n) => fieldError(error, n)
  const fail = v.result === 'FAIL'

  const save = () => run(async () => {
    await api.post('/calibration-records/', {
      equipment: schedule.equipment, performed_date: v.performed_date, calibration_reason: v.calibration_reason,
      performed_by_type: v.performed_by_type, performer_vendor: nn(v.performer_vendor), performer_name: nn(v.performer_name),
      reference_standard_details: nn(v.reference_standard_details), certificate_number: nn(v.certificate_number),
      result: v.result, readings: readings.filter((r) => r.parameter.trim()), deviation_summary: nn(v.deviation_summary),
      next_due_date: nn(v.next_due_date), notes: nn(v.notes),
    })
    onSaved()
  })

  return (
    <Modal wide title={`Record calibration — ${schedule.equipment_asset_tag}`} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={save} loading={busy}>Save record</Button></>}>
      <FormError error={error} />
      <FormField label="Performed on" type="date" max={today()} required error={fe('performed_date')} {...bind('performed_date')} />
      <FormField label="Reason" as="select" options={opt(REASONS)} {...bind('calibration_reason')} />
      <FormField label="Performed by" as="select" options={opt(PERFORMERS)} {...bind('performed_by_type')} />
      {v.performed_by_type !== 'IN_HOUSE' && (
        <FormField label="Vendor / lab" as="select" options={withBlank(vendors, 'Not listed')} error={fe('performer_vendor')} {...bind('performer_vendor')} />
      )}
      <FormField label="Person / lab name" error={fe('performer_name')} hint="Required when no vendor is selected" {...bind('performer_name')} />
      <FormField label="Reference standard (instrument and traceability)" as="textarea" error={fe('reference_standard_details')} {...bind('reference_standard_details')} />
      <FormField label="Certificate number" error={fe('certificate_number')} {...bind('certificate_number')} />
      <FormField label="Result" as="select" required options={[{ value: 'PASS', label: 'Pass' }, { value: 'FAIL', label: 'Fail' }]} {...bind('result')} />
      {fail && (
        <p role="alert">
          A failed calibration {schedule.on_fail_hold_equipment ? 'puts the equipment out of service until a later passing record' : 'does not hold the equipment'}
          {schedule.on_fail_open_work_order ? ' and opens a corrective work order.' : '.'}
        </p>
      )}
      <h4>Readings</h4>
      {fe('readings') && <p role="alert">{fe('readings')}</p>}
      <ReadingsEditor rows={readings} onChange={setReadings} />
      <FormField label="Deviation summary" as="textarea" error={fe('deviation_summary')} {...bind('deviation_summary')} />
      <FormField label="Next due (optional)" type="date" hint="Default: performed date + schedule interval" error={fe('next_due_date')} {...bind('next_due_date')} />
      <FormField label="Notes" as="textarea" error={fe('notes')} {...bind('notes')} />
    </Modal>
  )
}