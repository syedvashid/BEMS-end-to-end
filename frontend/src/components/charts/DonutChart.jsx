import { PALETTE, valueFormatter } from './format.js'

export default function DonutChart({ items = [], format = 'number', title = 'Donut chart' }) {
  const data = items.filter((i) => Number(i.value) > 0)
  if (!data.length) return <p className="rp-empty">No data to show.</p>
  const fmt = valueFormatter(format)
  const total = data.reduce((s, i) => s + Number(i.value), 0)
  const R = 70; const C = 2 * Math.PI * R
  let offset = 0
  return (
    <div className="rp-donut">
      <svg className="rp-svg" viewBox="0 0 200 200" width="180" height="180" role="img" aria-label={title}>
        <title>{title}</title>
        <g transform="rotate(-90 100 100)">
          {data.map((it, i) => {
            const len = (Number(it.value) / total) * C
            const el = (
              <circle key={`${it.label}-${i}`} cx="100" cy="100" r={R} fill="none" stroke={PALETTE[i % PALETTE.length]}
                strokeWidth="30" strokeDasharray={`${len} ${C - len}`} strokeDashoffset={-offset}>
                <title>{`${it.label}: ${fmt(it.value)} (${((Number(it.value) / total) * 100).toFixed(1)}%)`}</title>
              </circle>
            )
            offset += len
            return el
          })}
        </g>
        <text x="100" y="104" textAnchor="middle" style={{ fontSize: 18, fill: 'var(--color-text)' }}>{fmt(total)}</text>
      </svg>
      <div className="rp-legend" style={{ flexDirection: 'column' }}>
        {data.map((it, i) => (
          <span key={`${it.label}-${i}`}><i style={{ background: PALETTE[i % PALETTE.length] }} />{String(it.label).replace(/_/g, ' ')}: {fmt(it.value)}</span>
        ))}
      </div>
    </div>
  )
}
