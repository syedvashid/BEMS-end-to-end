import { useState } from 'react'
import { api } from '../api/client'
import { Button, FormField, Modal, Table, useToast } from '../components/ui'
import SimplePager from '../components/SimplePager'
import { useFacility } from '../context/FacilityContext'
import useFetch from '../hooks/useFetch'
import { apiError, errorText, fe, num, opts, toNull } from '../utils/maintenance'
import '../styles/maintenance.css'

const blankItem = () => ({ item_text: '', item_type: 'CHECK', unit: '', min_value: '', max_value: '' })

function TemplateEditor({ template, onClose, onSaved }) {
  const cats = useFetch('/equipment-categories/', { page_size: 100 })
  const models = useFetch('/equipment-models/', { page_size: 100 })
  const [f, setF] = useState({
    name: template?.name || '', description: template?.description || '',
    category: template?.category?.public_id || '', equipment_model: template?.equipment_model?.public_id || '',
  })
  const [items, setItems] = useState(template ? template.items.map((i) => ({
    item_text: i.item_text, item_type: i.item_type, unit: i.unit || '', min_value: i.min_value ?? '', max_value: i.max_value ?? '',
  })) : [blankItem()])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }))
  const setItem = (i, k, v) => setItems((rs) => rs.map((r, n) => (n === i ? { ...r, [k]: v } : r)))
  const move = (i, d) => setItems((rs) => { const a = [...rs]; const j = i + d; if (j < 0 || j >= a.length) return a; [a[i], a[j]] = [a[j], a[i]]; return a })

  const save = async () => {
    setBusy(true); setErr(null)
    const body = {
      name: f.name, description: toNull(f.description), category: toNull(f.category), equipment_model: toNull(f.equipment_model),
      items: items.map((r) => ({
        item_text: r.item_text, item_type: r.item_type, unit: toNull(r.unit),
        min_value: r.item_type === 'MEASUREMENT' ? toNull(r.min_value) : null, max_value: r.item_type === 'MEASUREMENT' ? toNull(r.max_value) : null,
      })),
    }
    try {
      if (template) await api.patch(`/checklist-templates/${template.public_id}/`, { ...body, row_version: template.row_version })
      else await api.post('/checklist-templates/', body)
      onSaved()
    } catch (e) { setErr(apiError(e)) } finally { setBusy(false) }
  }
  const c = cats.data?.results || []
  const m = models.data?.results || []
  return (
    <Modal wide title={template ? 'Edit checklist template' : 'New checklist template'} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Close</Button><Button variant="primary" loading={busy} onClick={save}>Save</Button></>}>
      {err && <div className="alert alert-danger">{errorText(err)}{err.details?.items ? ' Check the items.' : ''}</div>}
      <FormField label="Name" name="name" required value={f.name} onChange={set('name')} error={fe(err, 'name')} />
      <FormField label="Description" name="description" as="textarea" value={f.description} onChange={set('description')} error={fe(err, 'description')} />
      <div className="mt-row">
        <FormField label="For category (optional)" name="category" as="select" value={f.category} onChange={set('category')}
          options={opts(c.map((x) => x.public_id), Object.fromEntries(c.map((x) => [x.public_id, x.name])), '— any —')} error={fe(err, 'category')} />
        <FormField label="For model (optional)" name="equipment_model" as="select" value={f.equipment_model} onChange={set('equipment_model')}
          options={opts(m.map((x) => x.public_id), Object.fromEntries(m.map((x) => [x.public_id, x.model_name])), '— any —')} error={fe(err, 'equipment_model')} />
      </div>
      <h4>Items (in order)</h4>
      {items.map((r, i) => (
        <div className="mt-row" key={i}>
          <strong>{i + 1}</strong>
          <FormField label="Text" name={`t${i}`} value={r.item_text} onChange={(e) => setItem(i, 'item_text', e.target.value)} />
          <FormField label="Type" name={`ty${i}`} as="select" options={opts(['CHECK', 'MEASUREMENT'], { CHECK: 'Check', MEASUREMENT: 'Measurement' })}
            value={r.item_type} onChange={(e) => setItem(i, 'item_type', e.target.value)} />
          {r.item_type === 'MEASUREMENT' && (
            <>
              <FormField label="Unit" name={`u${i}`} value={r.unit} onChange={(e) => setItem(i, 'unit', e.target.value)} />
              <FormField label="Min" name={`mn${i}`} type="number" value={r.min_value} onChange={(e) => setItem(i, 'min_value', e.target.value)} />
              <FormField label="Max" name={`mx${i}`} type="number" value={r.max_value} onChange={(e) => setItem(i, 'max_value', e.target.value)} />
            </>
          )}
          <Button size="sm" onClick={() => move(i, -1)}>↑</Button>
          <Button size="sm" onClick={() => move(i, 1)}>↓</Button>
          <Button size="sm" variant="danger" onClick={() => setItems((rs) => rs.filter((_, n) => n !== i))}>Remove</Button>
        </div>
      ))}
      {err?.details?.items && <div className="alert alert-danger">{JSON.stringify(err.details.items)}</div>}
      <Button onClick={() => setItems((rs) => [...rs, blankItem()])}>Add item</Button>
    </Modal>
  )
}

export default function ChecklistTemplatesPage() {
  const { can } = useFacility()
  const toast = useToast()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [edit, setEdit] = useState(undefined)   // undefined = closed, null = new, object = existing
  const res = useFetch('/checklist-templates/', { page, page_size: 20, ...(search ? { search } : {}) })

  const open = async (row) => {
    try { const r = await api.get(`/checklist-templates/${row.public_id}/`); setEdit(r.data) } catch (e) { toast.error(errorText(apiError(e))) }
  }
  const remove = async (row) => {
    if (!window.confirm(`Delete template "${row.name}"?`)) return
    try { await api.delete(`/checklist-templates/${row.public_id}/`, { params: { row_version: row.row_version } }); toast.success('Deleted.'); res.reload() }
    catch (e) { toast.error(errorText(apiError(e))) }
  }
  return (
    <section>
      <div className="page-head"><h2>Checklist templates</h2><span className="spacer" />
        {can('checklist_template.add') && <Button variant="primary" onClick={() => setEdit(null)}>New template</Button>}
      </div>
      <div className="mt-toolbar"><FormField label="Search" name="search" value={search} onChange={(e) => { setPage(1); setSearch(e.target.value) }} /></div>
      <Table rows={res.data?.results} loading={res.loading} empty="No templates."
        columns={[
          { key: 'name', header: 'Name' },
          { key: 'category', header: 'Category', render: (r) => r.category?.name || '—' },
          { key: 'model', header: 'Model', render: (r) => r.equipment_model?.model_name || '—' },
          { key: 'item_count', header: 'Items' },
          { key: 'act', header: '', render: (r) => (
            <div className="mt-actions">
              {can('checklist_template.change') && <Button size="sm" onClick={() => open(r)}>Edit</Button>}
              {can('checklist_template.delete') && <Button size="sm" variant="danger" onClick={() => remove(r)}>Delete</Button>}
            </div>) },
        ]} />
      <SimplePager page={page} count={res.data?.count} pageSize={20} onPage={setPage} />
      {edit !== undefined && (
        <TemplateEditor template={edit} onClose={() => setEdit(undefined)}
          onSaved={() => { setEdit(undefined); toast.success('Saved.'); res.reload() }} />
      )}
    </section>
  )
}
