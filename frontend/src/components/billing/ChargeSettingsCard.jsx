import { useEffect, useState } from 'react'
import { ErrBox, api, parseApiError, useFetch, usePermission } from './shared.jsx'

export default function ChargeSettingsCard() {
  const canConfigure = usePermission('charge.configure')
  const { data, reload } = useFetch('/charge-settings/')
  const [value, setValue] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  useEffect(() => { if (data) setValue(!!data.auto_approve) }, [data])

  async function toggle(e) {
    const next = e.target.checked
    setBusy(true)
    setError(null)
    try {
      await api.put('/charge-settings/', { auto_approve: next })
      setValue(next)
      reload()
    } catch (err) {
      console.error('[billing] save settings failed', err)
      setError(parseApiError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <h3>Charge settings</h3>
      <ErrBox error={error} />
      <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <input type="checkbox" checked={value} disabled={!canConfigure || busy} onChange={toggle} />
        Approve new charge records automatically
      </label>
      <p style={{ opacity: 0.7 }}>
        When off, new records wait in Pending review until finance approves them.
      </p>
    </div>
  )
}
