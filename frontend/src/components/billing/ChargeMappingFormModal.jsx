import { useState } from 'react'
import { Button, Modal } from '../ui'
import { CategorySelect, ChargeItemSelect, EquipmentPicker } from './pickers.jsx'
import {
  ALLOWED_BASES, BASIS_LABEL, ErrBox, Field, RULES, RULE_FIELDS, api, fieldError, parseApiError, todayStr,
} from './shared.jsx'

export default function ChargeMappingFormModal({ mapping, onClose, onSaved }) {
  const m = mapping
  const [f, setF] = useState({
    scope: m ? (m.equipment ? 'EQUIPMENT' : 'CATEGORY') : 'EQUIPMENT',
    equipment: m?.equipment || '', category: m?.category || '', charge_item: m?.charge_item || '',
    billing_rule: m?.billing_rule || 'HOURLY', basis: m?.basis || 'ALLOCATION',
    rate_override: m?.rate_override ?? '', minimum_billable_minutes: String(m?.minimum_billable_minutes ?? 0),
    grace_minutes: String(m?.grace_minutes ?? 0), rounding: m?.rounding || 'UP', daily_cap_amount: m?.daily_cap_amount ?? '',
    day_block_mode: m?.day_block_mode || 'CALENDAR_DAY', bundle_reference: m?.bundle_reference || '',
    effective_from: m?.effective_from || todayStr(), effective_to: m?.effective_to || '', notes: m?.notes || '',
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }))
  const show = (field) => RULE_FIELDS[f.billing_rule].includes(field)

  function setRule(e) {
    const rule = e.target.value
    setF((s) => ({ ...s, billing_rule: rule, basis: ALLOWED_BASES[rule].includes(s.basis) ? s.basis : ALLOWED_BASES[rule][0] }))
  }

  async function save() {
    setBusy(true)
    setError(null)
    const body = {
      equipment: f.scope === 'EQUIPMENT' ? f.equipment || null : null,
      category: f.scope === 'CATEGORY' ? f.category || null : null,
      charge_item: f.charge_item || null, billing_rule: f.billing_rule, basis: f.basis,
      effective_from: f.effective_from, effective_to: f.effective_to || null, notes: f.notes || null,
    }
    if (show('rate_override')) body.rate_override = f.rate_override === '' ? null : f.rate_override
    if (show('minimum_billable_minutes')) body.minimum_billable_minutes = Number(f.minimum_billable_minutes || 0)
    if (show('grace_minutes')) body.grace_minutes = Number(f.grace_minutes || 0)
    if (show('rounding')) body.rounding = f.rounding
    if (show('daily_cap_amount')) body.daily_cap_amount = f.daily_cap_amount === '' ? null : f.daily_cap_amount
    if (show('day_block_mode')) body.day_block_mode = f.day_block_mode
    if (show('bundle_reference')) body.bundle_reference = f.bundle_reference || null
    try {
      if (m) await api.put(`/charge-mappings/${m.public_id}/`, { ...body, row_version: m.row_version })
      else await api.post('/charge-mappings/', body)
      onSaved()
    } catch (err) {
      console.error('[billing] save charge mapping failed', err)
      setError(parseApiError(err))
    } finally {
      setBusy(false)
    }
  }

  const general = error && (error.message || '')
  return (
    <Modal title={m ? 'Edit charge mapping' : 'New charge mapping'} onClose={onClose} wide
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} onClick={save}>Save</Button></>}>
      {general ? <ErrBox error={general} /> : null}
      <Field label="Applies to" name="scope" as="select" value={f.scope} onChange={set('scope')}
        options={[{ value: 'EQUIPMENT', label: 'One piece of equipment' }, { value: 'CATEGORY', label: 'An equipment category (or group)' }]} />
      {f.scope === 'EQUIPMENT'
        ? <EquipmentPicker value={f.equipment} onChange={(v) => setF((s) => ({ ...s, equipment: v }))}
            selectedLabel={m?.equipment_label} required error={fieldError(error, 'equipment')} />
        : <CategorySelect value={f.category} onChange={(v) => setF((s) => ({ ...s, category: v }))} required
            error={fieldError(error, 'category')} />}
      <ChargeItemSelect value={f.charge_item} onChange={(v) => setF((s) => ({ ...s, charge_item: v }))} required
        error={fieldError(error, 'charge_item')} />
      <Field label="Billing rule" name="billing_rule" as="select" value={f.billing_rule} onChange={setRule} options={RULES}
        error={fieldError(error, 'billing_rule')} />
      <Field label="Charged from" name="basis" as="select" value={f.basis} onChange={set('basis')}
        options={ALLOWED_BASES[f.billing_rule].map((b) => ({ value: b, label: BASIS_LABEL[b] }))}
        error={fieldError(error, 'basis')} hint="Allocation charges when the equipment is released; usage log charges each finished session." />
      {show('rate_override') && (
        <Field label="Rate override (INR)" name="rate_override" as="input" type="number" min="0" step="0.01"
          value={f.rate_override} onChange={set('rate_override')} error={fieldError(error, 'rate_override')}
          hint="Leave empty to use the charge item's default rate" />)}
      {show('grace_minutes') && (
        <Field label="Grace (minutes)" name="grace_minutes" as="input" type="number" min="0" value={f.grace_minutes}
          onChange={set('grace_minutes')} error={fieldError(error, 'grace_minutes')}
          hint={f.billing_rule === 'DAILY' ? 'Used with 24-hour blocks: the remainder must exceed this to count' : 'No charge up to this many minutes'} />)}
      {show('minimum_billable_minutes') && (
        <Field label="Minimum billable (minutes)" name="minimum_billable_minutes" as="input" type="number" min="0"
          value={f.minimum_billable_minutes} onChange={set('minimum_billable_minutes')}
          error={fieldError(error, 'minimum_billable_minutes')} hint="Applies once the grace is exceeded" />)}
      {show('rounding') && (
        <Field label="Rounding" name="rounding" as="select" value={f.rounding} onChange={set('rounding')}
          options={[{ value: 'UP', label: 'Up to the next whole hour' }, { value: 'NEAREST', label: 'Nearest whole hour' }]} />)}
      {show('daily_cap_amount') && (
        <Field label="Daily cap (INR)" name="daily_cap_amount" as="input" type="number" min="0" step="0.01"
          value={f.daily_cap_amount} onChange={set('daily_cap_amount')} error={fieldError(error, 'daily_cap_amount')}
          hint="Maximum per calendar day touched. Leave empty for no cap." />)}
      {show('day_block_mode') && (
        <Field label="Day counting" name="day_block_mode" as="select" value={f.day_block_mode} onChange={set('day_block_mode')}
          options={[{ value: 'CALENDAR_DAY', label: 'Calendar days (any part of a day counts)' }, { value: 'BLOCK_24H', label: '24-hour blocks' }]} />)}
      {show('bundle_reference') && (
        <Field label="Package reference" name="bundle_reference" as="input" required value={f.bundle_reference}
          onChange={set('bundle_reference')} error={fieldError(error, 'bundle_reference')}
          hint="No separate charge is created; this reference is shown instead" />)}
      <Field label="Effective from" name="effective_from" as="input" type="date" required value={f.effective_from}
        onChange={set('effective_from')} error={fieldError(error, 'effective_from')} />
      <Field label="Effective to" name="effective_to" as="input" type="date" value={f.effective_to}
        onChange={set('effective_to')} error={fieldError(error, 'effective_to')} hint="Leave empty for no end date" />
      <Field label="Notes" name="notes" as="textarea" value={f.notes} onChange={set('notes')} error={fieldError(error, 'notes')} />
    </Modal>
  )
}
