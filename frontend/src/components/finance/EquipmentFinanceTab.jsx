import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import { useFacility } from '../../context/FacilityContext'
import useFetch from '../../hooks/useFetch'
import { Button, FormField, Modal, Table, useToast } from '../ui'
import CondemnationRequestModal from './CondemnationRequestModal'
import {
  ErrorNote, IndicatorChip, LineChart, REASON_TEXT, fieldErr, fmtDay, fmtMoney, fmtNum, lbl, lastMonthInput, useAction,
} from './shared'

const Card = ({ label, value }) => (
  <div className="fin-card"><div className="fin-card-label">{label}</div><div className="fin-card-value">{value}</div></div>
)
const REASON_MESSAGE = {
  NOT_OWNED: 'This equipment is not owned, so it is not depreciated.',
  NOT_ELIGIBLE_STAGE: 'Only commissioned or condemned equipment is depreciated.',
  NO_COST: 'No purchase cost is recorded, so it cannot be depreciated.',
  NO_POLICY: 'No depreciation policy applies to this equipment or its category.',
  NO_START_DATE: 'There is no start date (commissioning or invoice date) to start from.',
}

function OpeningBookValueModal({ equipment, onClose, onDone }) {
  const [v, setV] = useState({ as_of_month: lastMonthInput(), book_value: '' })
  const act = useAction()
  const submit = () => act.run(async () => {
    await api.post(`/equipment/${equipment.public_id}/opening-book-value/`, { as_of_month: v.as_of_month, book_value: Number(v.book_value) })
    onDone()
  })
  return (
    <Modal title="Opening book value" onClose={onClose}
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={act.busy} onClick={submit}>Save</Button></>}>
      <p className="muted">For legacy equipment: sets the book value at the end of a past month. Monthly depreciation continues from the next month. This is only possible while no entry exists for that month or later.</p>
      <FormField label="Book value at the end of" name="as_of_month" type="month" max={lastMonthInput()} required value={v.as_of_month}
        error={fieldErr(act.error, 'as_of_month')} onChange={(e) => setV({ ...v, as_of_month: e.target.value })} />
      <FormField label="Book value (INR)" name="book_value" type="number" step="0.01" min="0" required value={v.book_value}
        error={fieldErr(act.error, 'book_value')} onChange={(e) => setV({ ...v, book_value: e.target.value })} />
      <ErrorNote error={act.error} />
    </Modal>
  )
}

