import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import ReplacementPlanModal from '../components/finance/ReplacementPlanModal'
import {
  ErrorNote, IndicatorChip, PlanChip, REASON_TEXT, clean, fmtMoney, fmtNum, opts, useAction, withBlank,
} from '../components/finance/shared'
import SimplePager from '../components/SimplePager'
import { Button, FormField, StatusBadge, Table, useToast } from '../components/ui'
import { useFacility } from '../context/FacilityContext'
import useFetch from '../hooks/useFetch'

export default function ReplacementPlanningPage() {
  const { can } = useFacility()
  const toast = useToast()
  const [indicator, setIndicator] = useState('')
  const [cPage, setCPage] = useState(1)
  const [status, setStatus] = useState('')
  const [pPage, setPPage] = useState(1)
  const [modal, setModal] = useState(null) // { plan?, equipment? }
  const cands = useFetch('/replacement-candidates/', clean({ indicator, page: cPage, page_size: 20 }))
  const plans = useFetch('/replacement-plans/', clean({ status, page: pPage, page_size: 20 }))
  const gen = useAction()
  const manage = can('finance.manage')

  const generate = () => gen.run(async () => {
    const { data } = await api.post('/tco/generate/', {})
    toast.success(`Snapshots: ${data.created} created, ${data.skipped_existing} already existed.`)
    cands.reload()
  })

  return (
    <section>
      <div className="page-head">
        <h2>Replacement planning</h2><span className="spacer" />
        {can('finance.run') && <Button onClick={generate} loading={gen.busy}>Generate snapshots</Button>}
        {manage && <Button variant="primary" onClick={() => setModal({})}>New plan</Button>}
      </div>
      <ErrorNote error={gen.error} />

      <h3>Candidates</h3>
      <p className="muted">From the latest TCO snapshot of each equipment. Generate snapshots first to refresh them.</p>
      <div className="row">
        <FormField label="Indicator" name="indicator" as="select" value={indicator}
          options={withBlank(opts(['REVIEW', 'REPLACE_RECOMMENDED']))} onChange={(e) => { setIndicator(e.target.value); setCPage(1) }} />
      </div>
      {cands.error && <div className="alert alert-danger">{(cands.error.message ?? cands.error.error?.message) || 'Could not load candidates.'}</div>}
      <Table rows={cands.data?.results} loading={cands.loading} empty="No candidates. Generate TCO snapshots, or nothing is flagged yet."
        columns={[
          { key: 'equipment', header: 'Equipment', render: (r) => <Link to={`/equipment/${r.equipment.public_id}`}>{r.equipment.asset_tag} · {r.equipment.name}</Link> },
          { key: 'replacement_indicator', header: 'Indicator', render: (r) => <IndicatorChip value={r.replacement_indicator} /> },
          { key: 'ratio', header: 'Maintenance / purchase', render: (r) => (r.maintenance_cost_ratio_percent == null ? '—' : `${fmtNum(r.maintenance_cost_ratio_percent)} %`) },
          { key: 'age', header: 'Age / expected life', render: (r) => `${fmtNum(r.age_years)} / ${fmtNum(r.expected_life_years)} yrs` },
          { key: 'total_cost_of_ownership', header: 'TCO', render: (r) => fmtMoney(r.total_cost_of_ownership) },
          { key: 'book_value', header: 'Book value', render: (r) => fmtMoney(r.book_value) },
          { key: 'why', header: 'Why', render: (r) => (r.reasons || []).map((x) => REASON_TEXT[x] || x).join('; ') || '—' },
          { key: 'plan', header: '', render: (r) => (r.has_open_plan
            ? <StatusBadge tone="info">In plan</StatusBadge>
            : manage && <Button size="sm" onClick={() => setModal({ equipment: r.equipment })}>Add to plan</Button>) },
        ]} />
      <SimplePager page={cPage} count={cands.data?.count} pageSize={20} onPage={setCPage} />

      <h3>Replacement plans</h3>
      <div className="row">
        <FormField label="Status" name="status" as="select" value={status}
          options={withBlank(opts(['CANDIDATE', 'APPROVED_FOR_BUDGET', 'DEFERRED', 'COMPLETED', 'CANCELLED']))}
          onChange={(e) => { setStatus(e.target.value); setPPage(1) }} />
      </div>
      <Table rows={plans.data?.results} loading={plans.loading} empty="No replacement plans yet."
        columns={[
          { key: 'equipment', header: 'Equipment', render: (r) => `${r.equipment_asset_tag} · ${r.equipment_name}` },
          { key: 'planned_year', header: 'Year' },
          { key: 'estimated_cost', header: 'Estimated cost', render: (r) => fmtMoney(r.estimated_cost) },
          { key: 'priority', header: 'Priority', render: (r) => r.priority },
          { key: 'status', header: 'Status', render: (r) => <PlanChip value={r.status} /> },
          { key: 'replaced_by_asset_tag', header: 'Replaced by', render: (r) => r.replaced_by_asset_tag || '—' },
          { key: 'edit', header: '', render: (r) => manage && <Button size="sm" onClick={() => setModal({ plan: r })}>Edit</Button> },
        ]} />
      <SimplePager page={pPage} count={plans.data?.count} pageSize={20} onPage={setPPage} />

      {modal && (
        <ReplacementPlanModal plan={modal.plan} equipment={modal.equipment} onClose={() => setModal(null)}
          onDone={() => { setModal(null); toast.success('Plan saved.'); plans.reload(); cands.reload() }} />
      )}
    </section>
  )
}
