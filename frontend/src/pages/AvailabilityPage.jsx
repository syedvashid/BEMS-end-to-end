import { useState } from 'react'
import { StateBadge } from '../components/EquipmentBadges'
import SimplePager from '../components/SimplePager'
import AllocateDialog from '../components/allocation/AllocateDialog'
import {
  Button, CalChip, EqLink, FormField, Items, Table, clean, eqValue, toIso, useDepartmentOptions, useFetch,
  useLocationOptions, useOptions, withBlank,
} from '../components/allocation/shared'
import { useToast } from '../components/ui'
import { useFacility } from '../context/FacilityContext'
import '../styles/maintenance.css'
import '../styles/allocation.css'

export default function AvailabilityPage() {
  const { can } = useFacility()
  const toast = useToast()
  const [f, setF] = useState({ category: '', location: '', department: '', from: '', to: '' })
  const [page, setPage] = useState(1)
  const [alloc, setAlloc] = useState(null)
  const cats = useOptions('/equipment-categories/', (c) => ({ value: c.public_id, label: c.name }))
  const locs = useLocationOptions()
  const depts = useDepartmentOptions()
  const set = (k) => (e) => { setPage(1); setF((s) => ({ ...s, [k]: e.target.value })) }
  const res = useFetch('/equipment/available/', clean({
    category: f.category, location: f.location, department: f.department,
    from: toIso(f.from), to: toIso(f.to), page, page_size: 20,
  }))
  return (
    <section>
      <div className="page-head"><h2>Equipment availability</h2></div>
      <div className="mt-toolbar">
        <FormField label="Category" name="category" as="select" options={withBlank(cats, 'All')} value={f.category} onChange={set('category')} />
        <FormField label="Location" name="location" as="select" options={withBlank(locs, 'All')} value={f.location} onChange={set('location')} />
        <FormField label="Department" name="department" as="select" options={withBlank(depts, 'All')} value={f.department} onChange={set('department')} />
        <FormField label="From" name="from" type="datetime-local" value={f.from} onChange={set('from')} />
        <FormField label="To" name="to" type="datetime-local" value={f.to} onChange={set('to')} />
      </div>
      <Table rows={res.data?.results} loading={res.loading} empty="No equipment is available for these filters." columns={[
        { key: 'eq', header: 'Equipment', render: (e) => <EqLink e={e} /> },
        { key: 'cat', header: 'Category', render: (e) => e.category.name },
        { key: 'loc', header: 'Location', render: (e) => e.current_location?.name || '—' },
        { key: 'st', header: 'State', render: (e) => <StateBadge value={e.operational_state} /> },
        { key: 'cal', header: 'Calibration', render: (e) => <CalChip status={e.calibration_status} /> },
        { key: 'w', header: 'Warnings', render: (e) => <Items items={e.warnings} /> },
        { key: 'a', header: '', render: (e) => (can('allocation.assign') ? <Button size="sm" variant="primary" onClick={() => setAlloc(e)}>Allocate</Button> : null) },
      ]} />
      <SimplePager page={page} count={res.data?.count} pageSize={20} onPage={setPage} />
      {alloc && <AllocateDialog equipment={eqValue(alloc)} onClose={() => setAlloc(null)}
        onDone={() => { setAlloc(null); toast.success('Equipment allocated.'); res.reload() }} />}
    </section>
  )
}