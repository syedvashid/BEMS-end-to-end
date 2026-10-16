import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, FormField, Pagination, Table } from '../ui'
import { PAGE_SIZE } from '../../utils/format'
import {
  daysAgo, fmtDay, fmtNum, FetchError, useFetch, useMasterOptions, usePermission,
} from './shared.jsx'

const pct = (v) => (v === null || v === undefined ? '—' : `${fmtNum(v, 2)}%`)
const hrs = (v) => fmtNum(v, 2)

const DOWNTIME = {
  path: '/downtime/', report: 'DOWNTIME', title: 'Downtime', order: '-unplanned_downtime_hours',
  columns: [
    ['in_service_hours', 'In service (h)', hrs], ['planned_downtime_hours', 'Planned (h)', hrs],
    ['unplanned_downtime_hours', 'Unplanned (h)', hrs], ['availability_percent', 'Availability', pct],
    ['uptime_percent', 'Uptime', pct], ['failures', 'Failures', (v) => v], ['mtbf_hours', 'MTBF (h)', hrs], ['mttr_hours', 'MTTR (h)', hrs],
  ],
}
const UTILIZATION = {
  path: '/utilization/', report: 'UTILIZATION', title: 'Utilization', order: 'utilization_percent',
  columns: [
    ['available_hours', 'Available (h)', hrs], ['used_hours', 'Used (h)', hrs], ['utilization_percent', 'Utilization', pct],
    ['allocated_hours', 'Allocated (h)', hrs], ['occupancy_percent', 'Occupancy', pct], ['sessions', 'Sessions', (v) => v],
  ],
}
export const KIND = { downtime: DOWNTIME, utilization: UTILIZATION }

export default function KpiTable({ kind }) {
  const cfg = KIND[kind]
  const canReport = usePermission('report.view')
  const [page, setPage] = useState(1)
  const [draft, setDraft] = useState({ from: daysAgo(30), to: daysAgo(1), category: '', department: '', location: '' })
  const [applied, setApplied] = useState(draft)
  const [orderKey, setOrderKey] = useState(cfg.order.replace('-', ''))
  const [desc, setDesc] = useState(cfg.order.startsWith('-'))
  const categories = useMasterOptions('/equipment-categories/')
  const departments = useMasterOptions('/departments/')
  const locations = useMasterOptions('/locations/')
  const set = (k) => (e) => setDraft((d) => ({ ...d, [k]: e.target.value }))
  const res = useFetch(cfg.path, { ...applied, ordering: `${desc ? '-' : ''}${orderKey}`, page, page_size: PAGE_SIZE })

  const columns = [
    { key: 'asset_tag', header: 'Equipment', render: (r) => <Link to={`/equipment/${r.public_id}`}>{r.asset_tag} · {r.name}</Link> },
    { key: 'department', header: 'Department', render: (r) => r.department || '—' },
    ...cfg.columns.map(([key, header, fmt]) => ({ key, header, render: (r) => fmt(r[key]) })),
  ]
  const exportLink = `/reports?report=${cfg.report}&from=${applied.from}&to=${applied.to}`
    + `${applied.category ? `&category=${applied.category}` : ''}${applied.department ? `&department=${applied.department}` : ''}`
    + `${applied.location && kind === 'utilization' ? `&location=${applied.location}` : ''}`

  return (
    <>
      <div className="page-head"><h1>{cfg.title}</h1></div>
      <form className="rp-toolbar" onSubmit={(e) => { e.preventDefault(); setPage(1); setApplied(draft) }}>
        <FormField label="From" name="k_from" type="date" value={draft.from} onChange={set('from')} />
        <FormField label="To" name="k_to" type="date" value={draft.to} onChange={set('to')} />
        <FormField label="Category" name="k_cat" as="select" value={draft.category} onChange={set('category')} options={categories} />
        <FormField label="Department" name="k_dept" as="select" value={draft.department} onChange={set('department')} options={departments} />
        <FormField label="Location" name="k_loc" as="select" value={draft.location} onChange={set('location')} options={locations} />
        <FormField label="Order by" name="k_order" as="select" value={orderKey} onChange={(e) => { setOrderKey(e.target.value); setPage(1) }}
          options={[{ value: 'asset_tag', label: 'Asset tag' }, ...cfg.columns.map(([k, l]) => ({ value: k, label: l }))]} />
        <Button onClick={() => { setDesc((d) => !d); setPage(1) }}>{desc ? 'Highest first' : 'Lowest first'}</Button>
        <Button type="submit" variant="primary">Apply</Button>
        {canReport && <Link to={exportLink}>Export through the report center</Link>}
      </form>
      <p className="rp-note">
        Based on the daily statistics{res.data?.data_up_to ? `, data up to ${fmtDay(res.data.data_up_to)}` : ''}. Period {fmtDay(applied.from)} to {fmtDay(applied.to)}.
      </p>
      <FetchError error={res.error} />
      <Table columns={columns} rows={res.data?.results} rowKey="public_id" loading={res.loading} empty="No equipment has statistics for this period." />
      <Pagination page={page} pageSize={PAGE_SIZE} count={res.data?.count ?? 0} onPageChange={setPage} />
    </>
  )
}
