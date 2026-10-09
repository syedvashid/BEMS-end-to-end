import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import EquipmentFormModal from '../components/EquipmentFormModal'
import { StageBadge, StateBadge } from '../components/EquipmentBadges'
import SimplePager from '../components/SimplePager'
import { Button, FormField, Table, useToast } from '../components/ui'
import { useFacility } from '../context/FacilityContext'
import useFetch from '../hooks/useFetch'
import {
  BLANK, CRITICALITY_OPTIONS, OWNERSHIP_OPTIONS, codeName, fmt, labelsRequest, openBlob, useMasterOptions,
} from '../utils/equipment'

const TABS = [
  { key: 'all', label: 'All', params: {} },
  { key: 'install', label: 'Awaiting installation', params: { lifecycle_stage: 'RECEIVED' } },
  { key: 'accept', label: 'Awaiting acceptance', params: { lifecycle_stage: 'INSTALLED' } },
  { key: 'service', label: 'In service', params: { operational_state: 'IN_SERVICE' } },
  { key: 'attention', label: 'Under maintenance / Out of service', params: { operational_state: 'UNDER_MAINTENANCE,OUT_OF_SERVICE' } },
]
const EMPTY = { search: '', category: '', equipment_model: '', department: '', location: '', ownership_type: '', criticality: '' }
const withBlank = (list) => [BLANK, ...list]

export default function EquipmentPage() {
  const { can } = useFacility()
  const navigate = useNavigate()
  const toast = useToast()
  const [tab, setTab] = useState('all')
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState(EMPTY)
  const [searchText, setSearchText] = useState('')
  const [selected, setSelected] = useState([])
  const [registering, setRegistering] = useState(false)

  const cats = useMasterOptions('/equipment-categories/', codeName)
  const models = useMasterOptions('/equipment-models/', (m) => `${m.model_name} (${m.model_number})`)
  const depts = useMasterOptions('/departments/', codeName)
  const locs = useMasterOptions('/locations/', codeName)

  const params = useMemo(() => {
    const p = { page, page_size: 20, ...TABS.find((t) => t.key === tab).params }
    Object.entries(filters).forEach(([k, v]) => { if (v) p[k] = v })
    return p
  }, [page, tab, filters])
  const list = useFetch('/equipment/', params)

  const setFilter = (k) => (e) => { setFilters((x) => ({ ...x, [k]: e.target.value })); setPage(1) }
  const toggle = (id) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))

  const printLabels = async () => {
    if (selected.length > 100) { toast.error('Select at most 100 items.'); return }
    try { await openBlob(labelsRequest(selected)) } catch { toast.error('Could not generate labels.') }
  }

  const rows = list.data?.results
  const columns = [
    {
      key: 'sel', header: '',
      render: (r) => <input type="checkbox" aria-label="Select" checked={selected.includes(r.public_id)}
        onClick={(e) => e.stopPropagation()} onChange={() => toggle(r.public_id)} />,
    },
    { key: 'asset_tag', header: 'Asset tag' },
    { key: 'name', header: 'Name' },
    { key: 'model', header: 'Model', render: (r) => `${r.equipment_model.model_name}${r.manufacturer ? ` · ${r.manufacturer.name}` : ''}` },
    { key: 'category', header: 'Category', render: (r) => fmt(r.category?.name) },
    { key: 'loc', header: 'Location', render: (r) => fmt(r.current_location?.name) },
    { key: 'stage', header: 'Stage', render: (r) => <StageBadge value={r.lifecycle_stage} /> },
    { key: 'state', header: 'State', render: (r) => <StateBadge value={r.operational_state} /> },
    { key: 'criticality', header: 'Criticality' },
  ]

  return (
    <section>
      <div className="page-head">
        <h2>Equipment</h2><span className="spacer" />
        {selected.length > 0 && <Button onClick={printLabels}>Print labels ({selected.length})</Button>}
        {can('equipment.add') && <Button onClick={() => setRegistering(true)} variant="primary">Register</Button>}
        {can('equipment.add') && <Button onClick={() => navigate('/equipment/bulk')}>Bulk add</Button>}
        {can('equipment.import') && <Button onClick={() => navigate('/equipment/import')}>Import</Button>}
      </div>

      <div className="eq-tabs">
        {TABS.map((t) => (
          <button key={t.key} type="button" className={`eq-tab${tab === t.key ? ' active' : ''}`}
            onClick={() => { setTab(t.key); setPage(1) }}>{t.label}</button>
        ))}
      </div>

      <div className="row">
        <FormField label="Search" name="search" value={searchText} onChange={(e) => setSearchText(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { setFilters((x) => ({ ...x, search: searchText.trim() })); setPage(1) } }}
          hint="Press Enter" />
        <FormField label="Category" name="category" as="select" options={cats.options} value={filters.category} onChange={setFilter('category')} />
        <FormField label="Model" name="equipment_model" as="select" options={models.options} value={filters.equipment_model} onChange={setFilter('equipment_model')} />
        <FormField label="Department" name="department" as="select" options={depts.options} value={filters.department} onChange={setFilter('department')} />
        <FormField label="Location (incl. sub-locations)" name="location" as="select" options={locs.options} value={filters.location} onChange={setFilter('location')} />
        <FormField label="Ownership" name="ownership_type" as="select" options={withBlank(OWNERSHIP_OPTIONS)} value={filters.ownership_type} onChange={setFilter('ownership_type')} />
        <FormField label="Criticality" name="criticality" as="select" options={withBlank(CRITICALITY_OPTIONS)} value={filters.criticality} onChange={setFilter('criticality')} />
      </div>

      {list.error && <div className="alert alert-danger">Could not load equipment.</div>}
      <Table columns={columns} rows={rows} loading={list.loading} empty="No equipment found."
        onRowClick={(r) => navigate(`/equipment/${r.public_id}`)} />
      <SimplePager page={page} count={list.data?.count} pageSize={20} onPage={setPage} />

      {registering && (
        <EquipmentFormModal onClose={() => setRegistering(false)}
          onDone={(eq) => { setRegistering(false); toast.success(`Registered ${eq.asset_tag}.`); list.reload() }} />
      )}
    </section>
  )
}
