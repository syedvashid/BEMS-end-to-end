import { useState } from 'react'
import { Button, Table, useToast } from '../components/ui'
import ChargeCalculator from '../components/billing/ChargeCalculator.jsx'
import ChargeMappingFormModal from '../components/billing/ChargeMappingFormModal.jsx'
import ChargeSettingsCard from '../components/billing/ChargeSettingsCard.jsx'
import ConfirmModal from '../components/billing/ConfirmModal.jsx'
import {
  BASIS_LABEL, Badge, Field, Pager, RULES, RULE_LABEL, api, fmtD, inr, qs, rowOf, useFetch, usePermission,
} from '../components/billing/shared.jsx'

export default function ChargeMappingsPage() {
  const toast = useToast()
  const canConfigure = usePermission('charge.configure')
  const [filters, setFilters] = useState({ billing_rule: '', search: '', active_on: '' })
  const [applied, setApplied] = useState(filters)
  const [page, setPage] = useState(1)
  const [editing, setEditing] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const { data, loading, error, reload } = useFetch(`/charge-mappings/?${qs({ ...applied, page, page_size: 20 })}`)
  const setF = (k) => (e) => setFilters((s) => ({ ...s, [k]: e.target.value }))

  const columns = [
    { key: 'scope', header: 'Applies to', render: (a, b) => {
      const m = rowOf(a, b)
      return m.equipment ? <span>{m.equipment_label} <Badge tone="info">Equipment</Badge></span>
        : <span>{m.category_name} <Badge tone="neutral">Category</Badge></span>
    } },
    { key: 'charge_item', header: 'Charge item', render: (a, b) => `${rowOf(a, b).charge_item_code} - ${rowOf(a, b).charge_item_name}` },
    { key: 'billing_rule', header: 'Rule', render: (a, b) => `${RULE_LABEL[rowOf(a, b).billing_rule]} (${BASIS_LABEL[rowOf(a, b).basis]})` },
    { key: 'rate', header: 'Rate', render: (a, b) => {
      const m = rowOf(a, b)
      if (m.billing_rule === 'BUNDLED') return `Package ${m.bundle_reference}`
      if (m.billing_rule === 'DISABLED') return '-'
      return `${inr(m.rate_override ?? m.charge_item_rate)} / ${m.charge_item_unit}${m.rate_override ? ' (override)' : ''}`
    } },
    { key: 'dates', header: 'Effective', render: (a, b) => { const m = rowOf(a, b); return `${fmtD(m.effective_from)} to ${m.effective_to ? fmtD(m.effective_to) : 'no end'}` } },
    ...(canConfigure ? [{ key: 'actions', header: '', className: 'actions', render: (a, b) => {
      const m = rowOf(a, b)
      return (
        <div className="row">
          <Button size="sm" onClick={() => setEditing(m)}>Edit</Button>
          <Button size="sm" variant="danger" onClick={() => setDeleting(m)}>Delete</Button>
        </div>
      )
    } }] : []),
  ]

  return (
    <section>
      <div className="page-head">
        <h1>Charge Mappings</h1><span className="spacer" />
        {canConfigure && <Button variant="primary" onClick={() => setEditing({})}>New mapping</Button>}
      </div>
      <p className="muted">A mapping says how equipment (or a whole category) is charged. A mapping on the equipment wins over its category, which wins over its category group.</p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 24, marginBottom: 16 }}>
        <ChargeSettingsCard />
        <ChargeCalculator />
      </div>
      <form className="filters" onSubmit={(e) => { e.preventDefault(); setPage(1); setApplied(filters) }}>
        <Field label="Rule" name="f_rule" as="select" value={filters.billing_rule} onChange={setF('billing_rule')}
          options={[{ value: '', label: 'All rules' }, ...RULES]} />
        <Field label="Search" name="f_search" as="input" value={filters.search} onChange={setF('search')} />
        <Field label="Active on" name="f_active_on" as="input" type="date" value={filters.active_on} onChange={setF('active_on')} />
        <Button type="submit">Search</Button>
      </form>
      {error && <div className="alert alert-danger">{error.message}</div>}
      <Table columns={columns} rows={data?.results} loading={loading} empty="No charge mappings yet." />
      <Pager data={data} page={page} onPage={setPage} />
      {editing && (
        <ChargeMappingFormModal mapping={editing.public_id ? editing : null} onClose={() => setEditing(null)}
          onSaved={() => { toast.success(editing.public_id ? 'Charge mapping updated.' : 'Charge mapping created.'); setEditing(null); reload() }} />
      )}
      {deleting && (
        <ConfirmModal title="Delete charge mapping" onClose={() => setDeleting(null)}
          onConfirm={async () => {
            await api.delete(`/charge-mappings/${deleting.public_id}/`, { params: { row_version: deleting.row_version } })
            setDeleting(null); toast.success('Charge mapping deleted.'); reload()
          }}>
          <p>Delete this mapping? Existing charge records keep the rate they were calculated with.</p>
        </ConfirmModal>
      )}
    </section>
  )
}
