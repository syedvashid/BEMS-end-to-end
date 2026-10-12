import { useState } from 'react'
import { StateBadge } from '../components/EquipmentBadges'
import SimplePager from '../components/SimplePager'
import {
  CalChip, EqLink, FormField, Table, fmtDateTime, useFetch, useLocationOptions, useOptions, withBlank,
} from '../components/allocation/shared'
import '../styles/maintenance.css'
import '../styles/allocation.css'

export default function BedsidePage() {
  const [location, setLocation] = useState('')
  const [category, setCategory] = useState('')
  const [page, setPage] = useState(1)
  const locs = useLocationOptions()
  const cats = useOptions('/equipment-categories/', (c) => ({ value: c.public_id, label: c.name }))
  const res = useFetch('/equipment/bedside/', { location, ...(category ? { category } : {}), page, page_size: 20 }, !!location)
  return (
    <section>
      <div className="page-head"><h2>Bedside view</h2></div>
      <div className="mt-toolbar">
        <FormField label="Location" name="location" as="select" options={withBlank(locs, 'Select a location…')} value={location} onChange={(e) => { setPage(1); setLocation(e.target.value) }} />
        <FormField label="Category" name="category" as="select" options={withBlank(cats, 'All')} value={category} onChange={(e) => { setPage(1); setCategory(e.target.value) }} />
      </div>
      {!location ? <p className="muted">Pick a ward, room or bed to see the equipment there.</p> : (
        <>
          <Table rows={res.data?.results} loading={res.loading} empty="No equipment in this location." columns={[
            { key: 'eq', header: 'Equipment', render: (e) => <EqLink e={e} /> },
            { key: 'cat', header: 'Category', render: (e) => e.category.name },
            { key: 'loc', header: 'Location', render: (e) => e.current_location?.name || '—' },
            { key: 'st', header: 'State', render: (e) => <StateBadge value={e.operational_state} /> },
            { key: 'cal', header: 'Calibration', render: (e) => <CalChip status={e.calibration_status} /> },
            { key: 'al', header: 'Allocated to', render: (e) => (e.allocation
              ? `${e.allocation.department?.name || '—'}${e.allocation.patient_reference ? ` · ${e.allocation.patient_reference}` : ''} · since ${fmtDateTime(e.allocation.since)}`
              : 'Free') },
          ]} />
          <SimplePager page={page} count={res.data?.count} pageSize={20} onPage={setPage} />
        </>
      )}
    </section>
  )
}