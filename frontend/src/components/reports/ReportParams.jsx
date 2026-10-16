import { FormField } from '../ui'
import { EquipmentPicker } from '../finance/shared.jsx'
import { useFetch } from './shared.jsx'

// Endpoint and label for each reference type (existing master list endpoints).
const REF = {
  department: ['/departments/', (r) => r.name],
  category: ['/equipment-categories/', (r) => r.name],
  location: ['/locations/', (r) => r.name],
  vendor: ['/vendors/', (r) => r.name],
  funding_source: ['/funding-sources/', (r) => r.name],
  part: ['/spare-parts/', (r) => `${r.part_code} · ${r.name}`],
  verification: ['/verifications/', (r) => `${r.verification_number} · ${r.title}`],
}

function RefSelect({ param, value, onChange, error }) {
  const [path, label] = REF[param.entity] || ['/departments/', (r) => r.name]
  const res = useFetch(path, { page_size: 100 })
  const options = [{ value: '', label: param.required ? 'Select…' : 'All' },
    ...(res.data?.results || []).map((r) => ({ value: r.public_id, label: label(r) }))]
  return <FormField label={param.label} name={`p_${param.name}`} as="select" required={param.required} value={value || ''} error={error}
    options={options} onChange={(e) => onChange(e.target.value)} />
}

const humanise = (s) => String(s).replace(/_/g, ' ')

export default function ReportParams({ spec = [], values, onChange, errors = {} }) {
  const err = (n) => (Array.isArray(errors[n]) ? errors[n].join(' ') : errors[n])
  return (
    <div className="rp-params">
      {spec.map((p) => {
        const common = { label: p.label, name: `p_${p.name}`, required: p.required, error: err(p.name), value: values[p.name] ?? '' }
        const set = (e) => onChange(p.name, e.target.value)
        switch (p.type) {
          case 'date': return <FormField key={p.name} {...common} type="date" onChange={set} />
          case 'month': return <FormField key={p.name} {...common} type="month" value={String(values[p.name] ?? '').slice(0, 7)} onChange={set} />
          case 'integer': return <FormField key={p.name} {...common} type="number" min={p.min ?? undefined} max={p.max ?? undefined} onChange={set} />
          case 'boolean':
            return <FormField key={p.name} {...common} as="select" onChange={set}
              options={[{ value: '', label: 'No' }, { value: 'true', label: 'Yes' }]} />
          case 'choice':
            return <FormField key={p.name} {...common} as="select" onChange={set}
              options={[{ value: '', label: p.required ? 'Select…' : 'All' }, ...p.choices.map((c) => ({ value: c, label: humanise(c) }))]} />
          case 'ref':
            if (p.entity === 'equipment') {
              return <EquipmentPicker key={p.name} label={p.label} required={p.required} value={values[p.name]} error={err(p.name)}
                onChange={(v) => onChange(p.name, v)} />
            }
            return <RefSelect key={p.name} param={p} value={values[p.name]} error={err(p.name)} onChange={(v) => onChange(p.name, v)} />
          default: return <FormField key={p.name} {...common} onChange={set} />
        }
      })}
    </div>
  )
}
