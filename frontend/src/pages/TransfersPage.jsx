import { useState } from 'react'
import SimplePager from '../components/SimplePager'
import {
  ApiAlert, Button, EqLink, EquipmentField, FormField, Modal, NoteModal, StatusBadge, Table, api, clean, fe, fmtDateTime,
  nn, toOpts, useAction, useDepartmentOptions, useFetch, useForm, useLocationOptions, withBlank,
} from '../components/allocation/shared'
import { useToast } from '../components/ui'
import { useFacility } from '../context/FacilityContext'
import '../styles/maintenance.css'
import '../styles/allocation.css'

const TONE = { PENDING: 'warning', APPROVED: 'success', REJECTED: 'danger', CANCELLED: 'neutral' }

function RequestModal({ onClose, onDone }) {
  const { can } = useFacility()
  const [eq, setEq] = useState(null)
  const { v, bind } = useForm({ location: '', department: '', reason: '' })
  const locs = useLocationOptions()
  const depts = useDepartmentOptions(can('transfer.approve') ? '/departments/' : '/my-departments/')
  const { busy, error, run } = useAction()
  const submit = () => run(async () => {
    await api.post('/transfer-requests/', { equipment: eq?.public_id ?? null, location: nn(v.location), department: nn(v.department), reason: v.reason })
    onDone()
  })
  return (
    <Modal title="Request transfer" onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Close</Button>
        <Button variant="primary" loading={busy} onClick={submit}>Request</Button></>}>
      <ApiAlert error={error} />
      <EquipmentField value={eq} onChange={setEq} error={fe(error, 'equipment')} />
      <FormField label="Destination location" as="select" required options={withBlank(locs)} {...bind('location')} error={fe(error, 'location')} />
      <FormField label="Destination department" as="select" required={!can('transfer.approve')}
        hint={can('transfer.approve') ? 'Leave empty to keep the owning department' : undefined}
        options={withBlank(depts, can('transfer.approve') ? '— unchanged —' : 'Select…')} {...bind('department')} error={fe(error, 'department')} />
      <FormField label="Reason" as="textarea" required {...bind('reason')} error={fe(error, 'reason')} />
    </Modal>
  )
}

export default function TransfersPage() {
  const { can } = useFacility()
  const toast = useToast()
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('')
  const [mine, setMine] = useState(false)
  const [modal, setModal] = useState(null)   // 'new' | {kind, t}
  const res = useFetch('/transfer-requests/', clean({ status, mine: mine || '', page, page_size: 20 }))
  const done = (msg) => () => { setModal(null); toast.success(msg); res.reload() }
  const act = (t, path, body = {}) => api.post(`/transfer-requests/${t.public_id}/${path}/`, body)
  return (
    <section>
      <div className="page-head"><h2>Transfers</h2><span className="spacer" />
        {can('transfer.request') && <Button variant="primary" onClick={() => setModal('new')}>Request transfer</Button>}
      </div>
      <div className="mt-toolbar">
        <FormField label="Status" name="status" as="select" options={withBlank(toOpts(['PENDING', 'APPROVED', 'REJECTED', 'CANCELLED']), 'All')} value={status} onChange={(e) => { setPage(1); setStatus(e.target.value) }} />
        <label className="al-check"><input type="checkbox" checked={mine} onChange={(e) => { setPage(1); setMine(e.target.checked) }} /> My requests only</label>
      </div>
      <Table rows={res.data?.results} loading={res.loading} empty="No transfer requests." columns={[
        { key: 'eq', header: 'Equipment', render: (t) => <EqLink e={t.equipment} /> },
        { key: 'from', header: 'From', render: (t) => [t.from_department?.name, t.from_location?.name].filter(Boolean).join(' / ') || '—' },
        { key: 'to', header: 'To', render: (t) => [t.to_department?.name, t.to_location.name].filter(Boolean).join(' / ') },
        { key: 'r', header: 'Reason', render: (t) => t.reason },
        { key: 'st', header: 'Status', render: (t) => <StatusBadge tone={TONE[t.status]}>{t.status}</StatusBadge> },
        { key: 'by', header: 'Requested', render: (t) => `${t.created_by || '—'} · ${fmtDateTime(t.created_at)}` },
        { key: 'dn', header: 'Decision', render: (t) => (t.decided_at ? `${t.decided_by || '—'}${t.decision_note ? `: ${t.decision_note}` : ''}` : '—') },
        { key: 'act', header: '', render: (t) => (t.status !== 'PENDING' ? null : (
          <div className="mt-actions">
            {can('transfer.approve') && !t.is_mine && <Button size="sm" variant="primary" onClick={() => setModal({ kind: 'approve', t })}>Approve</Button>}
            {can('transfer.approve') && !t.is_mine && <Button size="sm" variant="danger" onClick={() => setModal({ kind: 'reject', t })}>Reject</Button>}
            {t.is_mine && <Button size="sm" onClick={() => setModal({ kind: 'cancel', t })}>Cancel</Button>}
          </div>)) },
      ]} />
      <SimplePager page={page} count={res.data?.count} pageSize={20} onPage={setPage} />
      {modal === 'new' && <RequestModal onClose={() => setModal(null)} onDone={done('Transfer requested.')} />}
      {modal?.kind === 'approve' && <NoteModal title="Approve transfer" label="Note (optional)" submitLabel="Approve" onClose={() => setModal(null)}
        onSubmit={async (note) => { await act(modal.t, 'approve', { note }); done('Transfer approved; equipment moved.')() }} />}
      {modal?.kind === 'reject' && <NoteModal title="Reject transfer" label="Reason for rejection" required submitLabel="Reject" onClose={() => setModal(null)}
        onSubmit={async (note) => { await act(modal.t, 'reject', { note }); done('Transfer rejected.')() }} />}
      {modal?.kind === 'cancel' && <NoteModal title="Cancel request" label="Optional note (not stored)" submitLabel="Cancel request" onClose={() => setModal(null)}
        onSubmit={async () => { await act(modal.t, 'cancel'); done('Request cancelled.')() }} />}
    </section>
  )
}