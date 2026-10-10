import { useState } from 'react'
import { Button } from '../ui'
import CalibrationHistoryModal from './CalibrationHistoryModal'
import CalibrationScheduleModal from './CalibrationScheduleModal'
import RecordCalibrationModal from './RecordCalibrationModal'
import { CalChip, fmtDate, useFetch, usePermission } from './shared'

export default function CalibrationTab({ equipment }) {
  const canManage = usePermission('calibration.manage')
  const canRecord = usePermission('calibration.record')
  const canReview = usePermission('calibration.review')
  const { data, loading, reload } = useFetch('/calibration-schedules/', { equipment: equipment.public_id })
  const [modal, setModal] = useState(null)
  const s = data?.results?.[0]
  const done = () => { setModal(null); reload() }
  if (loading) return <p>Loading…</p>
  if (!s) {
    return (<div>
      <p>No calibration schedule for this equipment.</p>
      {canManage && equipment.lifecycle_stage === 'COMMISSIONED' && <Button onClick={() => setModal('schedule')}>Add calibration schedule</Button>}
      {modal === 'schedule' && <CalibrationScheduleModal equipmentId={equipment.public_id} onClose={() => setModal(null)} onSaved={done} />}
    </div>)
  }
  return (
    <div>
      <p><CalChip status={s.calibration_status} /> {s.has_unresolved_failure && '· Last result: fail'}</p>
      <p>Every {s.frequency_value} {s.frequency_type.toLowerCase()} · last {fmtDate(s.last_calibrated_date)} · next due {fmtDate(s.next_due_date)}</p>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {canRecord && <Button onClick={() => setModal('record')}>Record calibration</Button>}
        <Button variant="secondary" onClick={() => setModal('history')}>Records and certificates</Button>
        {canManage && <Button variant="ghost" onClick={() => setModal('schedule')}>Edit schedule</Button>}
      </div>
      {modal === 'schedule' && <CalibrationScheduleModal schedule={s} canDelete={canManage} onClose={() => setModal(null)} onSaved={done} />}
      {modal === 'record' && <RecordCalibrationModal schedule={s} onClose={() => setModal(null)} onSaved={done} />}
      {modal === 'history' && <CalibrationHistoryModal schedule={s} canReview={canReview} onClose={done} />}
    </div>
  )
}