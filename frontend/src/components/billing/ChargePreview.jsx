import { Badge, fmtD, inr, qty, useFetch, usePermission } from './shared.jsx'

// Charge preview for the Phase 7 Release dialog. Shows nothing without charge.view.
export default function ChargePreview({ allocationId }) {
  const can = usePermission('charge.view')
  const { data, loading, error } = useFetch(`/allocations/${allocationId}/charge-preview/`, undefined, !!(can && allocationId))
  if (!can || !allocationId) return null
  if (loading) return <p>Calculating charge...</p>
  if (error || !data) return <p style={{ opacity: 0.7 }}>The charge preview is not available right now.</p>
  const lines = data.lines || []
  return (
    <div style={{ marginTop: 12 }}>
      <h4 style={{ margin: '0 0 6px' }}>Charge preview</h4>
      {data.mapping && <p style={{ margin: '0 0 6px', opacity: 0.8 }}>
        {data.mapping.charge_item_name} ({data.mapping.billing_rule.toLowerCase().replace('_', ' ')}, {inr(data.mapping.unit_rate)} per {data.mapping.unit_label})
      </p>}
      {(data.reasons || []).map((r) => <p key={r.reason} style={{ margin: '0 0 6px' }}>{r.message}</p>)}
      {lines.length > 0 && (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <tbody>
            {lines.map((l) => (
              <tr key={`${l.period_key}-${l.mapping}`}>
                <td>{l.period_key.startsWith('DAY:') ? `Day ${Number(l.period_key.slice(4)) + 1} (${fmtD(l.charge_date)})` : l.rule.replace('_', ' ').toLowerCase()}</td>
                <td>{qty(l.quantity)} {l.unit_label}</td>
                <td style={{ textAlign: 'right' }}>{inr(l.amount)}</td>
                <td>{l.already_charged ? <Badge tone="info">Already charged</Badge> : null}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {lines.length > 0 && (
        <p style={{ margin: '8px 0 0' }}>
          <strong>To be charged now: {inr(data.total)}</strong>
          {Number(data.accrued_amount) !== 0 && <span> (already accrued: {inr(data.accrued_amount)})</span>}
        </p>
      )}
    </div>
  )
}
