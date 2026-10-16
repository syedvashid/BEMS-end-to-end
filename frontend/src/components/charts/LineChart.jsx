import { PALETTE, valueFormatter } from './format.js'

// labels: [x labels]; series: [{name, values:[number|null]}]. Null values break the line.
export default function LineChart({ labels = [], series = [], format = 'number', height = 220, title = 'Line chart' }) {
  const all = series.flatMap((s) => s.values).filter((v) => v !== null && v !== undefined).map(Number)
  if (labels.length < 2 || !all.length) return <p className="rp-empty">No data to show.</p>
  const fmt = valueFormatter(format)
  const w = 640; const pad = { l: 56, r: 12, t: 12, b: 26 }
  const min = Math.min(0, ...all); const max = Math.max(...all, 1); const span = max - min || 1
  const X = (i) => pad.l + (i * (w - pad.l - pad.r)) / (labels.length - 1)
  const Y = (v) => pad.t + (1 - (Number(v) - min) / span) * (height - pad.t - pad.b)
  const ticks = [0, 1, 2, 3].map((i) => min + (span * i) / 3)
  const at = [0, Math.floor((labels.length - 1) / 2), labels.length - 1]
  const pathOf = (values) => {
    let d = ''; let pen = false
    values.forEach((v, i) => {
      if (v === null || v === undefined) { pen = false; return }
      d += `${pen ? 'L' : 'M'}${X(i).toFixed(1)},${Y(v).toFixed(1)} `; pen = true
    })
    return d
  }
  return (
    <div>
      <svg className="rp-svg" viewBox={`0 0 ${w} ${height}`} width="100%" role="img" aria-label={title}>
        <title>{title}</title>
        {ticks.map((t) => (
          <g key={t}>
            <line className="rp-grid-line" x1={pad.l} x2={w - pad.r} y1={Y(t)} y2={Y(t)} />
            <text x={pad.l - 6} y={Y(t) + 4} textAnchor="end">{fmt(t)}</text>
          </g>
        ))}
        {at.map((i) => <text key={i} x={X(i)} y={height - 8} textAnchor={i === 0 ? 'start' : i === labels.length - 1 ? 'end' : 'middle'}>{labels[i]}</text>)}
        {series.map((s, si) => (
          <g key={s.name}>
            <path d={pathOf(s.values)} fill="none" stroke={PALETTE[si % PALETTE.length]} strokeWidth="2" />
            {s.values.map((v, i) => (v === null || v === undefined ? null : (
              <circle key={i} cx={X(i)} cy={Y(v)} r="3" fill={PALETTE[si % PALETTE.length]}>
                <title>{`${s.name} · ${labels[i]}: ${fmt(v)}`}</title>
              </circle>
            )))}
          </g>
        ))}
      </svg>
      {series.length > 1 && (
        <div className="rp-legend">
          {series.map((s, i) => <span key={s.name}><i style={{ background: PALETTE[i % PALETTE.length] }} />{s.name}</span>)}
        </div>
      )}
    </div>
  )
}
