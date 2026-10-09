import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { FormField } from './ui'

// value: { public_id, label } | null.  Searches /equipment/?summary=true (commissioned units only).
export default function EquipmentPicker({ value, onChange, error, label = 'Equipment', required, excludeId }) {
  const [q, setQ] = useState('')
  const [rows, setRows] = useState([])
  useEffect(() => {
    if (q.trim().length < 2) { setRows([]); return undefined }
    let alive = true
    const t = setTimeout(async () => {
      try {
        const res = await api.get('/equipment/', { params: { summary: 'true', search: q.trim(), page_size: 20 } })
        if (alive) setRows((res.data.results || []).filter((e) => e.lifecycle_stage === 'COMMISSIONED' && e.public_id !== excludeId))
      } catch { if (alive) setRows([]) }
    }, 250)
    return () => { alive = false; clearTimeout(t) }
  }, [q, excludeId])

  if (value) {
    return (
      <FormField label={label} name="equipment_display" required={required} error={error}
        value={value.label} onChange={() => {}} readOnly
        hint={<button type="button" className="link" onClick={() => { onChange(null); setQ('') }}>Change</button>} />
    )
  }
  return (
    <div>
      <FormField label={label} name="equipment_search" required={required} error={error}
        value={q} onChange={(e) => setQ(e.target.value)} hint="Type at least 2 letters of the name or asset tag" />
      {rows.length > 0 && (
        <ul className="mt-list">
          {rows.map((e) => (
            <li key={e.public_id}>
              <button type="button" className="link"
                onClick={() => { onChange({ public_id: e.public_id, label: `${e.asset_tag} · ${e.name}` }); setRows([]) }}>
                {e.asset_tag} · {e.name}{e.current_location ? ` (${e.current_location.name})` : ''}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
