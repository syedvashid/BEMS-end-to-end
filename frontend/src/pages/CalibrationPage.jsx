import { useState } from 'react'
import { Button, FormField, Pagination, StatusBadge, Table } from '../components/ui'
import CalibrationHistoryModal from '../components/compliance/CalibrationHistoryModal'
import CalibrationScheduleModal from '../components/compliance/CalibrationScheduleModal'
import GenerateSchedulesModal from '../components/compliance/GenerateSchedulesModal'
import RecordCalibrationModal from '../components/compliance/RecordCalibrationModal'
import { CalChip, clean, fmtDate, useFetch, usePermission } from '../components/compliance/shared'

const STATUS = [{ value: '', label: 'All statuses' }, { value: 'OK', label: 'OK' }, { value: 'DUE_SOON', label: 'Due soon' }, { value: 'OVERDUE', label: 'Overdue' }]

export default function CalibrationPage() {
  const canManage = usePermission('calibration.manage')
  const canRecord = usePermission('calibration.record')
  const canReview = usePermission('calibration.review')
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [modal, setModal] = useState(null)   // {type: 'schedule'|'record'|'history'|'generate', row?}
  const { data, loading, error, reload } = useFetch('/calibration-schedules/', clean({ page, page_size: 20, status, search }))
  const done = () => { setModal(null); reload() }

  const columns = [
    { key: 'equipment_asset_tag', header: 'Equipment', render: (r) => <><strong>{r.equipment_asset_tag}</strong><br />{r.equipment_name}</> },
    { key: 'frequency_value', header: 'Interval', render: (r) => `Every ${r.frequency_value} ${r.frequency_type.toLowerCase()}` },
    { key: 'last_calibrated_date', header: 'Last calibrated', render: (r) => fmtDate(r.last_calibrated_date) },
    { key: 'next_due_date', header: 'Next due', render: (r) => fmtDate(r.next_due_date) },
    {
      key: 'calibration_status', header: 'Status',
      render: (r) => <><CalChip status={r.calibration_status} />{r.has_unresolved_failure && <> <StatusBadge tone="danger">Last result: fail</StatusBadge></>}</>,
    },
    {
      key: 'actions', header: '',
      render: (r) => (
        <span style={{ display: 'flex', gap: 6 }}>
          {canRecord && <Button size="sm" onClick={() => setModal({ type: 'record', row: r })}>Record</Button>}
          <Button size="sm" variant="secondary" onClick={() => setModal({ type: 'history', row: r })}>History</Button>
          {canManage && <Button size="sm" variant="ghost" onClick={() => setModal({ type: 'schedule', row: r })}>Edit</Button>}
        </span>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <h1>Calibration</h1>
        {canManage && (
          <span style={{ display: 'flex', gap: 8 }}>
            <Button variant="secondary" onClick={() => setModal({ type: 'generate' })}>Generate schedules</Button>
            <Button onClick={() => setModal({ type: 'schedule' })}>New schedule</Button>
          </span>
        )}
      </div>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <FormField label="Status" name="status" as="select" options={STATUS} value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }} />
        <FormField label="Search" name="search" placeholder="Asset tag or name" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }} />
      </div>
      {error && <p role="alert">Could not load calibration schedules.</p>}
      <Table columns={columns} rows={data?.results || []} loading={loading} empty="No calibration schedules." />
      <Pagination page={page} pageSize={20} count={data?.count || 0} onChange={setPage} />

      {modal?.type === 'schedule' && <CalibrationScheduleModal schedule={modal.row} canDelete={canManage} onClose={() => setModal(null)} onSaved={done} />}
      {modal?.type === 'generate' && <GenerateSchedulesModal onClose={() => setModal(null)} onDone={done} />}
      {modal?.type === 'record' && <RecordCalibrationModal schedule={modal.row} onClose={() => setModal(null)} onSaved={done} />}
      {modal?.type === 'history' && <CalibrationHistoryModal schedule={modal.row} canReview={canReview} onClose={done} />}
    </div>
  )
}