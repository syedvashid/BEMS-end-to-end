import { useState } from 'react'
import ReservationModal from '../components/allocation/ReservationModal'
import {
  ApiAlert, Button, FormField, Modal, NoteModal, StatusBadge, api, eqValue, fmtDateTime, today, toInput,
  useAction, useFetch, useLocationOptions, useOptions, withBlank,
} from '../components/allocation/shared'
import { useToast } from '../components/ui'
import { useFacility } from '../context/FacilityContext'
import '../styles/maintenance.css'
import '../styles/allocation.css'

const DAY = 86400000

function Detail({ r, onClose, onDone }) {
  const { can } = useFacility()
  const [cancel, setCancel] = useState(false)
  const { busy, error, run } = useAction()
  const confirmed = r.status === 'CONFIRMED'
  const mark = (path) => run(async () => { await api.post(`/reservations/${r.public_id}/${path}/`, {}); onDone() })
  if (cancel) {
    return <NoteModal title="Cancel reservation" label="Reason" required field="reason" submitLabel="Cancel reservation"
      onClose={() => setCancel(false)} onSubmit={async (reason) => { await api.post(`/reservations/${r.public_id}/cancel/`, { reason }); onDone() }} />
  }
  return (
    <Modal title={`${r.equipment.asset_tag} · ${r.department.name}`} onClose={onClose}
      footer={<>
        <Button variant="secondary" onClick={onClose}>Close</Button>
        {confirmed && can('reservation.manage') && <Button loading={busy} onClick={() => mark('fulfil')}>Mark fulfilled</Button>}
        {confirmed && can('reservation.manage') && <Button loading={busy} onClick={() => mark('no-show')}>Mark no-show</Button>}
        {confirmed && (r.is_mine || can('reservation.manage')) && <Button variant="danger" onClick={() => setCancel(true)}>Cancel booking</Button>}
      </>}>
      <ApiAlert error={error} />
      <p>{fmtDateTime(r.start_at)} – {fmtDateTime(r.end_at)} <StatusBadge tone="info">{r.status}</StatusBadge></p>
      <p><strong>Purpose:</strong> {r.purpose}</p>
      {r.procedure_reference && <p><strong>Procedure:</strong> {r.procedure_reference}</p>}
      <p className="muted">Booked by {r.created_by || '—'}</p>
    </Modal>
  )
}

export default function ReservationsPage() {
  const { can } = useFacility()
  const toast = useToast()
  const [date, setDate] = useState(today())
  const [location, setLocation] = useState('')
  const [category, setCategory] = useState('')
  const [mine, setMine] = useState(false)
  const [book, setBook] = useState(null)
  const [sel, setSel] = useState(null)
  const locs = useLocationOptions()
  const cats = useOptions('/equipment-categories/', (c) => ({ value: c.public_id, label: c.name }))
  const dayStart = new Date(`${date}T00:00:00`)
  const dayEnd = new Date(dayStart.getTime() + DAY)
  const eq = useFetch('/equipment/bedside/', { location, ...(category ? { category } : {}), page_size: 20 }, !!location)
  const rs = useFetch('/reservations/', {
    window_from: dayStart.toISOString(), window_to: dayEnd.toISOString(), page_size: 100, ordering: 'start_at',
    ...(mine ? { mine: true } : {}),
  }, !!location)
  const rows = eq.data?.results || []
  const byEq = {}
  ;(rs.data?.results || []).filter((r) => r.status !== 'CANCELLED').forEach((r) => { (byEq[r.equipment.public_id] ||= []).push(r) })
  const reload = () => { rs.reload(); eq.reload() }

  const onTrack = (e, row) => {
    if (e.target !== e.currentTarget || !can('reservation.add')) return
    const rect = e.currentTarget.getBoundingClientRect()
    const hour = Math.floor(((e.clientX - rect.left) / rect.width) * 24)
    const s = new Date(dayStart.getTime() + hour * 3600000)
    setBook({ equipment: eqValue(row), start: toInput(s), end: toInput(new Date(s.getTime() + 3600000)) })
  }
  return (
    <section>
      <div className="page-head"><h2>Reservations</h2><span className="spacer" />
        {can('reservation.add') && <Button variant="primary" onClick={() => setBook({})}>New reservation</Button>}
      </div>
      <div className="mt-toolbar">
        <FormField label="Day" name="date" type="date" value={date} onChange={(e) => setDate(e.target.value || today())} />
        <FormField label="Location" name="location" as="select" options={withBlank(locs, 'Select a location…')} value={location} onChange={(e) => setLocation(e.target.value)} />
        <FormField label="Category" name="category" as="select" options={withBlank(cats, 'All')} value={category} onChange={(e) => setCategory(e.target.value)} />
        <label className="al-check"><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} /> My bookings only</label>
      </div>
      {!location ? <p className="muted">Pick a location to see its equipment on the timeline (first 20 items).</p> : (
        <div className="al-timeline">
          <div className="al-row al-head">
            <div className="al-label" />
            <div className="al-track al-hours">{Array.from({ length: 24 }, (_, h) => <span key={h}>{h % 2 === 0 ? h : ''}</span>)}</div>
          </div>
          {rows.length === 0 && !eq.loading && <p className="muted">No equipment in this location.</p>}
          {rows.map((row) => (
            <div className="al-row" key={row.public_id}>
              <div className="al-label" title={row.name}>{row.asset_tag}<br /><span className="muted">{row.name}</span></div>
              <div className="al-track" onClick={(e) => onTrack(e, row)}>
                {(byEq[row.public_id] || []).map((r) => {
                  const s = Math.max(new Date(r.start_at), dayStart), e = Math.min(new Date(r.end_at), dayEnd)
                  return (
                    <button key={r.public_id} type="button" className={`al-bar al-${r.status.toLowerCase()}`}
                      style={{ left: `${((s - dayStart) / DAY) * 100}%`, width: `${((e - s) / DAY) * 100}%` }}
                      title={`${r.department.name}: ${r.purpose}`}
                      onClick={(ev) => { ev.stopPropagation(); setSel(r) }}>{r.department.code || r.department.name}</button>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}
      {book && <ReservationModal equipment={book.equipment} start={book.start} end={book.end} onClose={() => setBook(null)}
        onDone={() => { setBook(null); toast.success('Reserved.'); reload() }} />}
      {sel && <Detail r={sel} onClose={() => setSel(null)} onDone={() => { setSel(null); toast.success('Updated.'); reload() }} />}
    </section>
  )
}