import KpiCard from '../charts/KpiCard.jsx'
import LineChart from '../charts/LineChart.jsx'
import { FetchError, fmtDay, useFetch } from '../reports/shared.jsx'

export default function EquipmentPerformanceCard({ equipmentId }) {
  const res = useFetch(`/equipment/${equipmentId}/performance/`)
  const d = res.data
  const series = d?.series || []
  return (
    <section className="rp-card" style={{ marginTop: 16 }}>
      <h3>Performance{d ? ` · ${fmtDay(d.from)} to ${fmtDay(d.to)}` : ''}</h3>
      <FetchError error={res.error} />
      {res.loading && !d && <p className="rp-note">Loading…</p>}
      {d && !d.has_service_window && <p className="rp-empty">No performance data: this equipment has not been commissioned.</p>}
      {d?.has_service_window && (
        <>
          <div className="rp-perf">
            <KpiCard title="Availability" value={d.availability_percent} format="percent" />
            <KpiCard title="Utilization" value={d.utilization_percent} format="percent" />
            <KpiCard title="MTBF" value={d.mtbf_hours} format="hours" hint={d.failures ? `${d.failures} failure(s)` : 'No failures'} />
            <KpiCard title="MTTR" value={d.mttr_hours} format="hours" />
          </div>
          <LineChart title="Used and available hours per day" format="hours" height={150}
            labels={series.map((s) => s.date)}
            series={[{ name: 'Available', values: series.map((s) => Math.round((s.available_minutes / 60) * 100) / 100) },
              { name: 'Used', values: series.map((s) => Math.round((s.used_minutes / 60) * 100) / 100) },
              { name: 'Downtime', values: series.map((s) => Math.round((s.downtime_minutes / 60) * 100) / 100) }]} />
        </>
      )}
    </section>
  )
}
