import { Badge, inr } from './shared.jsx'

// Result of a release or a usage log: the `charges` object returned by the API.
export default function ChargeResult({ charges }) {
  if (!charges) return null
  const created = charges.created || []
  const reasons = charges.not_billable || []
  if (!charges.warning && created.length === 0 && reasons.length === 0) return null
  return (
    <div style={{ marginTop: 8 }}>
      {charges.warning && <p role="alert" className="alert alert-warning">{charges.warning}</p>}
      {created.length > 0 && (
        <>
          <strong>Charges created</strong>
          <ul style={{ margin: '4px 0' }}>
            {created.map((c) => (
              <li key={c.public_id}>{c.record_number}: {inr(c.amount)} <Badge tone={c.status === 'APPROVED' ? 'success' : 'warning'}>
                {c.status === 'APPROVED' ? 'Approved' : 'Pending review'}</Badge></li>
            ))}
          </ul>
        </>
      )}
      {created.length === 0 && reasons.map((r) => <p key={r.reason} style={{ margin: '4px 0', opacity: 0.8 }}>{r.message}</p>)}
    </div>
  )
}
