import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ActionModal, Chip, FilterSelect, LocationSelect, RESULTS, api, clean, fmt, fmtDate, fmtDateTime, lbl, nn, opt,
  norm, parseApiError, useFetch,
} from '../components/safety/shared'
import VerificationFormModal from '../components/safety/VerificationFormModal'
import SimplePager from '../components/SimplePager'
import { Button, Table, useToast } from '../components/ui'
import { useFacility } from '../context/FacilityContext'
import WriteOffAction from '../components/finance/WriteOffAction'
const TABS = [
  { key: 'PENDING', label: 'Pending' }, { key: 'FOUND', label: 'Found' },
  { key: 'FOUND_ELSEWHERE', label: 'Elsewhere' }, { key: 'UNEXPECTED', label: 'Unexpected' },
]
const COUNTER_LABELS = [['expected', 'Expected'], ['found', 'Found'], ['elsewhere', 'Elsewhere'], ['unexpected', 'Unexpected'], ['pending', 'Pending']]

export default function VerificationRunPage() {
  const { publicId } = useParams()
  const { can } = useFacility()
  const toast = useToast()
  const res = useFetch(`/verifications/${publicId}/`)
  const [dialog, setDialog] = useState(null)
  const [target, setTarget] = useState(null)
  // scanning
  const [code, setCode] = useState('')
  const [loc, setLoc] = useState('')
  const [scanBusy, setScanBusy] = useState(false)
  const [scanMsg, setScanMsg] = useState(null)
  const [recent, setRecent] = useState([])
  const [counters, setCounters] = useState(null)
  const inputRef = useRef(null)
  // item lists
  const [tab, setTab] = useState('PENDING')
  const [resultFilter, setResultFilter] = useState('')
  const [page, setPage] = useState(1)
  const v = res.data
  const status = v?.status
  const listParams = status === 'IN_PROGRESS' ? { result: tab } : clean({ result: resultFilter })
  const items = useFetch(`/verifications/${publicId}/items/`, { ...listParams, page, page_size: 20 }, status === 'IN_PROGRESS' || status === 'COMPLETED')

  useEffect(() => { if (v) setCounters(v.counters) }, [v?.row_version, v?.public_id]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (status === 'IN_PROGRESS') inputRef.current?.focus() }, [status])

  if (res.loading && !res.data) return <p className="muted">Loading…</p>
  if (res.error || !v) return <div className="alert alert-danger">Verification not found. <Link to="/verifications">Back</Link></div>
  const base = `/verifications/${v.public_id}`
  const close = () => { setDialog(null); setTarget(null) }
  const refresh = () => { res.reload(); items.reload() }
  const done = (msg) => () => { close(); toast.success(msg); refresh() }
  const locScope = v.scope_type === 'LOCATION'
  const c = counters || v.counters

  const scan = async () => {
    const value = code.trim()
    if (!value || scanBusy) return
    if (!locScope && !loc) { setScanMsg({ tone: 'warning', text: 'Choose the location where you are scanning first.' }); return }
    setScanBusy(true); setScanMsg(null)
    try {
      const r = await api.post(`${base}/scan/`, clean({ code: value, found_location: locScope ? undefined : loc }))
      const { item, equipment, counters: next } = r.data
      setCounters(next)
      setRecent((list) => [{ at: new Date().toISOString(), code: value, tag: equipment.asset_tag, name: equipment.name, result: item.result }, ...list].slice(0, 10))
      setScanMsg({ tone: item.result === 'FOUND' ? 'success' : 'warning', text: `${equipment.asset_tag} · ${equipment.name}: ${lbl(item.result)}` })
      setCode(''); items.reload()
    } catch (e) {
      const err = norm(parseApiError(e))
      setScanMsg({ tone: 'danger', text: err.code === 'not_found' ? `Unknown code “${value}”.` : (err.message || 'Scan failed.') })
    } finally { setScanBusy(false); inputRef.current?.focus() }
  }

  const itemColumns = [
    { key: 'asset', header: 'Asset', render: (i) => <Link to={`/equipment/${i.equipment.public_id}`}>{i.equipment.asset_tag} · {i.equipment.name}</Link> },
    { key: 'serial', header: 'Serial', render: (i) => fmt(i.equipment.serial_number) },
    { key: 'exp', header: 'Expected at', render: (i) => fmt(i.expected_location?.name) },
    { key: 'found', header: 'Found at', render: (i) => fmt(i.found_location?.name) },
    { key: 'result', header: 'Result', render: (i) => <Chip kind="result" value={i.result} /> },
    { key: 'tag', header: 'Tag', render: (i) => (i.tag_status === 'OK' ? 'OK' : lbl(i.tag_status)) },
    { key: 'resolution', header: 'Resolution', render: (i) => (i.resolution === 'NONE' ? '' : lbl(i.resolution)) },
    {
      key: 'act', header: '', render: (i) => (
        <div className="row">
          {status === 'IN_PROGRESS' && can('verification.add') && <Button size="sm" onClick={() => { setTarget(i); setDialog('item') }}>Tag / notes</Button>}
          {status === 'COMPLETED' && can('verification.manage') && i.resolution === 'NONE' && ['FOUND_ELSEWHERE', 'MISSING', 'UNEXPECTED'].includes(i.result) && (
          <Button size="sm" onClick={() => { setTarget(i); setDialog('resolve') }}>Resolve</Button>)}
          {status === 'COMPLETED' && <WriteOffAction item={i} />}

        </div>
      ),
    },
  ]

  return (
    <section>
      <div className="page-head">
        <h2>{v.verification_number} · {v.title}</h2> <Chip kind="verification" value={v.status} />
        <span className="spacer" />
        <div className="mt-actions">
          {status === 'PLANNED' && can('verification.add') && <Button onClick={() => setDialog('edit')}>Edit</Button>}
          {status === 'PLANNED' && can('verification.add') && <Button variant="primary" onClick={() => setDialog('start')}>Start</Button>}
          {status === 'IN_PROGRESS' && can('verification.manage') && <Button variant="primary" onClick={() => setDialog('complete')}>Complete</Button>}
          {['PLANNED', 'IN_PROGRESS'].includes(status) && can('verification.manage') && <Button variant="danger" onClick={() => setDialog('cancel')}>Cancel</Button>}
          <Link to="/verifications">Back to list</Link>
        </div>
      </div>

      <div className="mt-grid">
        <div className="eq-kv"><span className="muted">Scope</span><span>{lbl(v.scope_type)}{v.department ? `: ${v.department.name}` : ''}{v.location ? `: ${v.location.name}` : ''}</span></div>
        <div className="eq-kv"><span className="muted">Planned</span><span>{fmtDate(v.planned_date)}</span></div>
        <div className="eq-kv"><span className="muted">Conducted by</span><span>{fmt(v.conducted_by_name)}</span></div>
        <div className="eq-kv"><span className="muted">Started / completed</span><span>{v.started_at ? fmtDateTime(v.started_at) : '—'} / {v.completed_at ? fmtDateTime(v.completed_at) : '—'}</span></div>
        {v.cancel_reason && <div className="eq-kv"><span className="muted">Cancel reason</span><span>{v.cancel_reason}</span></div>}
      </div>
      {v.notes && <p>{v.notes}</p>}

      {status === 'PLANNED' && <p className="muted">Press Start to list every active equipment in scope as expected. Disposed and rejected equipment is left out.</p>}

      {(status === 'IN_PROGRESS' || status === 'COMPLETED') && (
        <div className="row">
          {COUNTER_LABELS.map(([k, label]) => <div key={k} className="eq-kv"><span className="muted">{label}</span><strong>{c?.[k] ?? 0}</strong></div>)}
          {status === 'COMPLETED' && <div className="eq-kv"><span className="muted">Missing</span><strong>{c?.missing ?? 0}</strong></div>}
        </div>
      )}

      {status === 'IN_PROGRESS' && can('verification.add') && (
        <div className="mt-section">
          <h3>Scan</h3>
          {!locScope && <LocationSelect label="Found at (location)" value={loc} onChange={setLoc} hint="Stays selected between scans." />}
          <input
            ref={inputRef} autoFocus value={code} onChange={(e) => setCode(e.target.value)} disabled={scanBusy}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); scan() } }}
            placeholder="Scan or type a QR value, asset tag or legacy ID, then press Enter"
            aria-label="Scan code" autoComplete="off" spellCheck="false"
            style={{ width: '100%', fontSize: '1.5rem', padding: '0.75rem' }} />
          {scanMsg && <div className={`alert alert-${scanMsg.tone}`} role="status">{scanMsg.text}</div>}
          {recent.length > 0 && (
            <Table rows={recent} rowKey="at" columns={[
              { key: 'at', header: 'Time', render: (r) => fmtDateTime(r.at) },
              { key: 'tag', header: 'Asset', render: (r) => `${r.tag} · ${r.name}` },
              { key: 'result', header: 'Result', render: (r) => <Chip kind="result" value={r.result} /> },
            ]} />
          )}
        </div>
      )}

      {status === 'IN_PROGRESS' && (
        <div className="mt-section">
          <div className="eq-tabs">
            {TABS.map((t) => (
              <button key={t.key} type="button" className={`eq-tab${tab === t.key ? ' active' : ''}`} onClick={() => { setTab(t.key); setPage(1) }}>{t.label}</button>
            ))}
          </div>
          <Table rows={items.data?.results} loading={items.loading} empty="Nothing here." columns={itemColumns} />
          <SimplePager page={page} count={items.data?.count} pageSize={20} onPage={setPage} />
        </div>
      )}

      {status === 'COMPLETED' && (
        <div className="mt-section">
          <h3>Results</h3>
          <div className="row">
            <FilterSelect label="Result" value={resultFilter} onChange={(x) => { setResultFilter(x); setPage(1) }} options={opt(RESULTS.filter((r) => r !== 'PENDING'))} />
          </div>
          <Table rows={items.data?.results} loading={items.loading} empty="No items." columns={itemColumns} />
          <SimplePager page={page} count={items.data?.count} pageSize={20} onPage={setPage} />
        </div>
      )}

      {dialog === 'edit' && <VerificationFormModal verification={v} onClose={close} onDone={() => { close(); toast.success('Saved.'); refresh() }} />}
      {dialog === 'start' && (
        <ActionModal title="Start verification" submitLabel="Start" onClose={close} onDone={done('Verification started.')}
          intro="The expected list is built now from the equipment in scope and is not updated afterwards."
          onSubmit={() => api.post(`${base}/start/`, {})} />
      )}
      {dialog === 'complete' && (
        <ActionModal title="Complete verification" submitLabel="Complete" onClose={close} onDone={done('Verification completed.')}
          intro={`${c?.pending ?? 0} item(s) are still pending and will be recorded as Missing. This cannot be undone.`}
          onSubmit={() => api.post(`${base}/complete/`, {})} />
      )}
      {dialog === 'cancel' && (
        <ActionModal title="Cancel verification" submitLabel="Cancel verification" danger onClose={close} onDone={done('Verification cancelled.')}
          fields={[{ name: 'reason', label: 'Reason', as: 'textarea', required: true }]}
          onSubmit={(f) => api.post(`${base}/cancel/`, { reason: f.reason.trim(), row_version: v.row_version })} />
      )}
      {dialog === 'item' && target && (
        <ActionModal title={`Tag and notes: ${target.equipment.asset_tag}`} onClose={close} onDone={done('Saved.')}
          fields={[
            { name: 'tag_status', label: 'Tag condition', as: 'select', initial: target.tag_status, options: opt(['OK', 'DAMAGED', 'UNREADABLE']) },
            { name: 'notes', label: 'Notes', as: 'textarea', initial: target.notes || '' },
          ]}
          onSubmit={(f) => api.patch(`${base}/items/${target.public_id}/`, { tag_status: f.tag_status, notes: nn(f.notes.trim()), row_version: target.row_version })} />
      )}
      {dialog === 'resolve' && target && (
        <ActionModal title={`Resolve ${target.equipment.asset_tag} (${lbl(target.result)})`} submitLabel="Resolve" onClose={close} onDone={done('Item resolved.')}
          intro={target.found_location ? `Update location moves the equipment to ${target.found_location.name}. It is refused while the equipment is allocated.` : 'No found location was recorded, so the location cannot be updated.'}
          fields={[
            {
              name: 'resolution', label: 'Decision', as: 'select', required: true,
              initial: target.found_location ? 'LOCATION_UPDATED' : 'CONFIRMED_MISSING',
              options: [
                ...(target.found_location ? [{ value: 'LOCATION_UPDATED', label: 'Update location' }] : []),
                { value: 'CONFIRMED_MISSING', label: 'Confirm missing' }, { value: 'FOUND_LATER', label: 'Found later' }, { value: 'IGNORED', label: 'Ignore' }],
            },
            { name: 'notes', label: 'Notes', as: 'textarea' },
          ]}
          onSubmit={(f) => api.post(`${base}/items/${target.public_id}/resolve/`, { resolution: f.resolution, notes: nn(f.notes.trim()) })} />
      )}
    </section>
  )
}
