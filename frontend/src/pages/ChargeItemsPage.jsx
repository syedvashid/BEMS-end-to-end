import { useState } from 'react'
import { Button, Table, useToast } from '../components/ui'
import ChargeItemFormModal from '../components/billing/ChargeItemFormModal.jsx'
import ConfirmModal from '../components/billing/ConfirmModal.jsx'
import { Field, Pager, api, inr, qs, rowOf, useFetch, usePermission } from '../components/billing/shared.jsx'

export default function ChargeItemsPage() {
  const toast = useToast()
  const canConfigure = usePermission('charge.configure')
  const [search, setSearch] = useState('')
  const [term, setTerm] = useState('')
  const [page, setPage] = useState(1)
  const [editing, setEditing] = useState(null)   // null | {} (new) | item
  const [deleting, setDeleting] = useState(null)
  const { data, loading, error, reload } = useFetch(`/charge-items/?${qs({ search: term, page, page_size: 20 })}`)

  const columns = [
    { key: 'item_code', header: 'Code' },
    { key: 'name', header: 'Name' },
    { key: 'unit_label', header: 'Unit' },
    { key: 'default_rate', header: 'Default rate', render: (a, b) => inr(rowOf(a, b).default_rate) },
    { key: 'description', header: 'Description' },
    ...(canConfigure ? [{ key: 'actions', header: '', className: 'actions', render: (a, b) => {
      const it = rowOf(a, b)
      return (
        <div className="row">
          <Button size="sm" onClick={() => setEditing(it)}>Edit</Button>
          <Button size="sm" variant="danger" onClick={() => setDeleting(it)}>Delete</Button>
        </div>
      )
    } }] : []),
  ]

  return (
    <section>
      <div className="page-head">
        <h1>Charge Items</h1><span className="spacer" />
        {canConfigure && <Button variant="primary" onClick={() => setEditing({})}>New charge item</Button>}
      </div>
      <form className="filters" onSubmit={(e) => { e.preventDefault(); setPage(1); setTerm(search) }}>
        <Field label="Search" name="f_search" as="input" value={search} onChange={(e) => setSearch(e.target.value)} />
        <Button type="submit">Search</Button>
      </form>
      {error && <div className="alert alert-danger">{error.message}</div>}
      <Table columns={columns} rows={data?.results} loading={loading} empty="No charge items yet." />
      <Pager data={data} page={page} onPage={setPage} />
      {editing && (
        <ChargeItemFormModal item={editing.public_id ? editing : null} onClose={() => setEditing(null)}
          onSaved={() => { toast.success(editing.public_id ? 'Charge item updated.' : 'Charge item created.'); setEditing(null); reload() }} />
      )}
      {deleting && (
        <ConfirmModal title="Delete charge item" onClose={() => setDeleting(null)}
          onConfirm={async () => {
            await api.delete(`/charge-items/${deleting.public_id}/`, { params: { row_version: deleting.row_version } })
            setDeleting(null); toast.success('Charge item deleted.'); reload()
          }}>
          <p>Delete <strong>{deleting.item_code}</strong>? It cannot be deleted while active charge mappings use it.</p>
        </ConfirmModal>
      )}
    </section>
  )
}