export default function EquipmentFinanceTab({ equipment: e, reload }) {
  const { can } = useFacility()
  const toast = useToast()
  const navigate = useNavigate()
  const [dialog, setDialog] = useState(null)
  const canView = can('finance.view')
  const info = useFetch(`/equipment/${e.public_id}/finance/`, undefined, canView)
  const dep = useFetch(`/equipment/${e.public_id}/depreciation/`, { page_size: 100 }, canView)
  const tco = useFetch(`/equipment/${e.public_id}/tco/`, undefined, canView)

  if (!canView) return <p className="muted">You do not have permission to view finance details.</p>
  const i = info.data
  const entries = dep.data?.results || []
  const actual = [...entries].reverse().map((r) => ({ x: r.period_month, y: Number(r.closing_value) }))
  const projection = (dep.data?.projection || []).map((r) => ({ x: r.period_month, y: Number(r.closing_value) }))
  const t = tco.data
  const refreshAll = () => { info.reload(); dep.reload(); tco.reload(); reload?.() }
  const depreciable = ['COMMISSIONED', 'CONDEMNED'].includes(e.lifecycle_stage) && e.ownership_type === 'OWNED'

  return (
    <div>
      <div className="row">
        {can('finance.manage') && depreciable && <Button onClick={() => setDialog('opening')}>Opening book value</Button>}
        {can('condemnation.add') && e.lifecycle_stage === 'COMMISSIONED' && (
          <Button variant="danger" onClick={() => setDialog('condemn')}>Request condemnation</Button>
        )}
      </div>
      {info.error && <div className="alert alert-danger">Could not load finance details.</div>}

      {i && (
        <>
          <div className="fin-cards">
            <Card label="Book value" value={fmtMoney(i.book_value)} />
            <Card label="Accumulated depreciation" value={fmtMoney(i.accumulated_depreciation)} />
            <Card label="Capitalised cost" value={fmtMoney(i.capitalised_cost)} />
            <Card label="Last depreciation month" value={i.last_depreciation_month ? i.last_depreciation_month.slice(0, 7) : '—'} />
          </div>
          {!i.depreciable && <div className="alert alert-warning">{REASON_MESSAGE[i.reason] || 'Not depreciable.'}</div>}
          {i.policy && (
            <p className="muted">
              Policy ({lbl(i.policy.source)}): {lbl(i.policy.method)}
              {i.policy.method === 'STRAIGHT_LINE' ? `, ${fmtNum(i.policy.useful_life_years)} years` : `, ${fmtNum(i.policy.rate_percent, 3)} % a year`},
              salvage {fmtNum(i.policy.salvage_percent)} % ({fmtMoney(i.salvage_value)}), starts {fmtDay(i.effective_start_date)}.
            </p>
          )}
        </>
      )}

      <h3>Book value</h3>
      <LineChart actual={actual} projection={projection} />
      <p className="muted">Solid line: recorded months. Dashed line: projection to salvage value.</p>

      <h3>Depreciation schedule</h3>
      <Table rows={entries} loading={dep.loading} empty="No depreciation entries yet." rowKey="public_id"
        columns={[
          { key: 'period_month', header: 'Month' },
          { key: 'entry_type', header: 'Type', render: (r) => lbl(r.entry_type) },
          { key: 'opening_value', header: 'Opening', render: (r) => fmtMoney(r.opening_value) },
          { key: 'charge', header: 'Charge', render: (r) => fmtMoney(r.charge) },
          { key: 'closing_value', header: 'Closing', render: (r) => fmtMoney(r.closing_value) },
          { key: 'days_charged', header: 'Days', render: (r) => r.days_charged ?? '—' },
        ]} />
      {dep.data?.count > 100 && <p className="muted">Showing the latest 100 months of {dep.data.count}.</p>}

      <h3>Total cost of ownership</h3>
      {t && (
        <>
          <p>Replacement indicator: <IndicatorChip value={t.replacement_indicator} /></p>
          {t.reasons?.length > 0 && <ul>{t.reasons.map((r) => <li key={r}>{REASON_TEXT[r] || lbl(r)} (threshold {fmtNum(t.threshold_percent)} %).</li>)}</ul>}
          <Table rowKey="k" rows={[
            { k: 'a', label: 'Acquisition cost', value: fmtMoney(t.acquisition_cost) },
            { k: 'i', label: 'Installation cost', value: fmtMoney(t.installation_cost) },
            { k: 'l', label: 'Labour (completed work orders)', value: fmtMoney(t.labour_cost) },
            { k: 'v', label: 'Vendor service (completed work orders)', value: fmtMoney(t.vendor_cost) },
            { k: 'p', label: 'Spare parts consumed', value: fmtMoney(t.parts_cost) },
            { k: 'm', label: 'AMC fees (prorated)', value: fmtMoney(t.amc_cost) },
            { k: 's', label: 'Salvage value (subtracted)', value: fmtMoney(t.salvage_value) },
            { k: 't', label: 'Total cost of ownership', value: fmtMoney(t.total_cost_of_ownership) },
            { k: 'r', label: 'Maintenance cost / purchase cost', value: t.maintenance_cost_ratio_percent == null ? '—' : `${fmtNum(t.maintenance_cost_ratio_percent)} %` },
            { k: 'g', label: 'Age / expected life (years)', value: `${fmtNum(t.age_years)} / ${fmtNum(t.expected_life_years)}` },
            { k: 'h', label: `Cost per hour (${fmtNum(t.usage_hours)} h)`, value: fmtMoney(t.cost_per_hour) },
            { k: 'u', label: `Cost per use (${t.session_count} sessions)`, value: fmtMoney(t.cost_per_use) },
          ]} columns={[{ key: 'label', header: 'Component' }, { key: 'value', header: 'Amount' }]} />
        </>
      )}
      <p className="muted"><Link to="/finance">Finance summary</Link></p>

      {dialog === 'opening' && (
        <OpeningBookValueModal equipment={e} onClose={() => setDialog(null)}
          onDone={() => { setDialog(null); toast.success('Opening book value saved.'); refreshAll() }} />
      )}
      {dialog === 'condemn' && (
        <CondemnationRequestModal equipment={{ public_id: e.public_id, asset_tag: e.asset_tag, name: e.name }}
          onClose={() => setDialog(null)}
          onDone={(r) => { setDialog(null); toast.success(`Request ${r.request_number} created.`); navigate(`/condemnation/${r.public_id}`) }} />
      )}
    </div>
  )
}
