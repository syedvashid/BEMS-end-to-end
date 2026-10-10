import { useState } from 'react'
import { Link } from 'react-router-dom'
import { FormField, Pagination, Table } from '../components/ui'
import { BucketChip, clean, fmtDate, useFetch, useOptions, withBlank } from '../components/compliance/shared'

const TYPES = [['CALIBRATION', 'Calibration'], ['WARRANTY', 'Warranty'], ['AMC', 'AMC'], ['LICENCE', 'Licence'], ['DOCUMENT', 'Document']]
const BUCKETS = [['', 'All'], ['OVERDUE', 'Overdue'], ['D7', 'Within 7 days'], ['D30', '8–30 days'], ['D60', '31–60 days'], ['D90', '61–90 days']]
const SOURCE_PATH = { CALIBRATION: '/calibration', WARRANTY: '/warranties', AMC: '/amc-contracts', LICENCE: '/licences', DOCUMENT: '/documents' }

export default function CompliancePage() {
  const [types, setTypes] = useState(TYPES.map(([k]) => k))
  const [bucket, setBucket] = useState('')
  const [within, setWithin] = useState(90)
  const [department, setDepartment] = useState('')
  const [page, setPage] = useState(1)
  const departments = useOptions('/departments/', (d) => ({ value: d.public_id, label: d.name }))

  const { data, loading, error } = useFetch('/compliance/due/', clean({
    page, page_size: 20, bucket, department, within_days: within,
    types: types.length === TYPES.length ? '' : types.join(','),
  }))
  const toggle = (k) => { setTypes((t) => (t.includes(k) ? t.filter((x) => x !== k) : [...t, k])); setPage(1) }
  const rows = (data?.results || []).map((r) => ({ ...r, public_id: `${r.item_type}-${r.source_public_id}` }))

  const columns = [
    { key: 'item_type', header: 'Type', render: (r) => TYPES.find(([k]) => k === r.item_type)?.[1] || r.item_type },
    { key: 'title', header: 'Item', render: (r) => <Link to={SOURCE_PATH[r.item_type]}>{r.title}</Link> },
    {
      key: 'equipment', header: 'Equipment',
      render: (r) => (r.equipment ? <Link to={`/equipment/${r.equipment.public_id}`}>{r.equipment.asset_tag} — {r.equipment.name}</Link> : '—'),
    },
    { key: 'due_date', header: 'Due', render: (r) => fmtDate(r.due_date) },
    { key: 'days_left', header: 'Days', render: (r) => (r.days_left < 0 ? `${-r.days_left} overdue` : r.days_left) },
    { key: 'bucket', header: 'Bucket', render: (r) => <BucketChip bucket={r.bucket} /> },
  ]

  return (
    <div>
      <h1>Due &amp; Expiry</h1>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <fieldset style={{ border: 0, padding: 0 }}>
          <legend>Types</legend>
          {TYPES.map(([k, label]) => (
            <label key={k} style={{ marginRight: 12 }}>
              <input type="checkbox" checked={types.includes(k)} onChange={() => toggle(k)} /> {label}
            </label>
          ))}
        </fieldset>
        <FormField label="Bucket" name="bucket" as="select" options={BUCKETS.map(([value, label]) => ({ value, label }))}
          value={bucket} onChange={(e) => { setBucket(e.target.value); setPage(1) }} />
        <FormField label="Within days" name="within" type="number" min="0" max="365" value={within}
          disabled={!!bucket} onChange={(e) => { setWithin(e.target.value); setPage(1) }} />
        <FormField label="Department" name="department" as="select" options={withBlank(departments, 'All departments')}
          value={department} onChange={(e) => { setDepartment(e.target.value); setPage(1) }} />
      </div>
      {error && <p role="alert">Could not load due items.</p>}
      <Table columns={columns} rows={rows} loading={loading} empty="Nothing is due or expiring." />
      <Pagination page={page} pageSize={20} count={data?.count || 0} onChange={setPage} />
    </div>
  )
}