import { useEffect, useState } from 'react'
import { Button, StatusBadge, Table } from '../ui'
import {
  api, apiError, downloadFromUrl, FetchError, fmtStamp, useFetch,
} from './shared.jsx'

export const RUN_TONE = { COMPLETED: 'success', FAILED: 'danger', QUEUED: 'info', RUNNING: 'warning', EXPIRED: 'neutral' }

// Opens the signed one-time link. Returns an error object or null.
export async function downloadRun(runId) {
  try {
    const res = await api.post(`/report-runs/${runId}/download-link/`)
    downloadFromUrl(res.data.url)
    return null
  } catch (e) {
    const err = apiError(e)
    return err.status === 404 ? { ...err, message: 'This file is not available for download (it may have expired).' } : err
  }
}

export default function MyExports({ refreshKey = 0 }) {
  const res = useFetch('/report-runs/', { page_size: 15 })
  const [error, setError] = useState(null)
  const [busyId, setBusyId] = useState(null)
  useEffect(() => { if (refreshKey) res.reload() }, [refreshKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const download = async (r) => {
    setBusyId(r.public_id); setError(null)
    setError(await downloadRun(r.public_id)); setBusyId(null)
  }
  const columns = [
    { key: 'report_name', header: 'Report' },
    { key: 'format', header: 'Format' },
    { key: 'status', header: 'Status', render: (r) => <StatusBadge tone={RUN_TONE[r.status] || 'neutral'}>{r.status}</StatusBadge> },
    { key: 'row_count', header: 'Rows', render: (r) => r.row_count ?? '—' },
    { key: 'requested_at', header: 'Requested', render: (r) => fmtStamp(r.requested_at) },
    { key: 'expires_at', header: 'Expires', render: (r) => fmtStamp(r.expires_at) },
    { key: 'requested_by', header: 'By', render: (r) => r.requested_by || '—' },
    {
      key: 'actions', header: '', render: (r) => (r.status === 'COMPLETED'
        ? <Button size="sm" loading={busyId === r.public_id} onClick={() => download(r)}>Download</Button>
        : r.status === 'FAILED' ? <span className="rp-note">{r.error_message}</span> : null),
    },
  ]
  return (
    <section className="rp-card" style={{ marginTop: 16 }}>
      <h3>My exports <Button size="sm" variant="ghost" onClick={res.reload}>Refresh</Button></h3>
      <FetchError error={res.error || error} />
      <Table columns={columns} rows={res.data?.results} rowKey="public_id" loading={res.loading} empty="No exports yet." />
    </section>
  )
}
