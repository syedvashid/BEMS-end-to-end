import { shorten } from './format.js'

// rows: [labels]; columns: [labels]; values[r][c]: number | null; scale 0..100 by default.
export default function Heatmap({ rows = [], columns = [], values = [], unit = '%', min = 0, max = 100, title = 'Heatmap' }) {
  if (!rows.length || !columns.length) return <p className="rp-empty">No data to show.</p>
  const cell = Math.max(14, Math.min(30, Math.floor(560 / columns.length)))
  const labelW = 150; const top = 22; const rowH = 20
  const w = labelW + columns.length * cell + 8; const h = top + rows.length * rowH + 8
  const step = Math.max(1, Math.ceil(columns.length / 10))
  const shade = (v) => {
    if (v === null || v === undefined) return 'var(--rp-heat-empty)'
    const pct = Math.round(Math.max(0, Math.min(1, (Number(v) - min) / (max - min || 1))) * 100)
    return `color-mix(in srgb, var(--rp-heat) ${Math.max(pct, 6)}%, var(--rp-heat-empty))`
  }
  return (
    <div className="rp-scroll">
      <svg className="rp-svg" viewBox={`0 0 ${w} ${h}`} style={{ minWidth: Math.min(w, 700) }} width="100%" role="img" aria-label={title}>
        <title>{title}</title>
        {columns.map((c, ci) => (ci % step === 0
          ? <text key={c} x={labelW + ci * cell + cell / 2} y={14} textAnchor="middle">{String(c).slice(5)}</text> : null))}
        {rows.map((r, ri) => (
          <g key={`${r}-${ri}`} transform={`translate(0 ${top + ri * rowH})`}>
            <text x={labelW - 6} y={14} textAnchor="end">{shorten(r, 22)}</text>
            {columns.map((c, ci) => {
              const v = values[ri]?.[ci]
              return (
                <rect key={c} x={labelW + ci * cell} y={1} width={cell - 1} height={rowH - 2} rx={2} style={{ fill: shade(v) }}>
                  <title>{`${r} · ${c}: ${v === null || v === undefined ? 'no data' : `${v}${unit}`}`}</title>
                </rect>
              )
            })}
          </g>
        ))}
      </svg>
    </div>
  )
}
