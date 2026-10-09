import { useState } from 'react'
import { api } from '../api/client'
import { Button, FormField, Modal, Table, useToast } from '../components/ui'
import FormDialog from '../components/FormDialog'
import SimplePager from '../components/SimplePager'
import { useFacility } from '../context/FacilityContext'
import useFetch from '../hooks/useFetch'
import { fmtDateTime } from '../utils/equipment'
import { apiError, errorText, fe, money, toNull } from '../utils/maintenance'
import '../styles/maintenance.css'

function PartForm({ part, onClose, onSaved }) {
  const cats = useFetch('/equipment-categories/', { page_size: 100 })
  const [f, setF] = useState({
    part_code: part?.part_code || '', name: part?.name || '', description: part?.description || '', unit: part?.unit || 'pcs',
    reorder_level: part?.reorder_level ?? 0, standard_unit_cost: part?.standard_unit_cost ?? '',
  })
  const [sel, setSel] = useState(() => new Set((part?.categories || []).map((c) => c.public_id)))
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }))
  const toggle = (id) => setSel((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n })
  const save = async () => {
    setBusy(true); setErr(null)
    const body = { part_code: f.part_code, name: f.name, description: toNull(f.description), unit: f.unit || 'pcs',
      reorder_level: toNull(f.reorder_level) ?? 0, standard_unit_cost: toNull(f.standard_unit_cost) }
    try {
      let saved
      if (part) saved = (await api.patch(`/spare-parts/${part.public_id}/`, { ...body, row_version: part.row_version })).data
      else saved = (await api.post('/spare-parts/', body)).data
      await api.put(`/spare-parts/${saved.public_id}/categories/`, { categories: [...sel], row_version: saved.row_version })
      onSaved()
    } catch (e) { setErr(apiError(e)) } finally { setBusy(false) }
  }
  const list = cats.data?.results || []
  return (
    <Modal title={part ? 'Edit spare part' : 'New spare part'} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Close</Button><Button variant="primary" loading={busy} onClick={save}>Save</Button></>}>
      {err && !Object.keys(err.details || {}).length && <div className="alert alert-danger">{errorText(err)}</div>}
      <FormField label="Part code" name="part_code" required value={f.part_code} onChange={set('part_code')} error={fe(err, 'part_code')} />
      <FormField label="Name" name="name" required value={f.name} onChange={set('name')} error={fe(err, 'name')} />
      <FormField label="Description" name="description" as="textarea" value={f.description} onChange={set('description')} error={fe(err, 'description')} />
      <div className="mt-row">
        <FormField label="Unit" name="unit" value={f.unit} onChange={set('unit')} error={fe(err, 'unit')} />
        <FormField label="Reorder level" name="reorder_level" type="number" value={f.reorder_level} onChange={set('reorder_level')} error={fe(err, 'reorder_level')} />
        <FormField label="Standard unit cost (INR)" name="standard_unit_cost" type="number" value={f.standard_unit_cost} onChange={set('standard_unit_cost')} error={fe(err, 'standard_unit_cost')} />
      </div>
      <h4>Compatible categories</h4>
      <div className="mt-grid">
        {list.map((c) => (
          <label key={c.public_id} className="mt-row"><input type="checkbox" checked={sel.has(c.public_id)} onChange={() => toggle(c.public_id)} /><span>{c.name}</span></label>
        ))}
      </div>
    </Modal>
  )
}

function Entries({ part, onClose }) {
  const [page, setPage] = useState(1)
  const res = useFetch(`/spare-parts/${part.public_id}/stock-entries/`, { page, page_size: 20 })
  return (
    <Modal wide title={`Stock entries — ${part.part_code}`} onClose={onClose} footer={<Button onClick={onClose}>Close</Button>}>
      <Table rows={res.data?.results} loading={res.loading} empty="No entries."
        columns={[
          { key: 'created_at', header: 'When', render: (r) => fmtDateTime(r.created_at) },
          { key: 'entry_type', header: 'Type' },
          { key: 'quantity', header: 'Qty' },
          { key: 'unit_cost', header: 'Unit cost', render: (r) => money(r.unit_cost) },
          { key: 'work_order', header: 'Work order', render: (r) => r.work_order || '—' },
          { key: 'note', header: 'Note', render: (r) => r.reason || r.reference_note || '—' },
          { key: 'created_by', header: 'By', render: (r) => r.created_by || '—' },
        ]} />
      <SimplePager page={page} count={res.data?.count} pageSize={20} onPage={setPage} />
    </Modal>
  )
}

