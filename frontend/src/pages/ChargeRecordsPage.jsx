import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Modal, Table, useToast } from '../components/ui'
import ChargeRecordModal from '../components/billing/ChargeRecordModal.jsx'
import { DepartmentSelect, EquipmentPicker } from '../components/billing/pickers.jsx'
import {
  Badge, ErrBox, Field, Pager, RULES, RULE_LABEL, STATUS, StatusPill, api, fmtD, inr, parseApiError, qs, qty, rowOf,
  useFetch, usePermission,
} from '../components/billing/shared.jsx'

const BLANK = {
  status: '', equipment: '', patient_reference: '', department: '', charge_date_from: '', charge_date_to: '',
  billing_rule: '', exported: '',
}
const clean = (o) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== '' && v !== null && v !== undefined))

export default function ChargeRecordsPage() {
  const navigate = useNavigate()
  const toast = useToast()
  const canApprove = usePermission('charge.approve')
  const [filters, setFilters] = useState(BLANK)
  const [applied, setApplied] = useState(BLANK)
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState({})            // public_id -> row
  const [detailId, setDetailId] = useState(null)
  const [exportOpen, setExportOpen] = useState(false)
  const [exportRef, setExportRef] = useState('')
  const [exportAll, setExportAll] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const { data, loading, reload } = useFetch(`/charge-records/?${qs({ ...applied, page, page_size: 20 })}`)
  const setF = (k) => (e) => setFilters((s) => ({ ...s, [k]: e.target.value }))
  const chosen = Object.values(selected)
  const pending = chosen.filter((r) => r.status === 'PENDING_REVIEW')
  const exportable = chosen.filter((r) => ['APPROVED', 'REVERSED'].includes(r.status) && !r.exported_at)

  const toggle = (r) => setSelected((s) => {
    const n = { ...s }
    if (n[r.public_id]) delete n[r.public_id]; else n[r.public_id] = r
    return n
  })
  const togglePage = (checked) => setSelected((s) => {
    const n = { ...s }
    ;(data?.results || []).forEach((r) => { if (checked) n[r.public_id] = r; else delete n[r.public_id] })
    return n
  })
  const allOnPage = (data?.results || []).length > 0 && (data.results || []).every((r) => selected[r.public_id])

  async function approveSelected() {
    setBusy(true); setError(null)
    try {
      let approved = 0, skipped = 0
      const ids = pending.map((r) => r.public_id)
      for (let i = 0; i < ids.length; i += 200) {
        const r = await api.post('/charge-records/approve/', { ids: ids.slice(i, i + 200) })
        approved += r.data.approved.length
        skipped += r.data.skipped.length
      }
      toast.success(`Approved ${approved} record(s)${skipped ? `, skipped ${skipped}` : ''}.`)
      setSelected({})
      reload()
    } catch (err) {
      console.error('[billing] bulk approve failed', err)
      setError(parseApiError(err))
    } finally {
      setBusy(false)
    }
  }

  async function markExported() {
    setBusy(true); setError(null)
    const body = exportAll
      ? { filters: clean({ ...applied, status: 'APPROVED', exported: 'false' }), export_reference: exportRef }
      : { ids: exportable.map((r) => r.public_id), export_reference: exportRef }
    try {
      const r = await api.post('/charge-records/mark-exported/', body)
      toast.success(`Marked ${r.data.exported} record(s) as exported (${r.data.export_reference}).`)
      setExportOpen(false); setExportRef(''); setExportAll(false); setSelected({})
      reload()
    } catch (err) {
      console.error('[billing] mark exported failed', err)
      setError(parseApiError(err))
    } finally {
      setBusy(false)
    }
  }

  function exportCsv() {
    const p = { from: applied.charge_date_from, to: applied.charge_date_to, status: applied.status, equipment: applied.equipment,
      department: applied.department, patient_reference: applied.patient_reference, billing_rule: applied.billing_rule,
      exported: applied.exported }
    navigate(`/reports?${qs({ report: 'BILLING_EVENTS', ...p })}`)
  }

  const columns = [
    ...(canApprove ? [{ key: 'select',
      header: <input type="checkbox" aria-label="Select all on this page" checked={allOnPage} onChange={(e) => togglePage(e.target.checked)} />,
      render: (a, b) => { const r = rowOf(a, b); return (
        <span onClick={(e) => e.stopPropagation()}><input type="checkbox" aria-label={`Select ${r.record_number}`} checked={!!selected[r.public_id]} onChange={() => toggle(r)} /></span>) } }] : []),
    { key: 'record_number', header: 'Record' },
    { key: 'charge_date', header: 'Date', render: (a, b) => fmtD(rowOf(a, b).charge_date) },
    { key: 'equipment', header: 'Equipment', render: (a, b) => { const e = rowOf(a, b).equipment; return `${e.asset_tag} - ${e.name}` } },
    { key: 'billing_rule', header: 'Rule', render: (a, b) => RULE_LABEL[rowOf(a, b).billing_rule] },
    { key: 'quantity', header: 'Quantity', render: (a, b) => `${qty(rowOf(a, b).quantity)} ${rowOf(a, b).unit_label}` },
    { key: 'amount', header: 'Amount', render: (a, b) => inr(rowOf(a, b).amount) },
    { key: 'patient_reference', header: 'Patient' },
    { key: 'status', header: 'Status', render: (a, b) => { const r = rowOf(a, b); return (
      <span><StatusPill status={r.status} />{r.record_type === 'REVERSAL' ? <> <Badge tone="info">Reversal</Badge></> : null}
        {r.exported_at ? <> <Badge tone="neutral">Exported</Badge></> : null}</span>) } },
  ]

  return (
    <section>
      <div className="page-head">
        <h1>Charge Records</h1><span className="spacer" />
        <Button onClick={exportCsv}>Export CSV</Button>
      </div>
      <form className="filters"
        onSubmit={(e) => { e.preventDefault(); setPage(1); setApplied(filters) }}>
        <Field label="Status" name="f_status" as="select" value={filters.status} onChange={setF('status')}
          options={[{ value: '', label: 'All' }, ...Object.entries(STATUS).map(([value, s]) => ({ value, label: s.label }))]} />
        <Field label="Rule" name="f_rule" as="select" value={filters.billing_rule} onChange={setF('billing_rule')}
          options={[{ value: '', label: 'All' }, ...RULES.slice(0, 5)]} />
        <Field label="Patient reference" name="f_patient" as="input" value={filters.patient_reference} onChange={setF('patient_reference')} />
        <DepartmentSelect value={filters.department} onChange={(v) => setFilters((s) => ({ ...s, department: v }))} />
        <Field label="From" name="f_from" as="input" type="date" value={filters.charge_date_from} onChange={setF('charge_date_from')} />
        <Field label="To" name="f_to" as="input" type="date" value={filters.charge_date_to} onChange={setF('charge_date_to')} />
        <Field label="Exported" name="f_exp" as="select" value={filters.exported} onChange={setF('exported')}
          options={[{ value: '', label: 'All' }, { value: 'true', label: 'Exported' }, { value: 'false', label: 'Not exported' }]} />
        <EquipmentPicker value={filters.equipment} onChange={(v) => setFilters((s) => ({ ...s, equipment: v }))} hint="Optional" />
        <div className="row">
          <Button type="submit">Search</Button>
          <Button type="button" onClick={() => { setFilters(BLANK); setApplied(BLANK); setPage(1) }}>Clear</Button>
        </div>
      </form>
      {canApprove && (
        <div className="row" style={{ marginBottom: 12 }}>
          <Button variant="primary" loading={busy} disabled={pending.length === 0} onClick={approveSelected}>Approve selected ({pending.length})</Button>
          <Button onClick={() => setExportOpen(true)}>Mark exported</Button>
        </div>
      )}
      <ErrBox error={error} />
      <Table columns={columns} rows={data?.results || []} loading={loading} empty="No charge records match these filters."
        onRowClick={(r) => setDetailId(r.public_id)} />
      <Pager data={data} page={page} onPage={setPage} />
      {detailId && <ChargeRecordModal id={detailId} canApprove={canApprove} onClose={() => setDetailId(null)} onChanged={reload} />}
      {exportOpen && (
        <Modal title="Mark records as exported" onClose={() => setExportOpen(false)}
          footer={<><Button onClick={() => setExportOpen(false)}>Cancel</Button>
            <Button loading={busy} disabled={!exportRef.trim() || (!exportAll && exportable.length === 0)} onClick={markExported}>Mark exported</Button></>}>
          <p>Use this after you have sent the Billing Events CSV to the billing team.</p>
          <Field label="Export reference" name="export_reference" as="input" required value={exportRef}
            onChange={(e) => setExportRef(e.target.value)} hint="For example the batch number or the date sent" />
          <label className="check">
            <input type="checkbox" checked={exportAll} onChange={(e) => setExportAll(e.target.checked)} />
            All approved, not yet exported records that match the current filters
          </label>
          {!exportAll && <p className="muted">{exportable.length} selected approved record(s) will be marked.</p>}
        </Modal>
      )}
    </section>
  )
}
