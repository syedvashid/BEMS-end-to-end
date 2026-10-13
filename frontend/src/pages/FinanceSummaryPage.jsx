import { useState } from 'react'
import {
  ErrorNote, fmtMoney, lastMonthInput, lbl, useAction,
} from '../components/finance/shared'
import { Button, FormField, Modal, Table, useToast } from '../components/ui'
import { api } from '../api/client'
import { useFacility } from '../context/FacilityContext'
import useFetch from '../hooks/useFetch'

const GROUPS = [
  { value: 'category', label: 'Category' },
  { value: 'department', label: 'Department' },
  { value: 'funding_source', label: 'Funding source' },
  { value: 'ownership_type', label: 'Ownership type' },
  { value: 'location', label: 'Location' },
]

const Card = ({ label, value }) => (
  <div className="fin-card"><div className="fin-card-label">{label}</div><div className="fin-card-value">{value}</div></div>
)

function RunDepreciationModal({ onClose, onDone }) {
  const [month, setMonth] = useState(lastMonthInput())
  const [result, setResult] = useState(null)
  const act = useAction()
  const submit = () => act.run(async () => {
    const { data } = await api.post('/depreciation/run/', month ? { month } : {})
    setResult(data); onDone()
  })
  return (
    <Modal title="Run depreciation" onClose={onClose}
      footer={<>
        <Button variant="ghost" onClick={onClose}>{result ? 'Close' : 'Cancel'}</Button>
        {!result && <Button variant="primary" loading={act.busy} onClick={submit}>Run</Button>}
      </>}>
      {!result && (
        <>
          <p className="muted">Creates the missing monthly entries up to the chosen month (catch-up). Running it twice is safe.</p>
          <FormField label="Up to month" name="month" type="month" value={month} max={lastMonthInput()}
            hint="Leave empty for the last completed month." onChange={(e) => setMonth(e.target.value)} />
        </>
      )}
      <ErrorNote error={act.error} />
      {result && (
        <div className="eq-grid">
          <div className="eq-kv"><span className="muted">Month</span><span>{result.run_period}</span></div>
          <div className="eq-kv"><span className="muted">Equipment processed</span><span>{result.assets_processed}</span></div>
          <div className="eq-kv"><span className="muted">Entries created</span><span>{result.entries_created}</span></div>
          <div className="eq-kv"><span className="muted">Total charge</span><span>{fmtMoney(result.total_charge)}</span></div>
          <div className="eq-kv"><span className="muted">Skipped: no policy</span><span>{result.skipped_no_policy}</span></div>
          <div className="eq-kv"><span className="muted">Skipped: no cost</span><span>{result.skipped_no_cost}</span></div>
          <div className="eq-kv"><span className="muted">Skipped: no start date</span><span>{result.skipped_no_start_date}</span></div>
          <div className="eq-kv"><span className="muted">Failed</span><span>{result.failed_count}</span></div>
          {result.failed?.length > 0 && (
            <div className="alert alert-warning">Failed: {result.failed.map((f) => f.asset_tag).join(', ')}</div>
          )}
        </div>
      )}
    </Modal>
  )
}

export default function FinanceSummaryPage() {
  const { can } = useFacility()
  const toast = useToast()
  const [groupBy, setGroupBy] = useState('category')
  const [running, setRunning] = useState(false)
  const res = useFetch('/finance/summary/', { group_by: groupBy })
  const tco = useAction()
  const t = res.data?.totals

  const generate = () => tco.run(async () => {
    const { data } = await api.post('/tco/generate/', {})
    toast.success(`TCO snapshots: ${data.created} created, ${data.skipped_existing} already existed.`)
  })

  return (
    <section>
      <div className="page-head">
        <h2>Finance</h2><span className="spacer" />
        {can('finance.run') && <Button onClick={generate} loading={tco.busy}>Generate TCO snapshots</Button>}
        {can('finance.run') && <Button variant="primary" onClick={() => setRunning(true)}>Run depreciation</Button>}
      </div>
      <ErrorNote error={tco.error} />
      <div className="row">
        <FormField label="Group by" name="group_by" as="select" value={groupBy} options={GROUPS}
          onChange={(e) => setGroupBy(e.target.value)} />
      </div>
      {res.error && <div className="alert alert-danger">{(res.error.message ?? res.error.error?.message) || 'Could not load the summary.'}</div>}
      {t && (
        <div className="fin-cards">
          <Card label="Capitalised cost (owned)" value={fmtMoney(t.capitalised_cost)} />
          <Card label="Accumulated depreciation" value={fmtMoney(t.accumulated_depreciation)} />
          <Card label="Book value" value={fmtMoney(t.book_value)} />
          <Card label="Cannot be depreciated" value={t.cannot_depreciate_count} />
        </div>
      )}
      <Table rows={res.data?.groups} loading={res.loading} rowKey="key" empty="No equipment on the books yet."
        columns={[
          { key: 'label', header: lbl(groupBy), render: (r) => r.label },
          { key: 'count', header: 'Equipment' },
          { key: 'owned_count', header: 'Owned' },
          { key: 'capitalised_cost', header: 'Capitalised cost', render: (r) => fmtMoney(r.capitalised_cost) },
          { key: 'accumulated_depreciation', header: 'Accumulated', render: (r) => fmtMoney(r.accumulated_depreciation) },
          { key: 'book_value', header: 'Book value', render: (r) => fmtMoney(r.book_value) },
          { key: 'cannot_depreciate_count', header: 'Cannot be depreciated', render: (r) => r.cannot_depreciate_count || '—',
            },
        ]} />
      <p className="muted">"Cannot be depreciated" counts owned equipment with no policy, no purchase cost or no start date. Book value uses the latest monthly entry.</p>
      {running && <RunDepreciationModal onClose={() => setRunning(false)} onDone={res.reload} />}
    </section>
  )
}
