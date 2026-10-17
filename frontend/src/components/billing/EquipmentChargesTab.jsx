import { useState } from 'react'
import { Table } from '../ui'
import { Pager, RULE_LABEL, StatusPill, fmtD, inr, qs, qty, rowOf, useFetch } from './shared.jsx'

// "Charges" tab of the equipment detail page. Mount it only for users holding charge.view.
export default function EquipmentChargesTab({ equipment, equipmentId }) {
  const id = equipmentId || equipment?.public_id
  const [page, setPage] = useState(1)
  const { data, loading } = useFetch(`/equipment/${id}/charges/?${qs({ page })}`)
  const m = data?.mapping
  const recs = data?.records
  const columns = [
    { key: 'record_number', header: 'Record' },
    { key: 'charge_date', header: 'Date', render: (a, b) => fmtD(rowOf(a, b).charge_date) },
    { key: 'billing_rule', header: 'Rule', render: (a, b) => RULE_LABEL[rowOf(a, b).billing_rule] },
    { key: 'quantity', header: 'Quantity', render: (a, b) => `${qty(rowOf(a, b).quantity)} ${rowOf(a, b).unit_label}` },
    { key: 'amount', header: 'Amount', render: (a, b) => inr(rowOf(a, b).amount) },
    { key: 'patient_reference', header: 'Patient' },
    { key: 'status', header: 'Status', render: (a, b) => <StatusPill status={rowOf(a, b).status} /> },
  ]
  return (
    <div>
      <h3>Charge mapping today</h3>
      {loading && !data ? <p>Loading...</p> : m ? (
        <p>
          {m.charge_item_name} - {RULE_LABEL[m.billing_rule]}, charged from {m.basis === 'USAGE_LOG' ? 'usage logs' : 'allocations'},
          {' '}{inr(m.unit_rate)} per {m.unit_label}
          {m.billing_rule === 'BUNDLED' ? `, covered by package ${m.bundle_reference}` : ''}
          {' '}(set on the {data.level === 'EQUIPMENT' ? 'equipment' : data.level === 'CATEGORY' ? 'category' : 'category group'}).
        </p>
      ) : <p>No charge mapping applies to this equipment today, so nothing is charged.</p>}
      <h3>Latest charge records</h3>
      <Table columns={columns} rows={recs?.results || []} loading={loading} empty="No charge records for this equipment." />
      <Pager data={recs} page={page} onPage={setPage} />
    </div>
  )
}
