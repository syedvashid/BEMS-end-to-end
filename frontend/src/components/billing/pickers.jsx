import { useEffect, useMemo, useState } from 'react'
import { Field, api, useFetch } from './shared.jsx'

// Equipment search + select. value is the equipment public_id. selectedLabel keeps the current value visible while editing.
export function EquipmentPicker({ value, onChange, selectedLabel, error, label = 'Equipment', required, hint }) {
  const [term, setTerm] = useState('')
  const [opts, setOpts] = useState([])
  useEffect(() => {
    const t = setTimeout(async () => {
      try {
        const r = await api.get('/equipment/', { params: { search: term || undefined, page_size: 20 } })
        setOpts((r.data.results || []).map((e) => ({ value: e.public_id, label: `${e.asset_tag} - ${e.name}` })))
      } catch (err) {
        console.error('[billing] equipment search failed', err)
      }
    }, 300)
    return () => clearTimeout(t)
  }, [term])
  const options = useMemo(() => {
    const list = [{ value: '', label: 'Select equipment' }, ...opts]
    if (value && !opts.some((o) => o.value === value)) list.splice(1, 0, { value, label: selectedLabel || 'Selected equipment' })
    return list
  }, [opts, value, selectedLabel])
  return (
    <div>
      <Field label={`Search ${label.toLowerCase()}`} name="equipment_search" as="input" value={term}
        onChange={(e) => setTerm(e.target.value)} hint={hint || 'Type an asset tag or name'} />
      <Field label={label} name="equipment" as="select" value={value || ''} options={options} required={required}
        error={error} onChange={(e) => onChange(e.target.value)} />
    </div>
  )
}

function useOptions(path, labelOf) {
  const { data } = useFetch(`${path}?page_size=100`)
  return useMemo(() => (data?.results || []).map((r) => ({ value: r.public_id, label: labelOf(r) })), [data])
}

export function CategorySelect({ value, onChange, error, required, label = 'Equipment category' }) {
  const opts = useOptions('/equipment-categories/', (c) => `${c.name}${c.parent_category ? '' : ' (group)'}`)
  return (
    <Field label={label} name="category" as="select" value={value || ''} required={required} error={error}
      options={[{ value: '', label: 'Select category' }, ...opts]} onChange={(e) => onChange(e.target.value)} />
  )
}

export function ChargeItemSelect({ value, onChange, error, required }) {
  const opts = useOptions('/charge-items/', (c) => `${c.item_code} - ${c.name}`)
  return (
    <Field label="Charge item" name="charge_item" as="select" value={value || ''} required={required} error={error}
      options={[{ value: '', label: 'Select charge item' }, ...opts]} onChange={(e) => onChange(e.target.value)} />
  )
}

export function DepartmentSelect({ value, onChange, label = 'Department' }) {
  const opts = useOptions('/departments/', (d) => d.name)
  return (
    <Field label={label} name="department" as="select" value={value || ''}
      options={[{ value: '', label: 'All' }, ...opts]} onChange={(e) => onChange(e.target.value)} />
  )
}
