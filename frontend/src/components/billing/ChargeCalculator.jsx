import { useState } from 'react'
import { Button } from '../ui'
import { ErrBox, Field, RULES, api, inr, parseApiError, qty } from './shared.jsx'

const toIso = (v) => (v ? new Date(v).toISOString() : null)

// Inline calculator (POST /charges/calculator/): shows quantity, amount and the calculation steps.
export default function ChargeCalculator({ initial }) {
  const [f, setF] = useState({
    billing_rule: 'HOURLY', unit_rate: '500', grace_minutes: '10', minimum_billable_minutes: '60', rounding: 'UP',
    daily_cap_amount: '', day_block_mode: 'CALENDAR_DAY', start: '', end: '', duration_minutes: '', ...initial,
  })
  const [res, setRes] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }))

  async function run() {
    setBusy(true)
    setError(null)
    setRes(null)
    const body = {
      billing_rule: f.billing_rule, unit_rate: f.unit_rate || '0', grace_minutes: Number(f.grace_minutes || 0),
      minimum_billable_minutes: Number(f.minimum_billable_minutes || 0), rounding: f.rounding,
      daily_cap_amount: f.daily_cap_amount || null, day_block_mode: f.day_block_mode,
    }
    if (f.start && f.end) { body.start = toIso(f.start); body.end = toIso(f.end) }
    else if (f.duration_minutes !== '') body.duration_minutes = Number(f.duration_minutes)
    try {
      const r = await api.post('/charges/calculator/', body)
      setRes(r.data)
    } catch (err) {
      console.error('[billing] calculator failed', err)
      setError(parseApiError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <h3>Calculator</h3>
      <ErrBox error={error} />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 12 }}>
        <Field label="Billing rule" name="calc_rule" as="select" value={f.billing_rule} onChange={set('billing_rule')}
          options={RULES} />
        <Field label="Unit rate (INR)" name="calc_rate" as="input" type="number" min="0" step="0.01" value={f.unit_rate} onChange={set('unit_rate')} />
        <Field label="Grace (min)" name="calc_grace" as="input" type="number" min="0" value={f.grace_minutes} onChange={set('grace_minutes')} />
        <Field label="Minimum (min)" name="calc_min" as="input" type="number" min="0" value={f.minimum_billable_minutes} onChange={set('minimum_billable_minutes')} />
        <Field label="Rounding" name="calc_round" as="select" value={f.rounding} onChange={set('rounding')}
          options={[{ value: 'UP', label: 'Up' }, { value: 'NEAREST', label: 'Nearest' }]} />
        <Field label="Daily cap (INR)" name="calc_cap" as="input" type="number" min="0" step="0.01" value={f.daily_cap_amount} onChange={set('daily_cap_amount')} />
        <Field label="Day mode" name="calc_mode" as="select" value={f.day_block_mode} onChange={set('day_block_mode')}
          options={[{ value: 'CALENDAR_DAY', label: 'Calendar day' }, { value: 'BLOCK_24H', label: '24-hour block' }]} />
        <Field label="Start" name="calc_start" as="input" type="datetime-local" value={f.start} onChange={set('start')} />
        <Field label="End" name="calc_end" as="input" type="datetime-local" value={f.end} onChange={set('end')} />
        <Field label="or duration (min)" name="calc_dur" as="input" type="number" min="0" value={f.duration_minutes} onChange={set('duration_minutes')}
          hint="Used when start and end are empty" />
      </div>
      <Button variant="primary" loading={busy} onClick={run}>Calculate</Button>
      {res && (
        <div style={{ marginTop: 12 }}>
          <strong>{res.reason ? `No charge (${res.reason.replace('_', ' ').toLowerCase()})` : `${qty(res.quantity)} ${res.unit_label}, ${inr(res.amount)}`}</strong>
          <ol>{(res.steps || []).map((s, i) => <li key={i}>{s}</li>)}</ol>
        </div>
      )}
    </div>
  )
}
