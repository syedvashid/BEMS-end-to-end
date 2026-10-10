import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, FormError } from '../ui'
import RecordCalibrationModal from './RecordCalibrationModal'
import { ConflictNote, api, fmtDate, useFetch, usePermission, useSubmit } from './shared'

/** wo = work order detail JSON. Call onChanged() to reload the page after a save. */
export default function CoverageSection({ wo, onChanged }) {
  const canEdit = usePermission('work_order.change') && (wo.available_actions || []).includes('edit')
  const canRecord = usePermission('calibration.record')
  const canW = usePermission('warranty.view'), canA = usePermission('amc.view')
  const eq = wo.equipment.public_id
  const ws = useFetch('/warranties/', { equipment: eq }, canW && canEdit)
  const as = useFetch('/amc-contracts/', { equipment: eq }, canA && canEdit)
  const sch = useFetch('/calibration-schedules/', { equipment: eq }, !!wo.source_calibration_record && canRecord)
  const [pick, setPick] = useState('')
  const [rec, setRec] = useState(false)
  const { busy, error, run } = useSubmit()
  const sug = wo.coverage_suggestion

  const save = () => run(async () => {
    const [kind, id] = pick.split(':')
    const body = { row_version: wo.row_version }
    if (kind === 'W') body.warranty_id = id
    else if (kind === 'A') body.amc_contract_id = id
    else { body.coverage_source = pick === 'CLEAR' ? null : pick }
    await api.patch(`/work-orders/${wo.public_id}/`, body)
    setPick(''); onChanged()
  })
  const useSuggestion = () => run(async () => {
    const body = { row_version: wo.row_version }
    if (sug.warranty_id) body.warranty_id = sug.warranty_id
    else if (sug.amc_contract_id) body.amc_contract_id = sug.amc_contract_id
    await api.patch(`/work-orders/${wo.public_id}/`, body)
    onChanged()
  })
  const linked = wo.warranty
    ? `Warranty ${wo.warranty.reference_number || wo.warranty.warranty_type.toLowerCase()} (to ${fmtDate(wo.warranty.end_date)})`
    : wo.amc_contract ? `AMC ${wo.amc_contract.contract_number} (to ${fmtDate(wo.amc_contract.end_date)})` : null

  return (
    <div>
      <h4>Coverage</h4>
      <p>Source: {wo.coverage_source || 'not set'}{linked ? ` — ${linked}` : ''}</p>
      {sug && <p>Suggestion: {sug.message}</p>}
      {canEdit && sug && (sug.warranty_id || sug.amc_contract_id) && !linked && <Button size="sm" onClick={useSuggestion} loading={busy}>Use suggestion</Button>}
      {canEdit && (<>
        <FormError error={error} /><ConflictNote error={error} />
        <select value={pick} onChange={(e) => setPick(e.target.value)} aria-label="Link coverage">
          <option value="">Change coverage…</option>
          {(ws.data?.results || []).map((w) => <option key={w.public_id} value={`W:${w.public_id}`}>Warranty {w.reference_number || w.warranty_type} (to {fmtDate(w.end_date)})</option>)}
          {(as.data?.results || []).map((c) => <option key={c.public_id} value={`A:${c.public_id}`}>AMC {c.contract_number} (to {fmtDate(c.end_date)})</option>)}
          <option value="PAID">Paid</option><option value="IN_HOUSE">In-house</option><option value="CLEAR">Clear coverage</option>
        </select>{' '}
        <Button size="sm" onClick={save} disabled={!pick} loading={busy}>Save</Button>
      </>)}
      {wo.source_calibration_record && (
        <p>Opened by a failed calibration of {fmtDate(wo.source_calibration_record.performed_date)}.{' '}
          <Link to="/calibration">Calibration page</Link>{' '}
          {canRecord && sch.data?.results?.[0] && <Button size="sm" onClick={() => setRec(true)}>Record calibration</Button>}</p>
      )}
      {rec && sch.data?.results?.[0] && <RecordCalibrationModal schedule={sch.data.results[0]} onClose={() => setRec(false)} onSaved={() => { setRec(false); onChanged() }} />}
    </div>
  )
}