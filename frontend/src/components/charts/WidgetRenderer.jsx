import { fmtNum } from '../finance/shared.jsx'
import BarChart from './BarChart.jsx'
import DonutChart from './DonutChart.jsx'
import Heatmap from './Heatmap.jsx'
import KpiCard from './KpiCard.jsx'
import LineChart from './LineChart.jsx'

function WidgetTable({ data }) {
  const cols = data?.columns || []; const rows = data?.rows || []
  if (!rows.length) return <p className="rp-empty">No data to show.</p>
  return (
    <div className="rp-scroll">
      <table className="rp-table">
        <thead><tr>{cols.map((c) => <th key={c.key}>{c.label}</th>)}</tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>{cols.map((c) => <td key={c.key}>{typeof r[c.key] === 'number' ? fmtNum(r[c.key], 2) : (r[c.key] ?? '—')}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export const isWide = (w) => w.type === 'heatmap' || w.type === 'table'

export default function WidgetRenderer({ widget }) {
  const { type, title, data = {} } = widget
  if (type === 'kpi') return <KpiCard title={title} value={data.value} format={data.format} hint={data.hint} />
  let body
  switch (type) {
    case 'bar': body = <BarChart items={data.items} horizontal={data.horizontal} format={data.format} title={title} />; break
    case 'donut': body = <DonutChart items={data.items} format={data.format} title={title} />; break
    case 'line': body = <LineChart labels={data.labels} series={data.series} format={data.format} title={title} />; break
    case 'heatmap': body = <Heatmap rows={data.rows} columns={data.columns} values={data.values} unit={data.unit} title={title} />; break
    case 'table': body = <WidgetTable data={data} />; break
    default: body = <p className="rp-empty">Unsupported widget.</p>
  }
  return (
    <section className={`rp-card${isWide(widget) ? ' wide' : ''}`}>
      <h3>{title}</h3>
      {body}
    </section>
  )
}
