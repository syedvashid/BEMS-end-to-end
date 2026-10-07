import { useState } from 'react'
import { api } from '../api/client'
import { useFacility } from '../context/FacilityContext'
import useFetch from '../hooks/useFetch'
import {
  DOCUMENT_TYPES, INLINE_TYPES, checkFile, friendlyError, fmtDate, formatBytes, openDocumentLink, typeLabel,
} from '../utils/documents'
import { fieldError, parseApiError } from '../utils/errors'
import { dash } from '../utils/formHelpers'
import ConfirmDeleteModal from './ConfirmDeleteModal'
import ExpiryBadge from './ExpiryBadge'
import { Button, FormField, Modal, Table, useToast } from './ui'

const FIELD_KEYS = ['title', 'document_type', 'description', 'expiry_date', 'file']
const hasFieldError = (err) => FIELD_KEYS.some((k) => fieldError(err, k))
// axios drops this header for FormData so the browser adds the multipart boundary.
const MULTIPART = { headers: { 'Content-Type': 'multipart/form-data' } }

function UploadModal({ entityType, entityId, doc, onClose, onDone }) {
  const isVersion = !!doc
  const [f, setF] = useState({ document_type: 'OTHER', title: '', description: '', expiry_date: '' })
  const [file, setFile] = useState(null)
  const [fileMsg, setFileMsg] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }))

  const pick = (e) => {
    const picked = e.target.files?.[0] ?? null
    setFile(picked); setFileMsg(picked ? checkFile(picked) : null)
    if (picked && !f.title && !isVersion) setF((x) => ({ ...x, title: picked.name.replace(/\.[^.]+$/, '') }))
  }

  const submit = async () => {
    const msg = checkFile(file)
    if (msg) { setFileMsg(msg); return }
    const fd = new FormData()
    if (!isVersion) {
      fd.append('entity_type', entityType); fd.append('entity', entityId)
      fd.append('document_type', f.document_type); fd.append('title', f.title.trim())
      if (f.description.trim()) fd.append('description', f.description.trim())
      if (f.expiry_date) fd.append('expiry_date', f.expiry_date)
    }
    fd.append('file', file)
    setBusy(true); setErr(null)
    try {
      await api.post(isVersion ? `/documents/${doc.public_id}/versions/` : '/documents/', fd, MULTIPART)
      onDone(isVersion)
    } catch (e) { setErr(parseApiError(e)); setBusy(false) }
  }

  return (
    <Modal
      title={isVersion ? `New version of "${doc.title}"` : 'Upload document'} onClose={onClose}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} onClick={submit}>Upload</Button></>}
    >
      {err && !hasFieldError(err) && <div className="alert alert-danger">{friendlyError(err)}</div>}
      {!isVersion && (
        <>
          <FormField label="Type" name="document_type" as="select" required options={DOCUMENT_TYPES}
            value={f.document_type} onChange={set('document_type')} error={fieldError(err, 'document_type')} />
          <FormField label="Title" name="title" required value={f.title} onChange={set('title')} error={fieldError(err, 'title')} />
          <FormField label="Description" name="description" as="textarea" value={f.description}
            onChange={set('description')} error={fieldError(err, 'description')} />
          <FormField label="Expiry date" name="expiry_date" type="date" value={f.expiry_date}
            onChange={set('expiry_date')} error={fieldError(err, 'expiry_date')} hint="Optional" />
        </>
      )}
      <div>
        <label htmlFor="doc_file">File *</label><br />
        <input id="doc_file" type="file" accept=".pdf,.jpg,.jpeg,.png,.docx,.xlsx" onChange={pick} />
        <div className="hint">PDF, JPG, PNG, DOCX or XLSX, up to 20 MB.</div>
        {(fileMsg || fieldError(err, 'file')) && <div className="alert alert-danger">{fileMsg || fieldError(err, 'file')}</div>}
      </div>
    </Modal>
  )
}

function EditModal({ doc, onClose, onDone, onStale }) {
  const [f, setF] = useState({
    title: doc.title, document_type: doc.document_type,
    description: doc.description ?? '', expiry_date: doc.expiry_date ?? '',
  })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }))

  const submit = async () => {
    setBusy(true); setErr(null)
    try {
      await api.patch(`/documents/${doc.public_id}/`, {
        title: f.title.trim(), document_type: f.document_type,
        description: f.description.trim() || null, expiry_date: f.expiry_date || null,
        row_version: doc.row_version,
      })
      onDone()
    } catch (e) {
      const parsed = parseApiError(e)
      if (parsed.code === 'stale_version') onStale()
      setErr(parsed); setBusy(false)
    }
  }

  return (
    <Modal
      title="Edit document" onClose={onClose}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} onClick={submit}>Save</Button></>}
    >
      {err && !hasFieldError(err) && <div className="alert alert-danger">{friendlyError(err)}</div>}
      <FormField label="Type" name="document_type" as="select" required options={DOCUMENT_TYPES}
        value={f.document_type} onChange={set('document_type')} error={fieldError(err, 'document_type')} />
      <FormField label="Title" name="title" required value={f.title} onChange={set('title')} error={fieldError(err, 'title')} />
      <FormField label="Description" name="description" as="textarea" value={f.description}
        onChange={set('description')} error={fieldError(err, 'description')} />
      <FormField label="Expiry date" name="expiry_date" type="date" value={f.expiry_date}
        onChange={set('expiry_date')} error={fieldError(err, 'expiry_date')} hint="Optional" />
    </Modal>
  )
}