export default function SparePartsPage() {
  const { can } = useFacility()
  const toast = useToast()
  const [page, setPage] = useState(1)
  const [f, setF] = useState({ search: '', low_stock: '' })
  const [modal, setModal] = useState(null)   // { kind, part }
  const res = useFetch('/spare-parts/', { page, page_size: 20, ...Object.fromEntries(Object.entries(f).filter(([, v]) => v !== '')) })
  const set = (k) => (e) => { setPage(1); setF((s) => ({ ...s, [k]: e.target.value })) }
  const close = () => setModal(null)
  const saved = (msg) => () => { close(); toast.success(msg); res.reload() }
  const remove = async (p) => {
    if (!window.confirm(`Delete ${p.part_code}?`)) return
    try { await api.delete(`/spare-parts/${p.public_id}/`, { params: { row_version: p.row_version } }); toast.success('Deleted.'); res.reload() }
    catch (e) { toast.error(errorText(apiError(e))) }
  }
  const open = async (kind, p) => {
    if (kind === 'edit') {   // fetch the detail so categories and row_version are current
      try { setModal({ kind, part: (await api.get(`/spare-parts/${p.public_id}/`)).data }) } catch (e) { toast.error(errorText(apiError(e))) }
    } else setModal({ kind, part: p })
  }
  const stockPost = (p, body) => api.post(`/spare-parts/${p.public_id}/stock/`, body)

  return (
    <section>
      <div className="page-head"><h2>Spare parts</h2><span className="spacer" />
        {can('spare_part.add') && <Button variant="primary" onClick={() => setModal({ kind: 'edit', part: null })}>New part</Button>}
      </div>
      <div className="mt-toolbar">
        <FormField label="Search" name="search" value={f.search} onChange={set('search')} />
        <FormField label="Stock" name="low_stock" as="select" options={[{ value: '', label: 'All' }, { value: 'true', label: 'Low stock only' }]} value={f.low_stock} onChange={set('low_stock')} />
      </div>
      <Table rows={res.data?.results} loading={res.loading} empty="No spare parts."
        columns={[
          { key: 'part_code', header: 'Code' },
          { key: 'name', header: 'Name' },
          { key: 'cats', header: 'Categories', render: (p) => p.categories.map((c) => c.name).join(', ') || '—' },
          { key: 'on_hand', header: 'On hand', render: (p) => <>{p.on_hand_quantity} {p.unit} {p.is_low_stock && <span className="mt-pill mt-low">Low</span>}</> },
          { key: 'reorder_level', header: 'Reorder at' },
          { key: 'act', header: '', render: (p) => (
            <div className="mt-actions">
              <Button size="sm" onClick={() => open('entries', p)}>Entries</Button>
              {can('spare_part.stock') && <Button size="sm" onClick={() => open('receive', p)}>Receive</Button>}
              {can('spare_part.stock') && <Button size="sm" onClick={() => open('adjust', p)}>Adjust</Button>}
              {can('spare_part.change') && <Button size="sm" onClick={() => open('edit', p)}>Edit</Button>}
              {can('spare_part.delete') && <Button size="sm" variant="danger" onClick={() => remove(p)}>Delete</Button>}
            </div>) },
        ]} />
      <SimplePager page={page} count={res.data?.count} pageSize={20} onPage={setPage} />

      {modal?.kind === 'edit' && <PartForm part={modal.part} onClose={close} onSaved={saved('Saved.')} />}
      {modal?.kind === 'entries' && <Entries part={modal.part} onClose={close} />}
      {modal?.kind === 'receive' && (
        <FormDialog title={`Receive stock — ${modal.part.part_code}`} submitLabel="Receive" onClose={close}
          fields={[
            { name: 'quantity', label: 'Quantity', type: 'number', required: true },
            { name: 'unit_cost', label: 'Unit cost (INR)', type: 'number' },
            { name: 'reference_note', label: 'Reference (invoice / GRN)' },
          ]}
          onSubmit={async (v) => { await stockPost(modal.part, { entry_type: 'RECEIPT', quantity: v.quantity, unit_cost: toNull(v.unit_cost), reference_note: toNull(v.reference_note) }); saved('Stock received.')() }} />
      )}
      {modal?.kind === 'adjust' && (
        <FormDialog title={`Adjust stock — ${modal.part.part_code}`} submitLabel="Adjust" onClose={close}
          intro={`On hand: ${modal.part.on_hand_quantity} ${modal.part.unit}. Use a negative number to remove stock.`}
          fields={[
            { name: 'quantity', label: 'Quantity (+/−)', type: 'number', required: true },
            { name: 'reason', label: 'Reason', as: 'textarea', required: true },
          ]}
          onSubmit={async (v) => { await stockPost(modal.part, { entry_type: 'ADJUSTMENT', quantity: v.quantity, reason: v.reason }); saved('Stock adjusted.')() }} />
      )}
    </section>
  )
}
