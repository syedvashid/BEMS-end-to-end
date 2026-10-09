import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, FormField, Table, useToast } from '../components/ui'
import SimplePager from '../components/SimplePager'
import { PriorityPill, StatusPill } from '../components/WorkOrderBadges'
import { api } from '../api/client'
import { useFacility } from '../context/FacilityContext'
import useFetch from '../hooks/useFetch'
import { apiError, errorText } from '../utils/maintenance'
import '../styles/maintenance.css'

export default function PmDuePage() {
  const { can } = useFacility()
  const toast = useToast()
  const [within, setWithin] = useState('30')
  const [page, setPage] = useState(1)
  const res = useFetch('/maintenance-plans/due/', { within_days: within || 30, page, page_size: 20 })
  const generate = async (plan) => {
    try {
      const r = await api.post(`/maintenance-plans/${plan.public_id}/generate-work-order/`, {})
      toast.success(`Work order ${r.data.wo_number} created.`)
      res.reload()
    } catch (e) { toast.error(errorText(apiError(e))) }
  }
  return (
    <section>
      <div className="page-head"><h2>PM due &amp; overdue</h2></div>
      <div className="mt-toolbar">
        <FormField label="Due within (days)" name="within" type="number" value={within} onChange={(e) => { setPage(1); setWithin(e.target.value) }} />
      </div>
      <Table rows={res.data?.results} loading={res.loading} empty="Nothing due in this period."
        columns={[
          { key: 'equipment', header: 'Equipment', render: (p) => <Link to={`/equipment/${p.equipment.public_id}`}>{p.equipment.asset_tag} · {p.equipment.name}</Link> },
          { key: 'name', header: 'Plan' },
          { key: 'priority', header: 'Priority', render: (p) => <PriorityPill priority={p.priority} /> },
          { key: 'next_due_date', header: 'Due', render: (p) => (p.is_overdue ? <strong className="mt-low mt-pill">{p.next_due_date} · {p.days_overdue} d overdue</strong> : `${p.next_due_date} · in ${p.days_left} d`) },
          { key: 'wo', header: 'Work order', render: (p) => (p.open_work_order
            ? <><Link to={`/work-orders/${p.open_work_order.public_id}`}>{p.open_work_order.wo_number}</Link> <StatusPill status={p.open_work_order.status} /></>
            : (can('work_order.change') ? <Button size="sm" onClick={() => generate(p)}>Generate now</Button> : '—')) },
        ]} />
      <SimplePager page={page} count={res.data?.count} pageSize={20} onPage={setPage} />
    </section>
  )
}
