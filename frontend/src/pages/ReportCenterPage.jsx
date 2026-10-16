import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Button, Pagination, StatusBadge, Table } from '../components/ui'
import MyExports, { downloadRun, RUN_TONE } from '../components/reports/MyExports.jsx'
import ReportParams from '../components/reports/ReportParams.jsx'
import {
  api, apiError, clean, ErrorNote, FetchError, fmtNum, useFetch, usePermission,
} from '../components/reports/shared.jsx'
import { PAGE_SIZE } from '../utils/format'

const cellText = (v, type) => {
  if (v === null || v === undefined || v === '') return '—'
  if (typeof v === 'boolean') return v ? 'Yes' : 'No'
  if (typeof v === 'number') return fmtNum(v, 2)
  return String(v)
}

function ReportRunner({ code, initial, onRunsChanged }) {
  const def = useFetch(`/reports/${code}/`)
  const canExport = usePermission('report.export')
  const [values, setValues] = useState(null)
  const [applied, setApplied] = useState(null)
  const [page, setPage] = useState(1)
  const [run, setRun] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [busy, setBusy] = useState(false)
  const timer = useRef(null)

  useEffect(() => {
    if (def.data && values === null) {
      const v = {}
      def.data.parameters.forEach((p) => { v[p.name] = initial[p.name] ?? (p.default ?? '') })
      setValues(v)
    }
  }, [def.data]) // eslint-disable-line react-hooks/exhaustive-deps

  const data = useFetch(`/reports/${code}/data/`, applied ? { ...clean(applied), page, page_size: PAGE_SIZE } : {}, applied !== null)

  // Poll the run every 3 seconds while it is QUEUED or RUNNING.
  useEffect(() => {
    if (!run || !['QUEUED', 'RUNNING'].includes(run.status)) return undefined
    timer.current = setTimeout(async () => {
      try {
        const res = await api.get(`/report-runs/${run.public_id}/`)
        setRun(res.data)
        if (!['QUEUED', 'RUNNING'].includes(res.data.status)) onRunsChanged()
      } catch (e) { setActionError(apiError(e)) }
    }, 3000)
    return () => clearTimeout(timer.current)
  }, [run]) // eslint-disable-line react-hooks/exhaustive-deps

  const change = (name, v) => setValues((s) => ({ ...s, [name]: v }))
  const doRun = () => { setPage(1); setApplied({ ...values }) }
  const doExport = async (format) => {
    setBusy(true); setActionError(null)
    try {
      const res = await api.post(`/reports/${code}/export/`, { format, parameters: clean(values) })
      setRun(res.data); onRunsChanged()
    } catch (e) { setActionError(apiError(e)) } finally { setBusy(false) }
  }
  const doDownload = async () => { setActionError(await downloadRun(run.public_id)) }

  if (def.error) return <FetchError error={def.error} />
  if (!def.data || values === null) return <p className="rp-note">Loading…</p>
  const d = def.data
  const columns = (data.data?.columns || []).map((c) => ({ key: c.key, header: c.label, render: (r) => cellText(r[c.key], c.type) }))
  const summary = data.data?.summary

  return (
    <div>
      <h2>{d.name}</h2>
      <p className="rp-note">{d.description}</p>
      <ReportParams spec={d.parameters} values={values} onChange={change} errors={data.error?.details || actionError?.details || {}} />
      <div className="rp-actions">
        <Button variant="primary" onClick={doRun} loading={data.loading && applied !== null}>Run</Button>
        {canExport && d.formats.map((f) => (
          <Button key={f} loading={busy} onClick={() => doExport(f)}>{f === 'XLSX' ? 'Excel' : f}</Button>
        ))}
      </div>
      {run && (
        <div className="alert alert-info">
          Export {run.format}: <StatusBadge tone={RUN_TONE[run.status] || 'neutral'}>{run.status}</StatusBadge>
          {run.row_count != null && <> · {run.row_count} rows</>}
          {['QUEUED', 'RUNNING'].includes(run.status) && <> · working in the background, checking every 3 seconds…</>}
          {run.status === 'FAILED' && <> · {run.error_message}</>}
          {run.status === 'COMPLETED' && <> · <Button size="sm" variant="primary" onClick={doDownload}>Download</Button></>}
        </div>
      )}
      <ErrorNote error={actionError} />
      <FetchError error={data.error} />
      {summary && (
        <div className="rp-summary">
          {Object.entries(summary).map(([k, v]) => <span key={k}><strong>{String(k).replace(/_/g, ' ')}:</strong> {cellText(v)}</span>)}
        </div>
      )}
      {applied !== null && !data.error && (
        <>
          <div className="rp-scroll">
            <Table columns={columns} rows={(data.data?.results || []).map((r, i) => ({ ...r, __k: `${page}-${i}` }))} rowKey="__k" loading={data.loading} empty="No rows for these filters." />
          </div>
          <Pagination page={page} pageSize={PAGE_SIZE} count={data.data?.count ?? 0} onPageChange={setPage} />
        </>
      )}
    </div>
  )
}

export default function ReportCenterPage() {
  const [search] = useSearchParams()
  const list = useFetch('/reports/')
  const [code, setCode] = useState(search.get('report') || '')
  const [refreshKey, setRefreshKey] = useState(0)
  const canExport = usePermission('report.export')
  const initial = Object.fromEntries([...search.entries()].filter(([k]) => k !== 'report'))
  const groups = list.data?.groups || []

  return (
    <>
      <div className="page-head"><h1>Report Center</h1></div>
      <FetchError error={list.error} />
      <div className="rp-layout">
        <nav className="rp-list" aria-label="Reports">
          {groups.map((g) => (
            <div key={g.category}>
              <h4>{g.category}</h4>
              {g.reports.map((r) => (
                <button key={r.code} type="button" className={r.code === code ? 'active' : ''} onClick={() => setCode(r.code)}>{r.name}</button>
              ))}
            </div>
          ))}
          {!groups.length && !list.loading && <p className="rp-note">No reports are available for your role.</p>}
        </nav>
        <div>
          {code ? <ReportRunner key={code} code={code} initial={code === search.get('report') ? initial : {}} onRunsChanged={() => setRefreshKey((k) => k + 1)} />
            : <p className="rp-note">Choose a report on the left.</p>}
          {canExport && <MyExports refreshKey={refreshKey} />}
        </div>
      </div>
    </>
  )
}
