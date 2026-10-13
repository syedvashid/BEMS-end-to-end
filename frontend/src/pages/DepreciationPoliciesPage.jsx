import { useState } from 'react'
import { api } from '../api/client'
import PolicyFormModal from '../components/finance/PolicyFormModal'
import {
  ErrorNote, fmtNum, lbl, opts, useAction, withBlank, clean,
} from '../components/finance/shared'
import SimplePager from '../components/SimplePager'
import { Button, FormField, Table, useToast } from '../components/ui'
import { useFacility } from '../context/FacilityContext'
import useFetch from '../hooks/useFetch'

function SettingsCard() {
  const { can } = useFacility()
  const toast = useToast()
  const res = useFetch('/finance-settings/')
  const [v, setV] = useState(null)
  const act = useAction()
  const s = res.data
  const form = v || (s ? {
    threshold: s.maintenance_cost_threshold_percent,
    committee: s.committee_required_above_book_value ?? '',
  } : null)
  if (!form) return null
  const editable = can('finance.manage')
  const set = (k) => (e) => setV({ ...form, [k]: e.target.value })
  const save = () => act.run(async () => {
    await api.put('/finance-settings/', {
      maintenance_cost_threshold_percent: Number(form.threshold),
      committee_required_above_book_value: form.committee === '' ? null : Number(form.committee),
      ...(s.row_version ? { row_version: s.row_version } : {}),
    })
    setV(null); res.reload(); toast.success('Finance settings saved.')
  })
  return (
    <div className="fin-section">
      <h3>Finance settings</h3>
      {s.is_default && <p className="muted">Defaults are in use. Saving creates this facility's settings.</p>}
      <div className="row">
        <FormField label="Maintenance cost threshold (% of purchase cost)" name="threshold" type="number" step="0.01"
          value={form.threshold} disabled={!editable} onChange={set('threshold')} />
        <FormField label="Committee reference required above book value (INR)" name="committee" type="number" step="0.01"
          value={form.committee} disabled={!editable} hint="Leave empty to never require it." onChange={set('committee')} />
        {editable && <Button variant="primary" loading={act.busy} onClick={save}>Save settings</Button>}
      </div>
      <ErrorNote error={act.error} />
    </div>
  )
}

export default function DepreciationPoliciesPage() {
  const { can } = useFacility()
  const toast = useToast()
  const [f, setF] = useState({ scope: '', method: '' })
  const [page, setPage] = useState(1)
  const [editing, setEditing] = useState(null) // null | 'new' | policy
  const res = useFetch('/depreciation-policies/', clean({ ...f, page, page_size: 20 }))
  const del = useAction()
  const set = (k) => (e) => { setF((s) => ({ ...s, [k]: e.target.value })); setPage(1) }
  const manage = can('finance.manage')

  const remove = (p) => {
    if (!window.confirm('Remove this policy? Equipment that depends on it will be skipped by the next run.')) return
    del.run(async () => { await api.delete(`/depreciation-policies/${p.public_id}/`, { params: { row_version: p.row_version } }); toast.success('Policy removed.'); res.reload() })
  }

  return (
    <section>
      <div className="page-head">
        <h2>Depreciation policies</h2><span className="spacer" />
        {manage && <Button variant="primary" onClick={() => setEditing('new')}>New policy</Button>}
      </div>
      <SettingsCard />
      <h3>Policies</h3>
      <p className="muted">Resolution order: the equipment's own policy, then its category, then the category's parent group.</p>
      <div className="row">
        <FormField label="Applies to" name="scope" as="select" value={f.scope} onChange={set('scope')}
          options={withBlank([{ value: 'CATEGORY', label: 'Category' }, { value: 'EQUIPMENT', label: 'Equipment' }])} />
        <FormField label="Method" name="method" as="select" value={f.method} onChange={set('method')}
          options={withBlank(opts(['STRAIGHT_LINE', 'WRITTEN_DOWN_VALUE']))} />
      </div>
      <ErrorNote error={del.error} />
      {res.error && <div className="alert alert-danger">{(res.error.message ?? res.error.error?.message) || 'Could not load policies.'}</div>}
      <Table rows={res.data?.results} loading={res.loading} empty="No policies yet. Equipment without a policy is skipped by the monthly run."
        columns={[
          { key: 'scope', header: 'Applies to', render: (p) => (p.scope === 'EQUIPMENT' ? `Equipment ${p.equipment_asset_tag || ''}` : `Category ${p.category_name || ''}`) },
          { key: 'method', header: 'Method', render: (p) => lbl(p.method) },
          { key: 'basis', header: 'Life / rate', render: (p) => (p.method === 'STRAIGHT_LINE' ? `${fmtNum(p.useful_life_years)} years` : `${fmtNum(p.rate_percent, 3)} % a year`) },
          { key: 'salvage_percent', header: 'Salvage', render: (p) => `${fmtNum(p.salvage_percent)} %` },
          { key: 'start_rule', header: 'Starts from', render: (p) => lbl(p.start_rule) },
          { key: 'actions', header: '', render: (p) => manage && (
            <>
              <Button size="sm" onClick={() => setEditing(p)}>Edit</Button>{' '}
              <Button size="sm" variant="danger" onClick={() => remove(p)}>Remove</Button>
            </>
          ) },
        ]} />
      <SimplePager page={page} count={res.data?.count} pageSize={20} onPage={setPage} />
      {editing && (
        <PolicyFormModal policy={editing === 'new' ? null : editing} onClose={() => setEditing(null)}
          onDone={() => { setEditing(null); toast.success('Policy saved.'); res.reload() }} />
      )}
    </section>
  )
}