function VersionsModal({ doc, onClose, onOpen }) {
  const detail = useFetch(`/documents/${doc.public_id}/`)
  const columns = [
    { key: 'version_no', header: 'Version', render: (v) => `v${v.version_no}` },
    { key: 'original_filename', header: 'File' },
    { key: 'size_bytes', header: 'Size', render: (v) => formatBytes(v.size_bytes) },
    { key: 'uploaded_by', header: 'Uploaded by', render: (v) => dash(v.uploaded_by) },
    { key: 'uploaded_at', header: 'Uploaded', render: (v) => fmtDate(v.uploaded_at) },
    {
      key: 'actions', header: '', className: 'actions',
      render: (v) => (
        <div className="row">
          {INLINE_TYPES.includes(v.content_type) && <Button size="sm" onClick={() => onOpen(doc, v.version_no, true)}>View</Button>}
          <Button size="sm" onClick={() => onOpen(doc, v.version_no, false)}>Download</Button>
        </div>
      ),
    },
  ]
  return (
    <Modal title={`Versions: ${doc.title}`} onClose={onClose} wide footer={<Button onClick={onClose}>Close</Button>}>
      {detail.error && <div className="alert alert-danger">{friendlyError(detail.error)}</div>}
      <Table columns={columns} rows={detail.data?.versions} rowKey="version_no" loading={detail.loading} />
    </Modal>
  )
}

export default function DocumentsPanel({ entityType, entityId, viewPermission, attachPermission }) {
  const { can } = useFacility()
  const toast = useToast()
  const [uploading, setUploading] = useState(false)
  const [versionFor, setVersionFor] = useState(null)
  const [editing, setEditing] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [history, setHistory] = useState(null)

  const canView = can('document.view') && can(viewPermission)
  const canAdd = can('document.add') && can(attachPermission)
  const canChange = can('document.change') && can(attachPermission)
  const canDelete = can('document.delete') && can(attachPermission)
  const list = useFetch('/documents/', { entity_type: entityType, entity: entityId, page_size: 100 }, canView)

  if (!canView) return null

  const open = async (doc, versionNo, inline) => {
    try { await openDocumentLink(doc.public_id, versionNo, inline) } catch (e) { toast.error(friendlyError(parseApiError(e))) }
  }

  const columns = [
    { key: 'title', header: 'Title' },
    { key: 'document_type', header: 'Type', render: (d) => <span className="doc-badge doc-badge-type">{typeLabel(d.document_type)}</span> },
    { key: 'current_version_no', header: 'Version', render: (d) => `v${d.current_version_no}` },
    { key: 'expiry_date', header: 'Expiry', render: (d) => <>{d.expiry_date ? fmtDate(d.expiry_date) : dash(null)}<ExpiryBadge date={d.expiry_date} /></> },
    { key: 'created_at', header: 'Uploaded', render: (d) => fmtDate(d.created_at) },
    {
      key: 'actions', header: '', className: 'actions',
      render: (d) => (
        <div className="row">
          {INLINE_TYPES.includes(d.current_version?.content_type) && <Button size="sm" onClick={() => open(d, d.current_version_no, true)}>View</Button>}
          <Button size="sm" onClick={() => open(d, d.current_version_no, false)}>Download</Button>
          <Button size="sm" onClick={() => setHistory(d)}>Versions</Button>
          {canChange && <Button size="sm" onClick={() => setVersionFor(d)}>New version</Button>}
          {canChange && <Button size="sm" onClick={() => setEditing(d)}>Edit</Button>}
          {canDelete && <Button size="sm" variant="danger" onClick={() => setDeleting(d)}>Delete</Button>}
        </div>
      ),
    },
  ]

  return (
    <section>
      <div className="page-head">
        <h2>Documents</h2><span className="spacer" />
        {canAdd && <Button variant="primary" onClick={() => setUploading(true)}>Upload document</Button>}
      </div>
      {list.error && <div className="alert alert-danger">{friendlyError(list.error)}</div>}
      <Table columns={columns} rows={list.data?.results} loading={list.loading} empty="No documents yet." />

      {uploading && (
        <UploadModal entityType={entityType} entityId={entityId} onClose={() => setUploading(false)}
          onDone={() => { setUploading(false); toast.success('Document uploaded.'); list.reload() }} />
      )}
      {versionFor && (
        <UploadModal doc={versionFor} onClose={() => setVersionFor(null)}
          onDone={() => { setVersionFor(null); toast.success('New version added.'); list.reload() }} />
      )}
      {editing && (
        <EditModal doc={editing} onClose={() => setEditing(null)} onStale={list.reload}
          onDone={() => { setEditing(null); toast.success('Document updated.'); list.reload() }} />
      )}
      {history && <VersionsModal doc={history} onClose={() => setHistory(null)} onOpen={open} />}
      {deleting && (
        <ConfirmDeleteModal
          title="Delete document" label={deleting.title}
          path={`/documents/${deleting.public_id}/`} rowVersion={deleting.row_version}
          onClose={() => setDeleting(null)} onStale={list.reload}
          onDone={() => { setDeleting(null); toast.success('Document deleted.'); list.reload() }}
        />
      )}
    </section>
  )
}