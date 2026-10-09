import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { Button, FormField, Table } from '../components/ui'
import { fieldError, parseApiError } from '../utils/errors'
import { BLANK, IMPORT_FIELDS, friendly, opt } from '../utils/equipment'

const MULTIPART = { headers: { 'Content-Type': 'multipart/form-data' } }

export default function EquipmentImportPage() {
  const [file, setFile] = useState(null)          // kept in memory between steps
  const [mapping, setMapping] = useState({})
  const [result, setResult] = useState(null)
  const [done, setDone] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const form = (withMapping) => {
    const fd = new FormData()
    fd.append('file', file)
    if (withMapping) fd.append('mapping', JSON.stringify(mapping))
    return fd
  }

  const downloadTemplate = async () => {
    const res = await api.get('/equipment/import/template/', { responseType: 'blob' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(res.data); a.download = 'equipment_import_template.csv'; a.click()
    URL.revokeObjectURL(a.href)
  }

  const check = async (withMapping) => {
    setBusy(true); setErr(null)
    try {
      const { data } = await api.post('/equipment/import/dry-run/', form(withMapping), MULTIPART)
      setResult(data)
      if (!withMapping) setMapping(data.mapping || {})   // auto-matched by header
    } catch (e) { setErr(parseApiError(e)); setResult(null) }
    setBusy(false)
  }

  const confirm = async () => {
    setBusy(true); setErr(null)
    try {
      const { data } = await api.post('/equipment/import/', form(true), MULTIPART)
      setDone(data)
    } catch (e) { setErr(parseApiError(e)) }
    setBusy(false)
  }

  const pick = (e) => { setFile(e.target.files?.[0] ?? null); setResult(null); setMapping({}); setErr(null) }
  const ok = result && !result.errors.length && !result.missing_models.length && !result.missing_columns.length && result.valid_rows > 0
  const headerOptions = [BLANK, ...(result?.headers || []).filter(Boolean).map((h) => opt(h, h))]

  if (done) {
    return (
      <section>
        <h2>Import complete</h2>
        <p>{done.imported} records imported ({done.first_asset_tag} to {done.last_asset_tag}).</p>
        <Link to="/equipment">Back to equipment</Link>
      </section>
    )
  }

  return (
    <section>
      <div className="page-head"><h2>Import equipment</h2><span className="spacer" />
        <Button onClick={downloadTemplate}>Download template</Button><Link to="/equipment">Cancel</Link></div>
      <p className="muted">Existing equipment models must already exist (manufacturer + model number). Imported items are created as
        in-service legacy entries. CSV or XLSX, up to 5 MB and 5,000 rows.</p>
      {err && <div className="alert alert-danger">{fieldError(err, 'file') || fieldError(err, 'mapping') || friendly(err)}</div>}

      <input type="file" accept=".csv,.xlsx" onChange={pick} />
      <Button variant="primary" disabled={!file} loading={busy && !result} onClick={() => check(false)}>Check file</Button>

      {result && (
        <>
          <h3>Column mapping</h3>
          {!!result.missing_columns.length && (
            <div className="alert alert-warning">Map these required columns: {result.missing_columns.join(', ')}</div>
          )}
          <div className="row">
            {IMPORT_FIELDS.map(([key, label, required]) => (
              <FormField key={key} label={label} name={`map_${key}`} as="select" required={!!required} options={headerOptions}
                value={mapping[key] || ''} onChange={(e) => setMapping((m) => ({ ...m, [key]: e.target.value || null }))} />
            ))}
          </div>
          <Button loading={busy} onClick={() => check(true)}>Re-check with this mapping</Button>

          <h3>Results</h3>
          <p>{result.total_rows} rows, {result.valid_rows} valid, {result.total_rows - result.valid_rows} with errors.</p>
          {!!result.missing_models.length && (
            <>
              <h4>Missing equipment models (create them first)</h4>
              <Table rowKey="_k" columns={[
                { key: 'manufacturer', header: 'Manufacturer' }, { key: 'model_number', header: 'Model number' },
                { key: 'rows', header: 'Rows', render: (m) => m.rows.join(', ') },
              ]} rows={result.missing_models.map((m, i) => ({ ...m, _k: i }))} />
            </>
          )}
          {!!result.errors.length && (
            <>
              <h4>Errors{result.errors_truncated ? ' (first 500)' : ''}</h4>
              <Table rowKey="_k" columns={[
                { key: 'row', header: 'Row' }, { key: 'field', header: 'Field' }, { key: 'message', header: 'Problem' },
              ]} rows={result.errors.map((e, i) => ({ ...e, _k: i }))} />
            </>
          )}
          <Button variant="primary" disabled={!ok} loading={busy} onClick={confirm}>
            Import {result.valid_rows} rows
          </Button>
          {!ok && <span className="muted"> Fix all problems first; nothing is saved if any row has an error.</span>}
        </>
      )}
    </section>
  )
}
