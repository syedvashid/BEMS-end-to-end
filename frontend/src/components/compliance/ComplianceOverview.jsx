import { Link } from 'react-router-dom'
import { CalChip, fmtDate } from './shared'

export default function ComplianceOverview({ equipment: e }) {
  if (!e.calibration_status && !e.current_warranty && !e.current_amc) return null
  return (
    <div>
      {e.calibration_status && (
        <p>Calibration: <CalChip status={e.calibration_status} /> {e.next_calibration_due && `next due ${fmtDate(e.next_calibration_due)}`}
          {e.has_unresolved_failure && ' · last result: fail'}</p>)}
      <p>Warranty: {e.current_warranty ? `${e.current_warranty.warranty_type.toLowerCase()} until ${fmtDate(e.current_warranty.end_date)}` : 'none active'}</p>
      <p>AMC: {e.current_amc ? <>{e.current_amc.contract_number} ({e.current_amc.contract_type.replace('_', '-').toLowerCase()}) until {fmtDate(e.current_amc.end_date)}</> : <>none active</>}</p>
    </div>
  )
}