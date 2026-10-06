import { useMemo, useState } from 'react'
import { api } from '../api/client'
import ConfirmDeleteModal from '../components/ConfirmDeleteModal'
import EquipmentCategoryFormModal from '../components/EquipmentCategoryFormModal'
import PermissionGate from '../components/PermissionGate'
import RiskBadge from '../components/RiskBadge'
import { Button, FormError, FormField, Pagination, Table, useToast } from '../components/ui'
import { useFacility } from '../context/FacilityContext'
import useFetch from '../hooks/useFetch'
import useSubmit from '../hooks/useSubmit'
import { dash, opts } from '../utils/formHelpers'

const PAGE = 100   // grouping needs the whole set on one page

export default function EquipmentCategoriesPage() {
  const { can } = useFacility()
  const toast = useToast()
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState({ search: '', risk_class: '' })
  const [applied, setApplied] = useState(filters)
  const [editing, setEditing] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const list = useFetch('/equipment-categories/', { page, page_size: PAGE, ...applied })
  const defaults = useSubmit()

  // Group rows: each top-level category followed by its children (orphans in a filtered result stay top-level).
  const rows = useMemo(() => {
    const items = list.data?.results ?? []
    const ids = new Set(items.map((c) => c.public_id))
    const byParent = {}
    items.forEach((c) => { if (c.parent_category && ids.has(c.parent_category)) (byParent[c.parent_category] ||= []).push(c) })
    const out = []
    items.filter((c) => !c.parent_category || !ids.has(c.parent_category)).forEach((c) => {
      out.push({ ...c, _child: false })
      ;(byParent[c.public_id] || []).forEach((k) => out.push({ ...k, _child: true }))
    })
    return out
  }, [list.data])

  const loadDefaults = async () => {
    const res = await defaults.run(() => api.post('/equipment-categories/load-defaults/', {}))
    if (res) {
      toast.success(res.data.created === 0 ? 'All default categories already exist.' : `${res.data.created} categories created.`)
      list.reload()
    }
  }

  const columns = [
    { key: 'name', header: 'Name', render: (r) => <span className={r._child ? 'cat-child' : 'cat-group'}>{r.name}</span> },
    { key: 'code', header: 'Code' },
    { key: 'risk_class', header: 'Risk', render: (r) => <RiskBadge value={r.risk_class} /> },
    { key: 'default_pm_interval_days', header: 'PM (days)', render: (r) => dash(r.default_pm_interval_days) },
    { key: 'default_calibration_interval_days', header: 'Calibration (days)', render: (r) => dash(r.default_calibration_interval_days) },
    {
      key: 'actions', header: '', className: 'actions',
      render: (r) => (
        <div className="row">
          {can('equipment_category.change') && <Button size="sm" onClick={() => setEditing(r)}>Edit</Button>}
          {can('equipment_category.delete') && <Button size="sm" variant="danger" onClick={() => setDeleting(r)}>Delete</Button>}
        </div>
      ),
    },
  ]

  return (
    <>
      <div className="page-head">
        <h1>Equipment Categories</h1><span className="spacer" />
        <PermissionGate code="equipment_category.add">
          <Button onClick={loadDefaults} loading={defaults.busy}>Load default categories</Button>
          <Button variant="primary" onClick={() => setEditing('new')}>New category</Button>
        </PermissionGate>
      </div>
      <FormError error={defaults.error} />
      <form className="filters" onSubmit={(e) => { e.preventDefault(); setPage(1); setApplied(filters) }}>
        <FormField label="Search" name="f_search" value={filters.search} onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))} />
        <FormField label="Risk" name="f_risk" as="select" options={opts(['LOW', 'MEDIUM', 'HIGH'], 'All')} value={filters.risk_class} onChange={(e) => setFilters((f) => ({ ...f, risk_class: e.target.value }))} />
        <Button type="submit">Search</Button>
      </form>
      {list.error && <div className="alert alert-danger">{list.error.message}</div>}
      <Table columns={columns} rows={rows} loading={list.loading} />
      <Pagination page={page} pageSize={PAGE} count={list.data?.count ?? 0} onPageChange={setPage} />

      {editing && (
        <EquipmentCategoryFormModal
          category={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)} onStale={list.reload}
          onSaved={(_, isNew) => { setEditing(null); toast.success(isNew ? 'Category created.' : 'Category updated.'); list.reload() }}
        />
      )}
      {deleting && (
        <ConfirmDeleteModal
          title="Delete category" label={deleting.name}
          path={`/equipment-categories/${deleting.public_id}/`} rowVersion={deleting.row_version}
          onClose={() => setDeleting(null)} onStale={list.reload}
          onDone={() => { setDeleting(null); toast.success('Category deleted.'); list.reload() }}
        />
      )}
    </>
  )
}