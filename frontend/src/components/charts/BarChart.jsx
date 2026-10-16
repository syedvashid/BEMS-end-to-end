import { shorten, valueFormatter } from './format.js'

// items: [{label, value}]. Hover a bar to see its exact value (native SVG tooltip).
export default function BarChart({ items = [], horizontal = false, format = 'number', title = 'Bar chart' }) {
  if (!items.length) return <p className="rp-empty">No data to show.</p>
  const fmt = valueFormatter(format)
  const vals = items.map((i) => Number(i.value) || 0)
  const max = Math.max(...vals, 1)

  if (horizontal) {
    const rowH = 26; const labelW = 150; const w = 640; const barW = w - labelW - 90
    const h = items.length * rowH + 8
    return (
      <svg className="rp-svg" viewBox={`0 0 ${w} ${h}`} width="100%" role="img" aria-label={title}>
        <title>{title}</title>
        {items.map((it, i) => {
          const len = (vals[i] / max) * barW
          return (
            <g key={`${it.label}-${i}`} transform={`translate(0 ${i * rowH + 4})`}>
              <title>{`${it.label}: ${fmt(it.value)}`}</title>
              <text x={labelW - 6} y={14} textAnchor="end">{shorten(it.label, 24)}</text>
              <rect x={labelW} y={2} width={Math.max(len, 1)} height={16} rx={2} fill="var(--rp-c1)" />
              <text className="rp-value" x={labelW + len + 6} y={14}>{fmt(it.value)}</text>
            </g>
          )
        })}
      </svg>
    )
  }

  const w = Math.max(360, items.length * 64); const h = 230; const pad = { l: 8, r: 8, t: 20, b: 44 }
  const slot = (w - pad.l - pad.r) / items.length; const bw = Math.min(40, slot * 0.7)
  return (
    <div className="rp-scroll">
      <svg className="rp-svg" viewBox={`0 0 ${w} ${h}`} style={{ minWidth: w }} width="100%" role="img" aria-label={title}>
        <title>{title}</title>
        <line className="rp-grid-line" x1={pad.l} x2={w - pad.r} y1={h - pad.b} y2={h - pad.b} />
        {items.map((it, i) => {
          const bh = (vals[i] / max) * (h - pad.t - pad.b)
          const x = pad.l + i * slot + (slot - bw) / 2
          return (
            <g key={`${it.label}-${i}`}>
              <title>{`${it.label}: ${fmt(it.value)}`}</title>
              <rect x={x} y={h - pad.b - bh} width={bw} height={Math.max(bh, 1)} rx={2} fill="var(--rp-c1)" />
              <text className="rp-value" x={x + bw / 2} y={h - pad.b - bh - 4} textAnchor="middle">{fmt(it.value)}</text>
              <text x={x + bw / 2} y={h - pad.b + 14} textAnchor="middle">{shorten(it.label, 10)}</text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}
