import { useState } from 'react'
import ExpiryBadge from '../components/ExpiryBadge'
import { Button, FormField, Pagination, Table, useToast } from '../components/ui'
import useFetch from '../hooks/useFetch'
import {
  DOCUMENT_TYPES, ENTITY_TYPES, INLINE_TYPES, entityLabel, friendlyError, fmtDate, openDocumentLink, typeLabel,
} from '../utils/documents'
import { parseApiError } from '../utils/errors'
import { dash } from '../utils/formHelpers'
import { PAGE_SIZE } from '../utils/format'

export default function DocumentsPage() {
  const toast = useToast()
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState({ search: '', entity_type: '', document_type: '', expiry_before: '' })
  const [applied, setApplied] = useState(filters)
  const list = useFetch('/documents/', { page, page_size: PAGE_SIZE, ...applied })
  const set = (k) => (e) => setFilters((f) => ({ ...f, [k]: e.target.value }))

  const open = async (d, inline) => {
    try { await openDocumentLink(d.public_id, d.current_version_no, inline) } catch (e) { toast.error(friendlyError(parseApiError(e))) }
  }

  const columns = [
    { key: 'title', header: 'Title' },
    { key: 'document_type', header: 'Type', render: (d) => typeLabel(d.document_type) },
    { key: 'entity', header: 'Attached to', render: (d) => `${entityLabel(d.entity_type)}: ${d.entity_label ?? d.entity.slice(0, 8)}` },
    { key: 'current_version_no', header: 'Version', render: (d) => `v${d.current_version_no}` },
    { key: 'expiry_date', header: 'Expiry', render: (d) => <>{d.expiry_date ? fmtDate(d.expiry_date) : dash(null)}<ExpiryBadge date={d.expiry_date} /></> },
    { key: 'created_at', header: 'Uploaded', render: (d) => fmtDate(d.created_at) },
    {
      key: 'actions', header: '', className: 'actions',
      render: (d) => (
        <div className="row">
          {INLINE_TYPES.includes(d.current_version?.content_type) && <Button size="sm" onClick={() => open(d, true)}>View</Button>}
          <Button size="sm" onClick={() => open(d, false)}>Download</Button>
        </div>
      ),
    },
  ]

  return (
    <>
      <div className="page-head"><h1>Documents</h1></div>
      <form className="filters" onSubmit={(e) => { e.preventDefault(); setPage(1); setApplied(filters) }}>
        <FormField label="Search title" name="f_search" value={filters.search} onChange={set('search')} />
        <FormField label="Attached to" name="f_entity_type" as="select" value={filters.entity_type} onChange={set('entity_type')}
          options={[{ value: '', label: 'All records' }, ...ENTITY_TYPES]} />
        <FormField label="Type" name="f_document_type" as="select" value={filters.document_type} onChange={set('document_type')}
          options={[{ value: '', label: 'All types' }, ...DOCUMENT_TYPES]} />
        <FormField label="Expiring on or before" name="f_expiry_before" type="date" value={filters.expiry_before} onChange={set('expiry_before')} />
        <Button type="submit">Search</Button>
      </form>
      {list.error && <div className="alert alert-danger">{friendlyError(list.error)}</div>}
      <Table columns={columns} rows={list.data?.results} loading={list.loading} empty="No documents found." />
      <Pagination page={page} pageSize={PAGE_SIZE} count={list.data?.count ?? 0} onPageChange={setPage} />
    </>
  )
}